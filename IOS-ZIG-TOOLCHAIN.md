# iOS cross-compile toolchain (zig cc → aarch64-ios) — restore guide

This document is the index of the whole **.ipa reverse-engineering framework**
used in this workspace: the cross-compile toolchain (below), plus the acquisition,
static-analysis, build/inject/package and byte-patch tooling catalogued under
"Framework components" at the end. Primary purpose: rebuild the
`.cache/.../ios-mod/toolchain` used to compile the injected dylibs (REAObservers,
ZyonGo, pool libloader helpers, probes) after a machine reformat, and locate every
other piece an analysis depends on.
Everything here lives under `.cache/`, which is **gitignored** — it is NOT in the
repo and must be re-downloaded. This document is the recipe.

## What the toolchain is

| Component | Version | Purpose |
|---|---|---|
| Zig | `0.14.1` (`x86_64-linux`) | provides `zig cc`, a clang that cross-compiles to `aarch64-ios` without Xcode |
| iPhoneOS SDK | `iPhoneOS15.6.sdk` (theos/sdks, commit `0222fd5413cf4b9af096f37b4621afa2688572f7`) | iOS headers + tbd stubs to link against |
| ldid | `v2.1.5-procursus7` (`ldid_linux_x86_64`) | ad-hoc / entitlement code signing of the built dylib |

Host: runs under WSL (Ubuntu) on Windows, or any x86_64 Linux. The Zig binary is a
static x86_64 ELF — no system deps.

## Target layout

Restore into exactly this path (other build scripts hardcode it):

```
.cache/pokemongo-analysis-20261019/ios-mod/toolchain/
├── zig-x86_64-linux-0.14.1/zig
├── sdks/iPhoneOS15.6.sdk/
└── ldid_linux_x86_64
```

From the repo root, in WSL that is `/mnt/c/Projetos/rea/.cache/pokemongo-analysis-20261019/ios-mod/toolchain`.

## 1. Zig 0.14.1

```bash
TC="$(git rev-parse --show-toplevel)/.cache/pokemongo-analysis-20261019/ios-mod/toolchain"
mkdir -p "$TC" && cd "$TC"
curl -fLO https://ziglang.org/download/0.14.1/zig-x86_64-linux-0.14.1.tar.xz
tar xf zig-x86_64-linux-0.14.1.tar.xz
./zig-x86_64-linux-0.14.1/zig version   # must print 0.14.1
```

(If ziglang.org is down, 0.14.1 is mirrored at
`https://github.com/ziglang/zig/releases` — but the official site is the canonical host.)

## 2. iPhoneOS 15.6 SDK (theos/sdks, pinned commit)

Only one SDK is needed; the full repo is large, so grab just the pinned commit and
copy the single SDK out:

```bash
cd "$TC"
git clone --filter=blob:none --no-checkout https://github.com/theos/sdks.git sdks-src
cd sdks-src
git checkout 0222fd5413cf4b9af096f37b4621afa2688572f7 -- iPhoneOS15.6.sdk
mkdir -p "$TC/sdks"
cp -a iPhoneOS15.6.sdk "$TC/sdks/"
cd "$TC" && rm -rf sdks-src
ls "$TC/sdks/iPhoneOS15.6.sdk/System/Library/Frameworks" | head   # sanity check
```

Fallback (no sparse checkout): `curl -fLO https://github.com/theos/sdks/archive/master.zip`,
unzip, copy `sdks-master/iPhoneOS15.6.sdk` into `$TC/sdks/`. The SDKs are subject to
Apple's Xcode SDK agreement; keep for local use.

## 3. ldid (code signing)

```bash
cd "$TC"
curl -fLO https://github.com/ProcursusTeam/ldid/releases/download/v2.1.5-procursus7/ldid_linux_x86_64
chmod +x ldid_linux_x86_64
./ldid_linux_x86_64 2>&1 | head -1   # prints usage
```

## 4. Build + sign a dylib

Pattern used for every REA dylib (compile each `.c`/`.m`, then link, then sign).
`$NATIVE` = the source dir (e.g. `.cache/<target>-analysis-*/native`),
`$OUT` = output `.dylib`:

