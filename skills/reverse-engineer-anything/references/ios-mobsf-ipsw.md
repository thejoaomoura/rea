# IPA and Mach-O analysis with MobSF, ipsw, and XMachOViewer

Use this route when the user requests iOS package security analysis or Mach-O
inspection of an IPA. These are external tools invoked through the agent's
shell or desktop interface, not REA MCP tools or selectable REA native providers.
Do not invent provider IDs for them. Ordinary archive inventory still uses REA.

## Select the evidence source

1. Inventory the supplied IPA with `open_binary` and `inspect_artifact`.
   Preserve its absolute path and SHA-256. Use `extract_artifact` when files
   are needed; retain the returned extraction directory and member identities.
2. For package security assessment, use an existing local MobSF instance.
   Upload only the caller-selected IPA. MobSF stores the upload and scan in its
   own workspace/database; static scanning does not launch the iOS app.
3. For focused Mach-O inspection, or when MobSF is unavailable or cannot analyze
   the target on this host, use `ipsw` on the extracted executable. Preserve the
   MobSF failure reason and state which requested facets remain unanswered.
   Authentication errors need a credential repair; malformed input needs input
   correction. Neither proves the package unsupported.
4. Read `Payload/<app>.app/Info.plist` with `inspect_plist` and resolve
   `CFBundleExecutable` within that bundle. Do not guess the executable from
   the app name. Inspect nested frameworks/extensions separately as requested.
   If plist inspection is unavailable, use another format-aware plist reader;
   keep executable identity unknown until established.
5. If ipsw fails on the requested facet, preserve its command, version, stderr,
   and exit code, then use XMachOViewer for visual inspection of the same
   extracted Mach-O. Keep the member hash and selected architecture aligned.
   A successful GUI inspection does not erase the failed facet or prove that
   ObjC/Swift metadata recovery succeeded.

## MobSF without Docker

