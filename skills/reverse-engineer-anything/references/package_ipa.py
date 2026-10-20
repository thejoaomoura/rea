# Reusable Mach-O / IPA packaging logic for reverse-engineering workflows.
#
# Parses thin little-endian ARM64 Mach-O 64 images, removes an embedded code
# signature, injects a single LC_LOAD_DYLIB dependency, and repackages an IPA so
# that only the main executable is modified and every other member is preserved
# byte-for-byte. The result is UNSIGNED: re-sign the app and the added dylib with
# an external tool (e.g. ldid / a provisioning-based signer) before installing.
#
# Everything is parameterised (no app identity, module name, version, or path is
# hardcoded). Use it as a library (import the functions) or as a CLI.
from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import plistlib
import struct
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

MAGIC_64 = b"\xcf\xfa\xed\xfe"
ARM64 = 0x0100000C
LOAD_DYLIB = 0xC
ID_DYLIB = 0xD
CODE_SIGNATURE = 0x1D
DYLIB_COMMANDS = {LOAD_DYLIB, ID_DYLIB, 0x80000018, 0x8000001F, 0x80000023}
ZERO_FILL_TYPES = {1, 12, 18}
FAT_MAGICS = {b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf", b"\xbe\xba\xfe\xca", b"\xbf\xba\xfe\xca"}


class PackageError(ValueError):
    """An input violates a format, identity or package contract."""


@dataclasses.dataclass(frozen=True)
class Command:
    kind: int
    offset: int
    data: bytes


@dataclasses.dataclass(frozen=True)
class Section:
    segment: str
    name: str
    address: int
    offset: int
    size: int
    flags: int


@dataclasses.dataclass(frozen=True)
class Image:
    cpu: int
    subtype: int
    file_type: int
    commands_end: int
    commands: tuple[Command, ...]
    sections: tuple[Section, ...]
    dependencies: tuple[str, ...]
    install_names: tuple[str, ...]
    rpaths: tuple[str, ...]
    signatures: tuple[tuple[int, int], ...]
    platforms: tuple[tuple[int, int, int], ...]
    encrypted: bool


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fixed_string(data: bytes) -> str:
    try:
        return data.split(b"\0", 1)[0].decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PackageError("Invalid UTF-8 Mach-O name") from error


def command_string(command: bytes, minimum_size: int) -> str:
    if len(command) < minimum_size:
        raise PackageError("Truncated string-bearing load command")
    offset = struct.unpack_from("<I", command, 8)[0]
    if not minimum_size <= offset < len(command) or b"\0" not in command[offset:]:
        raise PackageError("Invalid load-command string offset or terminator")
    return fixed_string(command[offset:])


def parse_image(data: bytes) -> Image:
    """Parse the supported thin, little-endian 64-bit Mach-O representation."""
    if data[:4] != MAGIC_64 or len(data) < 32:
        raise PackageError("Expected a thin little-endian Mach-O 64 image")
    _, cpu, subtype, file_type, count, size, _, _ = struct.unpack_from("<8I", data)
    if size > len(data) - 32 or count > size // 8:
        raise PackageError("Load commands exceed the image")
    commands_end = 32 + size
    cursor = 32
    commands, sections, dependencies, names, rpaths, signatures, platforms = [], [], [], [], [], [], []
    encrypted = False
    for _ in range(count):
        if cursor + 8 > commands_end:
            raise PackageError("Truncated load command")
        kind, span = struct.unpack_from("<II", data, cursor)
        if span < 8 or span % 8 or cursor + span > commands_end:
            raise PackageError("Invalid Mach-O 64 load-command boundary")
        command = data[cursor:cursor + span]
        commands.append(Command(kind, cursor, command))
        if kind in DYLIB_COMMANDS:
            value = command_string(command, 24)
            (names if kind == ID_DYLIB else dependencies).append(value)
        elif kind == 0x8000001C:
            rpaths.append(command_string(command, 12))
        elif kind == 0x19:
            if span < 72:
                raise PackageError("Truncated segment command")
            segment = fixed_string(command[8:24])
            file_offset, file_size = struct.unpack_from("<QQ", command, 40)
            if file_offset + file_size > len(data):
                raise PackageError("File-backed segment exceeds image: " + segment)
            section_count = struct.unpack_from("<I", command, 64)[0]
            if 72 + section_count * 80 > span:
                raise PackageError("Sections exceed segment command")
            for index in range(section_count):
                offset = 72 + index * 80
                name = fixed_string(command[offset:offset + 16])
                section_segment = fixed_string(command[offset + 16:offset + 32])
                address, section_size, section_offset = struct.unpack_from("<QQI", command, offset + 32)
                flags = struct.unpack_from("<I", command, offset + 64)[0]
                if flags & 0xFF not in ZERO_FILL_TYPES and section_size:
                    if section_offset < commands_end or section_offset + section_size > len(data):
                        raise PackageError("Invalid file-backed section range: " + name)
                sections.append(Section(section_segment, name, address, section_offset, section_size, flags))
        elif kind in (0x21, 0x2C):
            if span < 20:
                raise PackageError("Truncated encryption command")
            cryptoff, cryptsize, cryptid = struct.unpack_from("<III", command, 8)
            if cryptoff + cryptsize > len(data):
                raise PackageError("Encrypted range exceeds image")
            encrypted = encrypted or cryptid != 0
        elif kind == CODE_SIGNATURE:
            if span != 16:
                raise PackageError("Invalid code-signature command size")
            offset, length = struct.unpack_from("<II", command, 8)
            if offset < commands_end or not length or offset + length > len(data):
                raise PackageError("Invalid code-signature range")
            signatures.append((offset, length))
        elif kind == 0x32:
            if span < 24:
                raise PackageError("Truncated platform command")
            platform, minimum, sdk, tool_count = struct.unpack_from("<4I", command, 8)
            if 24 + tool_count * 8 > span:
                raise PackageError("Platform tool list exceeds command")
            platforms.append((platform, minimum, sdk))
        elif kind == 0x25:
            if span < 16:
                raise PackageError("Truncated iOS minimum-version command")
            minimum, sdk = struct.unpack_from("<II", command, 8)
            platforms.append((2, minimum, sdk))
        cursor += span
    if cursor != commands_end:
        raise PackageError("Load-command count and total size disagree")
    return Image(cpu, subtype, file_type, commands_end, tuple(commands), tuple(sections),
                 tuple(dependencies), tuple(names), tuple(rpaths), tuple(signatures), tuple(platforms), encrypted)


def file_sections(image: Image) -> tuple[Section, ...]:
    return tuple(section for section in image.sections
                 if section.flags & 0xFF not in ZERO_FILL_TYPES and section.size)


def require_arm64(image: Image) -> None:
    if image.cpu != ARM64 or image.subtype != 0:
        raise PackageError("Only the verified ARM64 subtype-0 images are supported")
    if image.encrypted:
        raise PackageError("Encrypted images require a separately decrypted artifact")


def rewrite_commands(data: bytes, commands: list[bytes]) -> bytes:
    image = parse_image(data)
    packed = b"".join(commands)
    end = 32 + len(packed)
    first_section = min((section.offset for section in file_sections(image)), default=len(data))
    if end > first_section:
        raise PackageError("Insufficient header space; executable sections would move")
    if end > image.commands_end and any(data[image.commands_end:end]):
        raise PackageError("New load command would overwrite nonzero header data")
    output = bytearray(data)
    output[32:max(end, image.commands_end)] = packed + bytes(max(0, image.commands_end - end))
    struct.pack_into("<II", output, 16, len(commands), len(packed))
    parse_image(bytes(output))
    return bytes(output)


def remove_signature(data: bytes) -> bytes:
    """Remove the signature command and zero its validated unreferenced blob."""
    image = parse_image(data)
    require_arm64(image)
    if not image.signatures:
        return data
    if len(image.signatures) != 1:
        raise PackageError("Multiple embedded signature commands are unsupported")
    for offset, length in image.signatures:
        for section in file_sections(image):
            if offset < section.offset + section.size and section.offset < offset + length:
                raise PackageError("Signature overlaps a declared file-backed section")
    output = bytearray(rewrite_commands(data, [c.data for c in image.commands if c.kind != CODE_SIGNATURE]))
    for offset, length in image.signatures:
        output[offset:offset + length] = bytes(length)
    return bytes(output)


def add_dylib(data: bytes, install_name: str) -> bytes:
    """Add one LC_LOAD_DYLIB without moving any section or changing its content."""
    image = parse_image(data)
    require_arm64(image)
    if image.file_type != 2:
        raise PackageError("A dependency must be added to the main executable (MH_EXECUTE)")
    if install_name in image.dependencies:
        if image.dependencies.count(install_name) != 1:
            raise PackageError("Duplicate dependency")
        return data
    encoded = install_name.encode("utf-8") + b"\0"
    span = (24 + len(encoded) + 7) & ~7
    command = struct.pack("<6I", LOAD_DYLIB, span, 24, 0, 0x10000, 0x10000)
    command += encoded + bytes(span - 24 - len(encoded))
    return rewrite_commands(data, [entry.data for entry in image.commands] + [command])


def prepare_image(data: bytes, install_name: str | None = None) -> bytes:
    """Strip the signature; when install_name is given, also add that dependency."""
    prepared = remove_signature(data)
    return add_dylib(prepared, install_name) if install_name else prepared


def validate_module(data: bytes, install_name: str | None = None) -> Image:
    image = parse_image(data)
    require_arm64(image)
    if image.file_type != 6:
        raise PackageError("Expected an MH_DYLIB module")
    if install_name is not None and image.install_names != (install_name,):
        raise PackageError("Module install name is not " + install_name)
    if len(image.platforms) != 1 or image.platforms[0][0] != 2:
        raise PackageError("Module must target an iOS device, not macOS or a simulator")
    if not any(s.name == "__text" and s.size for s in image.sections):
        raise PackageError("Module has no native executable code")
    if not any(s.name in ("__mod_init_func", "__init_offsets") and s.size for s in image.sections):
        raise PackageError("Module has no dyld initializer section")
    return image


def archive_members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    members = archive.infolist()
    if len({m.filename for m in members}) != len(members):
        raise PackageError("Duplicate ZIP member")
    for member in members:
        path = PurePosixPath(member.filename)
        if not member.filename or path.is_absolute() or ".." in path.parts or "\\" in member.filename:
            raise PackageError("Unsafe ZIP member path")
    return {m.filename: m for m in members}


def app_paths(archive: zipfile.ZipFile, expected_bundle_id: str | None = None) -> tuple[str, str]:
    """Return (app_root, main_executable_member) from the single .app bundle."""
    roots = [n for n in archive.namelist()
             if n.startswith("Payload/") and n.count("/") == 2 and n.endswith(".app/Info.plist")]
    if len(roots) != 1:
        raise PackageError("Expected one main app bundle")
    plist = plistlib.loads(archive.read(roots[0]))
    if expected_bundle_id is not None and plist.get("CFBundleIdentifier") != expected_bundle_id:
        raise PackageError("Unexpected bundle identifier")
    executable = plist.get("CFBundleExecutable")
    if not isinstance(executable, str) or PurePosixPath(executable).name != executable:
        raise PackageError("Invalid main executable name")
    root = roots[0].rsplit("/", 1)[0]
    return root, root + "/" + executable


def signature_resource(name: str) -> bool:
    return "_CodeSignature" in PurePosixPath(name).parts or PurePosixPath(name).name == "embedded.mobileprovision"


def validate_member_metadata(original: zipfile.ZipInfo, candidate: zipfile.ZipInfo) -> None:
    if original.create_system != candidate.create_system or original.external_attr != candidate.external_attr:
        raise PackageError("ZIP file type or permissions changed: " + original.filename)


def native_member(data: bytes) -> bool:
    if data[:4] in FAT_MAGICS:
        raise PackageError("Universal Mach-O member requires explicit slice-aware preparation")
    return data[:4] == MAGIC_64


def section_integrity(before: bytes, after: bytes) -> list[dict]:
    old, new = parse_image(before), parse_image(after)
    if old.sections != new.sections:
        raise PackageError("Mach-O section representation changed")
    result = []
    for section in file_sections(old):
        left = before[section.offset:section.offset + section.size]
        right = after[section.offset:section.offset + section.size]
        if left != right:
            raise PackageError("Executable or data section changed: " + section.segment + "/" + section.name)
        result.append({"segment": section.segment, "name": section.name, "file_offset": section.offset,
                       "size": section.size, "sha256": digest(left)})
    return result


def added_member(name: str, executable: bool = False) -> zipfile.ZipInfo:
    entry = zipfile.ZipInfo(name)
    entry.create_system = 3
    entry.external_attr = (0o100755 if executable else 0o100644) << 16
    entry.compress_type = zipfile.ZIP_DEFLATED
    return entry


def build_package(source: Path, module: Path, output: Path, *, install_name: str | None = None,
                  member_name: str | None = None, expected_bundle_id: str | None = None,
                  strip_other_signatures: bool = True) -> dict:
    """Inject `module` into `source` IPA; only the main executable is modified."""
    if source.resolve() == output.resolve() or module.resolve() == output.resolve():
        raise PackageError("Output would overwrite an input")
    if output.exists():
        raise PackageError("Output already exists; choose a new path")
    library = module.read_bytes()
    module_image = validate_module(library, install_name)
    if install_name is None:
        install_name = module_image.install_names[0]
    if member_name is None:
        member_name = PurePosixPath(install_name).name
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as original:
        members = archive_members(original)
        root, main = app_paths(original, expected_bundle_id)
        library_path = root + "/Frameworks/" + member_name
        if library_path in members:
            raise PackageError("Source already contains the module")
        with tempfile.TemporaryDirectory(prefix="ipa-package-", dir=output.parent) as tmp:
            candidate = Path(tmp) / "candidate.ipa"
            with zipfile.ZipFile(candidate, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as built:
                built.comment = original.comment
                for name, info in members.items():
                    data = original.read(info)
                    if name == main:
                        data = prepare_image(data, install_name)
                    elif strip_other_signatures and native_member(data):
                        data = prepare_image(data, None)
                    entry = copy.copy(info)
                    built.writestr(entry, data)
                    entry.external_attr = info.external_attr
                built.writestr(added_member(library_path, executable=True), prepare_image(library, None))
            report = validate_package(source, candidate, module, install_name=install_name,
                                      member_name=member_name, expected_bundle_id=expected_bundle_id,
                                      strip_other_signatures=strip_other_signatures)
            candidate.replace(output)
    report["output"] = str(output)
    (output.with_suffix(".integrity.json")).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def validate_package(source: Path, candidate: Path, module: Path, *, install_name: str,
                     member_name: str, expected_bundle_id: str | None = None,
                     strip_other_signatures: bool = True) -> dict:
    library = module.read_bytes()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(candidate) as built:
        old_members, new_members = archive_members(original), archive_members(built)
        root, main = app_paths(original, expected_bundle_id)
        if app_paths(built, expected_bundle_id) != (root, main):
            raise PackageError("App paths changed")
        library_path = root + "/Frameworks/" + member_name
        if set(new_members) != set(old_members) | {library_path}:
            raise PackageError("Unexpected ZIP additions or removals")
        if built.read(library_path) != prepare_image(library, None):
            raise PackageError("Packaged library differs from the compiled artifact")
        images, unchanged = [], []
        for name, info in old_members.items():
            before, after = original.read(info), built.read(name)
            if name == main:
                if after != prepare_image(before, install_name):
                    raise PackageError("Unexpected main-executable modification")
                if parse_image(after).signatures:
                    raise PackageError("Stale signature retained on main executable")
                images.append({"member": name, "before_sha256": digest(before), "after_sha256": digest(after),
                               "sections": section_integrity(before, prepare_image(before, None)),
                               "dependency_added": install_name})
            elif strip_other_signatures and native_member(before):
                if after != prepare_image(before, None):
                    raise PackageError("Unexpected binary modification: " + name)
            else:
                if before != after:
                    raise PackageError("Unintended resource change: " + name)
                unchanged.append(name)
        main_image = parse_image(built.read(main))
        if main_image.dependencies.count(install_name) != 1:
            raise PackageError("Main executable must load the module exactly once")
        rpath_root = install_name.split("/", 1)[0]
        if rpath_root == "@rpath" and "@executable_path/Frameworks" not in main_image.rpaths:
            raise PackageError("Main executable lacks an rpath that resolves @rpath")
        if built.testzip() is not None:
            raise PackageError("ZIP CRC failure")
    return {"result": "passed", "source_sha256": file_digest(source),
            "candidate_sha256": file_digest(candidate), "candidate_size": candidate.stat().st_size,
            "module_sha256": digest(library), "install_name": install_name, "module_member": member_name,
            "modified_images": images, "unchanged_member_count": len(unchanged),
            "signing_state": "unsigned; re-sign the app and the added dylib before installing",
            "runtime_verified": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject a dylib into an IPA (main executable only).")
    parser.add_argument("action", choices=("build", "verify"), nargs="?", default="build")
    parser.add_argument("--source", type=Path, required=True, help="input .ipa")
    parser.add_argument("--module", type=Path, required=True, help="dylib to inject")
    parser.add_argument("--output", type=Path, required=True, help="output .ipa (must not exist)")
    parser.add_argument("--install-name", default=None, help="dependency path to add; default = the module's own LC_ID_DYLIB")
    parser.add_argument("--member-name", default=None, help="file name under <App>.app/Frameworks/; default from install name")
    parser.add_argument("--expected-bundle-id", default=None, help="optional CFBundleIdentifier guard")
    parser.add_argument("--keep-other-signatures", action="store_true", help="do not strip signatures from other embedded Mach-O members")
    args = parser.parse_args()
    kwargs = dict(install_name=args.install_name, member_name=args.member_name,
                  expected_bundle_id=args.expected_bundle_id, strip_other_signatures=not args.keep_other_signatures)
    if args.action == "verify":
        report = validate_package(args.source, args.output, args.module, **kwargs)
    else:
        report = build_package(args.source, args.module, args.output, **kwargs)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