```bash
ZIG="$TC/zig-x86_64-linux-0.14.1/zig"
SDK="$TC/sdks/iPhoneOS15.6.sdk"
NATIVE=/mnt/c/Projetos/rea/.cache/squadbusters-analysis-20261020/native
OUT=/mnt/c/Projetos/rea/.cache/squadbusters-analysis-20261020/build/REAObservers.dylib
mkdir -p "$(dirname "$OUT")/objects"

CFLAGS="-target aarch64-ios.14.0 -isysroot $SDK \
  -iframework $SDK/System/Library/Frameworks -L $SDK/usr/lib \
  -isystem $SDK/usr/include -I $NATIVE -O2 -fvisibility=hidden -Wall -Wextra -Werror"

for src in REABootstrap.c REAProjection.c READiagnostics.m REAMemory.m REARuntime.m REAEntry.m; do
  obj="$(dirname "$OUT")/objects/${src%.*}.o"
  "$ZIG" cc $CFLAGS -c "$NATIVE/$src" -o "$obj"
done

"$ZIG" cc -target aarch64-ios.14.0 -isysroot "$SDK" -shared \
  -install_name @executable_path/Frameworks/REAObservers.dylib \
  -framework Foundation -framework UIKit -framework QuartzCore -framework CoreGraphics \
  -o "$OUT" "$(dirname "$OUT")"/objects/*.o

"$TC/ldid_linux_x86_64" -S "$OUT"          # ad-hoc sign (or -S<entitlements.plist>)
```

Use `ZIG_GLOBAL_CACHE_DIR` / `ZIG_LOCAL_CACHE_DIR` env vars to pin Zig's cache off
the default `$HOME` if building in a sandbox.

## 5. Verify

```bash
"$ZIG" cc -target aarch64-ios.14.0 -isysroot "$SDK" -E -x c /dev/null >/dev/null && echo "sdk+zig OK"
file "$OUT"        # Mach-O 64-bit dynamically linked shared library arm64
```

## Notes

- Pinning: Zig `0.14.1` and SDK commit `0222fd5` are the exact versions the existing
  builds used. Newer Zig may change `zig cc` flags; stay on 0.14.1 to reproduce.
- The dylib is injected into a decrypted IPA (`LC_LOAD_DYLIB` via `insert_dylib`/eSign),
  then the whole app bundle is re-signed (eSign / Sideloadly) for the device.
- Nothing here needs Xcode or macOS; it is a Linux/WSL cross toolchain.

---

# Framework components (.ipa reverse engineering)

The complete pipeline, in the order a target moves through it. Everything under
`.cache/` is **gitignored** (local workspace only) — paths below are where each
piece lives in the workspace, not in the repo. The committed, portable parts are
the REA skill and this document.

## 1. Acquisition (get the .ipa)

| Tool | Where / source | Role |
|---|---|---|
| `ipatool` (majd/ipatool) | external CLI | download store IPA by bundle id; result is **FairPlay-encrypted** (`cryptid=1`) |
| iMazing | external GUI | same, via Apple ID purchase API |
| frida-ios-dump / bagbak | external, needs jailbroken device + Frida | dump the **decrypted** app (`cryptid=0`) — the only form usable for static patch/analysis |
| decrypt.download / archive.org mirrors | web | pre-decrypted community dumps |
| `.cache/pokemongo-analysis-20261019/download_ipa.py`, `inspect_ipa.py` | workspace | scripted acquisition + first IPA inventory |

## 2. Static analysis engines

