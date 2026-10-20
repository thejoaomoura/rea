# iOS cross-compile toolchain (zig cc → aarch64-ios) — restore guide

How to rebuild the `.cache/.../ios-mod/toolchain` used to compile the injected
dylibs (REAObservers, pool libloader helpers, probes) after a machine reformat.
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
