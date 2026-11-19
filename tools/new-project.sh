#!/usr/bin/env bash
# Create a lyric project from the template.
# usage: tools/new-project.sh DEST song.mp3 START_S DURATION_S [FADE_OUT_S]
set -euo pipefail
K=$(cd "$(dirname "$0")/.." && pwd); D=$1; SONG=$2; SS=$3; DU=$4; FO=${5:-2.5}
mkdir -p "$D/assets/photos"; cp "$K/template/index.html" "$D/index.html"
curl -s -o "$D/assets/gsap.min.js" https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js
ST=$(python3 -c "print(max(0,$DU-$FO))")
ffmpeg -v error -y -ss "$SS" -t "$DU" -i "$SONG" -af "afade=t=in:d=0.3,afade=t=out:st=$ST:d=$FO" -c:a libmp3lame -b:a 192k "$D/assets/chorus.mp3"
echo "project at $D  (set T0=$SS, DUR=$DU in index.html; run tools/fonts.sh next)"
