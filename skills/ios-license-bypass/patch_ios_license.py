"""
patch_ios_license.py — iOS license gate bypass via binary patching.

Parses Mach-O binaries, locates Objective-C method implementations,
patches ARM64 instructions to neutralize license checks, and repackages the IPA.

Usage:
    py patch_ios_license.py <ipa_path> [--output <output_ipa>] [--work-dir <dir>]

Requirements:
    - Python 3.10+
    - No external dependencies (pure stdlib)
"""

import struct
import os
import sys
import zipfile
import hashlib
import argparse
from pathlib import Path

# ─── ARM64 patch bytes ───
# mov w0, #1; ret  →  return YES (true)
RETURN_YES = bytes([0x01, 0x00, 0x80, 0xD2, 0x00, 0x01, 0x1F, 0xD6])
# mov w0, #0; ret  →  return NO (false)
RETURN_NO = bytes([0x00, 0x00, 0x80, 0xD2, 0x00, 0x01, 0x1F, 0xD6])
# NOP
NOP = bytes([0x1F, 0x20, 0x03, 0xD5])

# ─── patch targets ───
# Map selector names to patch types
PATCH_SELECTORS = {
    # Force license valid
    "isLicensed": "return_yes",
    "isValid": "return_yes",
    "isExpired": "return_no",
    "isActiveLicenseInfo:": "return_yes",
    
    # NOP crash gates
    "enforceAuthGateFromViewController:title:message:crashApp:": "nop",
    "setLicensedState": "nop",
    "markCredentialsVerified": "nop",
    
    # Short-circuit network/verify
    "activateDeviceWithUID:key:onSuccess:onFailure:": "return_yes",
    "pollKeyLiveVerifyForAuth:": "return_yes",
    "verifyKeyLockLiveBeforeHUDWithCompletion:": "return_yes",
    "validateResponse:length:responseStatusCode:": "return_yes",
    
    # Bypass error classification
    "isInvalidAESKeyError:": "return_no",
    "isInvalidPackageTokenError:responseBody:": "return_no",
    "isPackageTokenInvalidError:message:": "return_no",
}

PATCH_BYTES = {
    "return_yes": RETURN_YES,
    "return_no": RETURN_NO,
    "nop": NOP * 2,  # 8 bytes of NOP
}


def read_cstr(data, offset):
    """Read a C string from data at offset."""
    if offset >= len(data):
        return ""
    end = data.find(b'\x00', offset)
    if end == -1:
        return ""
    return data[offset:end].decode('ascii', errors='replace')


def build_vmaddr_map(data):
    """Build vmaddr→file offset mapping from Mach-O segments."""
    magic = struct.unpack_from('<I', data, 0)[0]
    if magic != 0xfeedfacf:  # 64-bit Mach-O
        return None
    
    ncmds = struct.unpack_from('<I', data, 16)[0]
    offset = 32  # mach_header_64 size
    segments = []
    
    for i in range(ncmds):
        cmd = struct.unpack_from('<I', data, offset)[0]
        cmdsize = struct.unpack_from('<I', data, offset + 4)[0]
        
        if cmd == 0x19:  # LC_SEGMENT_64
            vmaddr = struct.unpack_from('<Q', data, offset + 24)[0]
            vmsize = struct.unpack_from('<Q', data, offset + 32)[0]
            fileoff = struct.unpack_from('<Q', data, offset + 40)[0]
            filesize = struct.unpack_from('<Q', data, offset + 48)[0]
            segments.append((vmaddr, vmsize, fileoff, filesize))
        
        offset += cmdsize
    
    return segments


def vmaddr_to_offset(segments, vmaddr):
    """Convert vmaddr to file offset using segment map."""
    for vmaddr_base, vmsize, fileoff, filesize in segments:
        if vmaddr_base <= vmaddr < vmaddr_base + vmsize:
            return fileoff + (vmaddr - vmaddr_base)
    return None


