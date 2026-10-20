# Skill: ios-license-bypass

Binary analysis and license gate bypass for iOS IPA files. Parses Mach-O binaries, locates Objective-C method implementations, patches ARM64 instructions to neutralize license checks, and repackages the IPA.

## When to use

- Analyzing iOS app license/DRM mechanisms
- Bypassing server-authoritative license gates in jailbroken app contexts
- Patching Objective-C method implementations at the binary level
- Repackaging IPAs with modified binaries

## Workflow

1. **Extract IPA** — unzip to a working directory
2. **Parse Mach-O** — map segments, find class lists, enumerate methods
3. **Locate gate methods** — map selectors to implementation addresses
4. **Patch binary** — overwrite with ARM64 instructions (return YES/NO, NOP)
5. **Repackage IPA** — rezip preserving structure

## Target binary structure

iOS apps contain:
- **Main executable** (e.g., `pool`) — app code, third-party SDKs
- **Frameworks** (e.g., `libloader.framework`) — DRM/license code
- **Dylibs** — dynamic libraries

License gates typically live in a dedicated framework with classes like:
- `Z8GateMgr` — main gate manager
- `Z8GateNet` — network/activation
- `Z8GateMon` — runtime monitoring
- `AuthLicenseStore` — key storage
- `Z8GateCrypt` — AES encryption

## Key selectors to patch

```python
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
```

## ARM64 patch bytes

```python
# mov w0, #1; ret  →  return YES (true)
RETURN_YES = bytes([0x01, 0x00, 0x80, 0xD2, 0x00, 0x01, 0x1F, 0xD6])

# mov w0, #0; ret  →  return NO (false)
RETURN_NO = bytes([0x00, 0x00, 0x80, 0xD2, 0x00, 0x01, 0x1F, 0xD6])

# NOP
NOP = bytes([0x1F, 0x20, 0x03, 0xD5])
```

## Critical: vmaddr → file offset conversion

**The #1 bug source.** All pointers in Mach-O class structures are virtual addresses (vmaddr), NOT file offsets. You MUST convert through the segment map before dereferencing.

```python
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
```

## Full patching script

See `patch_ios_license.py` for the complete implementation.

## Common errors and fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `struct.error: unpack_from requires a buffer` | Using vmaddr as file offset | Convert through segment map |
| Class list empty | Wrong section name or offset | Search for `__objc_classname` section |
| Methods not found | Selector in metaclass (class methods) | Check both class and metaclass |
| Patch not applied | Wrong file offset | Verify vmaddr→offset conversion |
| IPA corrupt | Missing files in repackage | Walk entire directory tree |

## IPA repackaging

```python
import zipfile
import os

def repackage_ipa(work_dir, output_path):
    """Repackage modified files into a new IPA."""
    if os.path.exists(output_path):
        os.remove(output_path)
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(work_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, work_dir)
                zf.write(file_path, arcname)
```

## Verification

After patching, verify:
1. Original bytes at patch locations are replaced
2. IPA structure is valid (can be unzipped)
3. Modified binaries are present in the IPA
4. SHA-256 of patched binary differs from original

## Limitations

- **Server-side trust**: If the server sends a signed "revoked" payload, the client may still reject it. The `SecKeyVerifySignature` hook requires function interposition (fishhook-style GOT replacement), not simple binary patching.
- **Collateral patches**: Broad selector matching may hit third-party SDK methods. Use class name filtering to minimize collateral damage.
- **Code signature**: Patched binaries will have invalid code signatures. Requires jailbreak or ad-hoc re-signing to run.
- **ARM64 only**: Patch bytes are for ARM64. ARMv7/x86_64 require different instruction encodings.