`opensecurity/mobile-security-framework-mobsf:latest` identifies a Docker image,
not a native executable. For a Docker-free service, use the official
[MobSF source installation](https://github.com/MobSF/Mobile-Security-Framework-MobSF)
and its [installation documentation](https://mobsf.github.io/docs/).
Record the checked-out release/commit; do not equate it with a floating image tag.

Reuse an existing installation first. Check the selected release's prerequisites
before installing: its Python constraint and native dependencies can change.
REA setup does not install MobSF, Python, Java, OpenSSL, build tools, Scoop, or
ipsw. Keep provider installation separate from MCP registration. When running
Python on Windows, use the `py` launcher with the required version selected.

On a provisioned Windows source installation, start the service from its source
directory with `run.bat 127.0.0.1:8000`. Keep it bound to loopback. Do not start a
second service if the supplied local endpoint is already available. Obtain the
API key from that installation's API page; never include it in reports, command
transcripts, or committed files. Do not upload the IPA to a public service.

The following calls run in **PowerShell 7** (`-Form` is unavailable in Windows
PowerShell 5.1). Set `MOBSF_API_KEY` in the current process using the existing
credential mechanism before running them. This is a shell variable for these
calls, not a REA configuration setting. Replace the IPA path with the user's
actual input. The service must use synchronous scanning for this example.

```powershell
$ErrorActionPreference = 'Stop'
$mobsfUrl = 'http://127.0.0.1:8000'
$ipaPath = (Resolve-Path -LiteralPath 'C:\analysis\App.ipa').Path
if (-not $env:MOBSF_API_KEY) { throw 'MOBSF_API_KEY is missing' }
$mobsfHeaders = @{ Authorization = $env:MOBSF_API_KEY }
$ipaSha256 = (Get-FileHash -LiteralPath $ipaPath -Algorithm SHA256).Hash
$upload = Invoke-RestMethod -Method Post -Uri "$mobsfUrl/api/v1/upload" `
  -Headers $mobsfHeaders -Form @{ file = Get-Item -LiteralPath $ipaPath }
if ($upload.error -or $upload.hash -notmatch '^[a-fA-F0-9]{32}$') {
  throw "MobSF upload failed: $($upload | ConvertTo-Json -Depth 100 -Compress)"
}
$scan = Invoke-RestMethod -Method Post -Uri "$mobsfUrl/api/v1/scan" `
  -Headers $mobsfHeaders -Body @{ hash = $upload.hash }
if ($scan.error) {
  throw "MobSF scan failed: $($scan | ConvertTo-Json -Depth 100 -Compress)"
}
$report = Invoke-RestMethod -Method Post -Uri "$mobsfUrl/api/v1/report_json" `
  -Headers $mobsfHeaders -Body @{ hash = $upload.hash }
if ($report.error) {
  throw "MobSF report failed: $($report | ConvertTo-Json -Depth 100 -Compress)"
}
@{ path = $ipaPath; sha256 = $ipaSha256; endpoint = $mobsfUrl;
   upload = $upload; scan = $scan; report = $report } |
  ConvertTo-Json -Depth 100
```

Use the hash returned by upload as MobSF's scan identifier, not as a replacement
for REA's SHA-256 identity. With asynchronous scanning enabled, inspect the
instance's `/api/v1/tasks` and `/api/v1/scan_logs` using that hash and retrieve
the report only after completion. A queued scan or missing report is not a
completed analysis. Preserve HTTP status and the provider's diagnostic on
failure, excluding authentication credentials.

## Windows fallback with blacktop/ipsw

Check `Get-Command ipsw` and `ipsw version` first. When installation is requested
and Scoop already exists, inspect `scoop bucket list` and `scoop list`; run only
the missing steps below. If the `blacktop` bucket exists with a different source,
report the conflict instead of replacing it.

```powershell
scoop bucket add blacktop https://github.com/blacktop/scoop-bucket.git
scoop install blacktop/ipsw
ipsw version
```

Pass the extracted Mach-O file, **not the IPA ZIP**, to the following commands.
Replace the path with the executable established from the plist and inventory.
Keep each command's stdout, stderr, and exit code as external evidence.

```powershell
$machoPath = 'C:\analysis\extracted\Payload\App.app\AppExecutable'
Get-FileHash -LiteralPath $machoPath -Algorithm SHA256
ipsw macho info $machoPath
ipsw macho info $machoPath --json
ipsw macho info $machoPath --sig
```

Read `ipsw macho info --help` for the installed version's supported flags. Select
`--arch` only after inspecting the reported slices, and preserve the selected
architecture. If a flag or facet is unsupported, report that limitation rather
than substituting empty successful output. Use other `ipsw macho` subcommands
only when their help and the analyst's question justify them.

### Objective-C and experimental Swift metadata

Use `ipsw class-dump` for classes, method declarations, categories, and protocols.
It accepts standalone Mach-O files as well as images in a dyld shared cache.
Check the installed command's help before selecting filters or output options:

```powershell
ipsw class-dump --help
ipsw class-dump $machoPath
ipsw swift-dump --help
ipsw swift-dump $machoPath
```

For universal binaries, add `--arch` with the previously observed slice to avoid
an interactive architecture picker. Use `--class`, `--proto`, or `--cat` for a
requested ObjC subset. Header export uses `--headers -o` with a caller-selected
output directory. Method declarations are metadata, not recovered method bodies.

Treat Swift dumping as experimental: preserve parsing failures and incomplete
coverage, especially for complex generics. Empty output does not prove that no
Swift types exist. For system frameworks backed by a dyld shared cache, inspect
the original cache and exact dylib install path; an extracted dylib may depend
on metadata elsewhere in that cache. Do not confuse this with an IPA executable.

`ipsw` supplies binary inspection, not an equivalent MobSF vulnerability report
or REA decompiler. Code-signature metadata is not proof of platform trust. An
encrypted Mach-O (nonzero `cryptid` in its encryption load command) can expose
headers and metadata while its protected code remains unavailable; neither
tool automatically recovers decrypted application code. Report unsupported
facets and distinguish static observations from inferred behavior.

## Visual fallback with XMachOViewer (portable Win64)

Use [XMachOViewer](https://github.com/horsicq/XMachOViewer) when ipsw cannot inspect
the requested structure, or when the user requests a GUI. From the official
[releases](https://github.com/horsicq/XMachOViewer/releases), select the Win64
portable ZIP (for example, `xmachoviewer_win64_portable_0.04.zip`), record its
release and download URL, and extract it to a dedicated tools directory. Reuse
an existing copy when available. Keep the complete portable folder and its
bundled libraries; no installer or global PATH change is required.

Launch the GUI from that folder and open the extracted Mach-O through its file
picker. Inspect headers, load commands, sections, symbols, and disassembly for
the selected architecture. Preserve relevant addresses/file offsets and exports
or screenshots together with the input hash and viewer version. Check that the
chosen build supports the target architecture before interpreting disassembly.

Use an available desktop-control tool for the actual GUI interaction. If desktop
access is unavailable, provide the exact file to open and the inspection steps,
and report visual verification as pending. Merely launching the viewer is not a
successful analysis. Do not execute the inspected binary or edit its bytes.
The GUI fallback does not imply equivalent ObjC class dumps, Swift recovery,
MobSF findings, or decryption of protected code.

## Evidence and verification

Report the IPA identity, exact member path and hash, provider version, command or
API endpoint, selected architecture, findings, failures, and remaining unknowns.
External output is not automatically an authenticated REA Evidence record; cite
it as external evidence alongside the REA inventory that identifies the member.

Verify a real provider claim with a caller-supplied or owned fixture: complete
upload/scan/report for MobSF, and parse an extracted Mach-O with the installed
Windows ipsw. For the GUI fallback, open that same member and inspect the requested
views. Installation checks and mocked API responses alone do not establish IPA
analysis support. No real MobSF/ipsw/XMachOViewer workflow was verified by adding
this guide.

Sources: [MobSF API implementation](https://github.com/MobSF/Mobile-Security-Framework-MobSF/blob/master/mobsf/MobSF/views/api/api_static_analysis.py),
[ipsw installation](https://blacktop.github.io/ipsw/docs/getting-started/installation/),
[Mach-O inspection](https://blacktop.github.io/ipsw/docs/guides/macho/),
[ObjC and Swift dumping](https://github.com/blacktop/ipsw-skill/blob/main/ipsw/references/class-dump.md),
[XMachOViewer capabilities](https://github.com/horsicq/XMachOViewer).