| Tool | Where / source | Role |
|---|---|---|
| REA skill | `skills/reverse-engineer-anything/` (committed) + its `references/*.md` | routing + method for native/managed/JS/firmware/IPA targets; see `references/ios-mobsf-ipsw.md` |
| `ios-license-bypass` skill | `skills/ios-license-bypass/` (committed) | iOS license/gate analysis workflow |
| Capstone 5.0.7 | pip (Python 3.13) | ARM64 disassembly |
| Unicorn 2.1.4 | pip (Python 3.13) | scalar ARM64 emulation of candidate routines |
| Mach-O/ZIP parsers | `.cache/duck-survival-20261019/macho_reader_base.py`, `macho_analysis_reader.py`; per-project `inspect_*.py` | header/load-command/section/symbol/function-start parsing, IPA member inventory |
| MobSF (dockerless) / `ipsw` / XMachOViewer | external, per REA `references/ios-mobsf-ipsw.md` | IPA security assessment, ObjC/Swift class dump, Mach-O viewer |

## 3. Cross-compile toolchain

zig `0.14.1` + iPhoneOS15.6 SDK + ldid `v2.1.5-procursus7` — full restore recipe
and build/sign command in the sections above. Location
`.cache/pokemongo-analysis-20261019/ios-mod/toolchain/`.

## 4. Injected runtime modules (sources)

| Module | Where | Role |
|---|---|---|
| REAObservers | `.cache/brawlstars-analysis-20261020/native/` (Brawl); `.cache/squadbusters-analysis-20261020/native/` (Squad retarget) | ObjC runtime observers → JSONL diagnostics; `vm_read_overwrite` reads only, no game writes |
| ZyonGo | `.cache/pokemongo-analysis-20261019/ios-mod/` | native module + static detours, ImGui toolbox |

## 5. Build / inject / package

| Tool | Where | Role |
|---|---|---|
| `build_native.py` | `.cache/pokemongo-analysis-20261019/ios-mod/` | compile a dylib with the zig toolchain + verify Mach-O identity (per-target `*.build.json`) |
| `static_hooks.py` | same | prepare static ARM64 entry detours (RX relays + separate RW table) |
| `package_ipa.py` | same | repackage an unsigned IPA with the compiled module, verifying every ZIP member/CRC |
| `insert_dylib` / `optool` / eSign "inject dylib" | external | add `LC_LOAD_DYLIB` for the injected module |
| eSign / Sideloadly / AltStore / `ldid` | external + toolchain | re-sign app + embedded dylib(s) + frameworks for the device (see signing note above) |

## 6. Byte-level patching (loader / in-binary)

| Script | Where | Role |
|---|---|---|
| `patch_local_session.py` | `.cache/pool-local-session-trial-20261019/` | ARM64 call-redirect + code-cave patches in a decrypted loader; CRC/member-verified repack |
| `patch_runtime_lifecycle.py`, `patch_runtime_persist.py` | `.cache/pool-runtime-lifecycle-trial-20261019/` | hook install/persistence patches (ObjC `method_setImplementation` guard/reinstall) |
| `inspect_lifecycle.py`, `inspect_proof_contract.py` | pool projects | read-only ARM64 traces feeding the patch scripts |
| `trace_gameplay_offsets.py`, `trace_menu_hooks.py`, `verify_static_projection.py`, `runtime_projection.py` | `.cache/brawlstars-analysis-20261020/` | resolve/verify gameplay offsets, menu hooks and world→screen projection |

## 7. Per-target workspace layout

Each target is a dated dir under `.cache/`:

```
.cache/<target>-analysis-YYYYMMDD/
├── dump/           decrypted IPA + extracted native images (image.bin) + Info.plist
├── analysis/       offset/symbol/chain JSON (aim_*.json, scene_*.json, …) + probe scripts
├── native/         injected-module ObjC/C sources (REAObservers, …)
├── build/          compiled .dylib + *.build.json/*.compiler.json + verification.json
├── ANALYSIS.md     findings, identity table (SHA-256), tool versions
└── patch-manifest.json   byte offsets/originals/replacements per patch (loader projects)
```

Known targets: `brawlstars-analysis-20261020` (`com.supercell.laser`),
`squadbusters-analysis-20261020` (`com.supercell.squad`),
`pool-*-trial-20261019` (`pool.app`/8 Ball Pool),
`duck-survival-20261019` (`com.us.ducksurvival.ios`),
`pokemongo-analysis-20261019` (ZyonGo / Pokémon GO).