def get_classlist(data):
    """Find __objc_classlist section address and size."""
    magic = struct.unpack_from('<I', data, 0)[0]
    if magic != 0xfeedfacf:
        return 0, 0
    
    ncmds = struct.unpack_from('<I', data, 16)[0]
    offset = 32
    
    for i in range(ncmds):
        cmd = struct.unpack_from('<I', data, offset)[0]
        cmdsize = struct.unpack_from('<I', data, offset + 4)[0]
        
        if cmd == 0x19:  # LC_SEGMENT_64
            nsects = struct.unpack_from('<I', data, offset + 64)[0]
            sect_offset = offset + 72
            for j in range(nsects):
                sectname = data[sect_offset:sect_offset+16].rstrip(b'\x00').decode('ascii', errors='replace')
                if sectname == "__objc_classlist":
                    addr = struct.unpack_from('<Q', data, sect_offset + 32)[0]
                    size = struct.unpack_from('<Q', data, sect_offset + 40)[0]
                    return addr, size
                sect_offset += 80
        offset += cmdsize
    
    return 0, 0


def parse_methods(data, baseMethods_ptr, segments):
    """Parse a method_list_t and return (selector, imp_vmaddr, imp_file_offset) tuples."""
    if baseMethods_ptr == 0:
        return []
    
    entsize_flags = struct.unpack_from('<I', data, baseMethods_ptr)[0]
    count = struct.unpack_from('<I', data, baseMethods_ptr + 4)[0]
    entsize = entsize_flags & 0xFFFF
    
    methods = []
    for j in range(count):
        method_offset = baseMethods_ptr + 8 + j * entsize
        name_vmaddr = struct.unpack_from('<Q', data, method_offset)[0]
        imp_vmaddr = struct.unpack_from('<Q', data, method_offset + 16)[0]
        
        name_off = vmaddr_to_offset(segments, name_vmaddr)
        imp_off = vmaddr_to_offset(segments, imp_vmaddr)
        
        if name_off is None or imp_off is None:
            continue
        
        sel_name = read_cstr(data, name_off)
        methods.append((sel_name, imp_vmaddr, imp_off))
    
    return methods


def get_all_methods(data):
    """Get all methods from all classes and metaclasses.
    
    CRITICAL: All pointers in class structures are vmaddrs and must be
    converted to file offsets through the segment map before dereferencing.
    """
    segments = build_vmaddr_map(data)
    if not segments:
        return []
    
    classlist_vmaddr, classlist_size = get_classlist(data)
    if not classlist_vmaddr:
        return []
    
    # Convert classlist vmaddr to file offset
    classlist_addr = vmaddr_to_offset(segments, classlist_vmaddr)
    if classlist_addr is None:
        return []
    
    n_classes = classlist_size // 8
    all_methods = []
    
    for i in range(n_classes):
        class_ptr_vmaddr = struct.unpack_from('<Q', data, classlist_addr + i * 8)[0]
        if class_ptr_vmaddr == 0:
            continue
        
        # Convert class_ptr vmaddr to file offset
        class_ptr = vmaddr_to_offset(segments, class_ptr_vmaddr)
        if class_ptr is None:
            continue
        
        data_ptr_vmaddr = struct.unpack_from('<Q', data, class_ptr + 32)[0]
        if data_ptr_vmaddr == 0:
            continue
        
        # Convert data_ptr vmaddr to file offset
        data_ptr = vmaddr_to_offset(segments, data_ptr_vmaddr)
        if data_ptr is None:
            continue
        
        name_ptr_vmaddr = struct.unpack_from('<Q', data, data_ptr + 24)[0]
        if name_ptr_vmaddr == 0:
            continue
        
        name_off = vmaddr_to_offset(segments, name_ptr_vmaddr)
        if name_off is None:
            continue
        class_name = read_cstr(data, name_off)
        
        # Instance methods
        baseMethods_ptr_vmaddr = struct.unpack_from('<Q', data, data_ptr + 32)[0]
        baseMethods_ptr = vmaddr_to_offset(segments, baseMethods_ptr_vmaddr)
        if baseMethods_ptr is not None:
            methods = parse_methods(data, baseMethods_ptr, segments)
            for sel, imp_vm, imp_off in methods:
                all_methods.append((class_name, sel, imp_vm, imp_off))
        
        # Class methods (metaclass)
        meta_ptr_vmaddr = struct.unpack_from('<Q', data, class_ptr)[0]
        if meta_ptr_vmaddr:
            meta_ptr = vmaddr_to_offset(segments, meta_ptr_vmaddr)
            if meta_ptr is not None:
                meta_data_ptr_vmaddr = struct.unpack_from('<Q', data, meta_ptr + 32)[0]
                if meta_data_ptr_vmaddr:
                    meta_data_ptr = vmaddr_to_offset(segments, meta_data_ptr_vmaddr)
                    if meta_data_ptr is not None:
                        meta_baseMethods_ptr_vmaddr = struct.unpack_from('<Q', data, meta_data_ptr + 32)[0]
                        meta_baseMethods_ptr = vmaddr_to_offset(segments, meta_baseMethods_ptr_vmaddr)
                        if meta_baseMethods_ptr is not None:
                            meta_methods = parse_methods(data, meta_baseMethods_ptr, segments)
                            for sel, imp_vm, imp_off in meta_methods:
                                all_methods.append((class_name + " (class)", sel, imp_vm, imp_off))
    
    return all_methods


