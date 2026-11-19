#!/usr/bin/env bash
# Snapshot key seconds of a served project into one contact sheet.
# usage: tools/contact.sh URL OUT_DIR COLS t1 t2 ...   (URL e.g. http://127.0.0.1:5178/index.html?clean=1)
set -euo pipefail
K=$(cd "$(dirname "$0")" && pwd); URL=$1; O=$2; C=$3; shift 3; mkdir -p "$O"; rm -f "$O"/s_*.png
TS=(); for t in "$@"; do TS+=("$(printf '%06.2f' "$t")"); done
NODE_PATH=$(npm root -g) node "$K/snap.cjs" "$URL" "$O" "${TS[@]}"
ffmpeg -v error -y -pattern_type glob -i "$O/s_*.png" -vf "scale=240:-1,tile=${C}x$(( ($# + C - 1) / C ))" "$O/sheet.png"; echo "$O/sheet.png"
