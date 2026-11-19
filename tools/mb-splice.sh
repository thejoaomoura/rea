#!/usr/bin/env bash
# Fix motion-blur strobing on a fast segment: re-render frames [A,B) with more samples and overlay them on the final MP4.
# usage: tools/mb-splice.sh URL FINAL.mp4 A_FRAME B_FRAME [SAMPLES=12] [FPS=30]
set -euo pipefail
T=$(cd "$(dirname "$0")" && pwd); URL=$1; MP4=$2; A=$3; B=$4; K=${5:-12}; F=${6:-30}
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
START=$A END=$B SAMPLES=$K WORKERS=${WORKERS:-4} NODE_PATH=$(npm root -g) node "$T/export-mb.cjs" "$URL" "$W/sub" "$F" | tail -1
ffmpeg -v error -y -start_number $((A*K)) -framerate $((F*K)) -i "$W/sub/s%06d.jpg" -vf "tmix=frames=$K,select='eq(mod(n\,$K)\,$((K-1)))',setpts=N/($F*TB)" -r "$F" -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p "$W/seg.mp4"
ffmpeg -v error -y -i "$MP4" -i "$W/seg.mp4" -filter_complex "[1:v]setpts=PTS+($A/$F)/TB[s];[0:v][s]overlay=eof_action=pass:enable='between(t,$A/$F,($B-0.5)/$F)'" \
  -c:v libx264 -preset slow -crf 20 -maxrate 10M -bufsize 20M -tune grain -pix_fmt yuv420p -profile:v high -c:a copy -movflags +faststart "$W/out.mp4"
mv "$W/out.mp4" "$MP4"; ls -la "$MP4"