def extract_ipa(ipa_path, work_dir):
    """Extract IPA to working directory."""
    if os.path.exists(work_dir):
        import shutil
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)
    
    with zipfile.ZipFile(ipa_path, 'r') as zf:
        zf.extractall(work_dir)
    
    return work_dir


def find_binaries(work_dir):
    """Find all Mach-O binaries in the extracted IPA."""
    binaries = []
    for root, dirs, files in os.walk(work_dir):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'rb') as f:
                    magic = struct.unpack('<I', f.read(4))[0]
                    if magic == 0xfeedfacf:  # 64-bit Mach-O
                        binaries.append(file_path)
            except:
                pass
    return binaries


def patch_binary(binary_path, patch_selectors=None, target_classes=None):
    """Patch a binary's license gate methods.
    
    Args:
        binary_path: Path to the Mach-O binary
        patch_selectors: Dict of selector → patch_type (uses default if None)
        target_classes: Set of class names to limit patches to (None = all)
    
    Returns:
        List of (class_name, selector, file_offset, original_hex, patched_hex) tuples
    """
    if patch_selectors is None:
        patch_selectors = PATCH_SELECTORS
    
    with open(binary_path, 'rb') as f:
        data = bytearray(f.read())
    
    methods = get_all_methods(data)
    patches = []
    
    for class_name, sel, imp_vm, imp_off in methods:
        if sel not in patch_selectors:
            continue
        
        # Filter by class name if specified
        if target_classes:
            # Strip " (class)" suffix for comparison
            base_class = class_name.replace(" (class)", "")
            if base_class not in target_classes:
                continue
        
        patch_type = patch_selectors[sel]
        patch_bytes = PATCH_BYTES[patch_type]
        
        if imp_off + len(patch_bytes) > len(data):
            continue
        
        original = bytes(data[imp_off:imp_off + len(patch_bytes)])
        data[imp_off:imp_off + len(patch_bytes)] = patch_bytes
        
        patches.append((class_name, sel, imp_off, original.hex(), patch_bytes.hex()))
    
    if patches:
        with open(binary_path, 'wb') as f:
            f.write(data)
    
    return patches


def repackage_ipa(work_dir, output_path):
    """Repackage the modified files into a new IPA."""
    if os.path.exists(output_path):
        os.remove(output_path)
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(work_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, work_dir)
                zf.write(file_path, arcname)
    
    return output_path


