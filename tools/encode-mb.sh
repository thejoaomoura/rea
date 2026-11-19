#!/usr/bin/env bash
# Average motion-blur sub-frames (from export-mb.cjs) into the final MP4 (or a GIF when OUT ends in .gif).
# usage: tools/encode-mb.sh SUBFRAMES_DIR AUDIO|- OUT [FPS] [SAMPLES] [START_FRAME]
set -euo pipefail
DIR=$1; AUD=$2; OUT=$3; F=${4:-30}; K=${5:-5}; S0=${6:-0}
MIX="tmix=frames=$K,select='eq(mod(n\,$K)\,$((K-1)))',setpts=N/($F*TB)"
if [[ "$OUT" == *.gif ]]; then
  ffmpeg -v error -y -start_number $((S0*K)) -framerate $((F*K)) -i "$DIR/s%06d.jpg" -vf "$MIX,scale=360:-1:flags=lanczos,split[x][y];[x]palettegen=max_colors=128[p];[y][p]paletteuse=dither=bayer:bayer_scale=4" -r "$F" "$OUT"
else
  ffmpeg -v error -y -start_number $((S0*K)) -framerate $((F*K)) -i "$DIR/s%06d.jpg" -i "$AUD" -vf "$MIX" -r "$F" -c:v libx264 -preset slow -crf 20 -maxrate 10M -bufsize 20M \
    -tune grain -pix_fmt yuv420p -profile:v high -c:a aac -b:a 256k -shortest -movflags +faststart "$OUT"
fi
ls -la "$OUT"