def verify_patches(binary_path, patches):
    """Verify patches were applied correctly."""
    with open(binary_path, 'rb') as f:
        data = f.read()
    
    verified = 0
    for class_name, sel, imp_off, original_hex, patched_hex in patches:
        current = data[imp_off:imp_off + len(bytes.fromhex(patched_hex))]
        if current.hex() == patched_hex:
            verified += 1
    
    return verified


def main():
    parser = argparse.ArgumentParser(description='iOS license gate bypass via binary patching')
    parser.add_argument('ipa', help='Path to the IPA file')
    parser.add_argument('--output', '-o', help='Output IPA path (default: <name>_patched.ipa)')
    parser.add_argument('--work-dir', '-w', help='Working directory (default: ./work)')
    parser.add_argument('--target-classes', '-t', help='Comma-separated class names to target')
    parser.add_argument('--dry-run', '-d', action='store_true', help='Show patches without applying')
    
    args = parser.parse_args()
    
    ipa_path = args.ipa
    if not os.path.exists(ipa_path):
        print(f"ERROR: IPA not found: {ipa_path}")
        sys.exit(1)
    
    output_path = args.output or ipa_path.replace('.ipa', '_patched.ipa')
    work_dir = args.work_dir or os.path.join(os.path.dirname(ipa_path), 'work')
    
    target_classes = None
    if args.target_classes:
        target_classes = set(args.target_classes.split(','))
    
    print(f"IPA: {ipa_path}")
    print(f"Output: {output_path}")
    print(f"Work dir: {work_dir}")
    print()
    
    # Step 1: Extract
    print("[1/4] Extracting IPA...")
    extract_ipa(ipa_path, work_dir)
    print(f"  Extracted to: {work_dir}")
    
    # Step 2: Find binaries
    print("\n[2/4] Finding Mach-O binaries...")
    binaries = find_binaries(work_dir)
    print(f"  Found {len(binaries)} binaries")
    for b in binaries:
        print(f"    {os.path.relpath(b, work_dir)}")
    
    # Step 3: Patch
    print("\n[3/4] Patching license gate methods...")
    total_patches = 0
    for binary_path in binaries:
        rel_path = os.path.relpath(binary_path, work_dir)
        print(f"\n  Patching: {rel_path}")
        
        patches = patch_binary(binary_path, target_classes=target_classes)
        
        if patches:
            for class_name, sel, imp_off, orig_hex, patch_hex in patches:
                print(f"    {class_name}.{sel} @ {imp_off:#x}")
            print(f"  → {len(patches)} patches applied")
            total_patches += len(patches)
        else:
            print(f"  → No patches needed")
    
    print(f"\n  Total patches: {total_patches}")
    
    if args.dry_run:
        print("\n[dry-run] No changes saved.")
        return
    
    # Step 4: Repackage
    print("\n[4/4] Repackaging IPA...")
    repackage_ipa(work_dir, output_path)
    
    print(f"\nOutput: {output_path}")
    print(f"Size: {os.path.getsize(output_path):,} bytes")
    
    # Verify
    print("\nVerifying patches...")
    for binary_path in binaries:
        rel_path = os.path.relpath(binary_path, work_dir)
        patches = patch_binary(binary_path, target_classes=target_classes)
        # Re-read to verify
        with open(binary_path, 'rb') as f:
            data = f.read()
        verified = 0
        for class_name, sel, imp_off, orig_hex, patch_hex in patches:
            current = data[imp_off:imp_off + len(bytes.fromhex(patch_hex))]
            if current.hex() == patch_hex:
                verified += 1
        if verified:
            print(f"  {rel_path}: {verified}/{len(patches)} patches verified")
    
    print("\n--- Done ---")
    print(f"Patched IPA: {output_path}")
    print(f"Sign with your tool of choice (eSign, ldid, etc.)")


if __name__ == "__main__":
    main()
