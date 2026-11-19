#!/usr/bin/env bash
# Frames (jpg) + audio -> MP4 for social (9:16). Bitrate capped: animated grain explodes CRF-only files.
# usage: tools/encode.sh FRAMES_DIR AUDIO OUT.mp4 [FPS]
set -euo pipefail
ffmpeg -v error -y -framerate "${4:-30}" -i "$1/f%05d.jpg" -i "$2" -c:v libx264 -preset slow -crf 20 -maxrate 10M -bufsize 20M \
  -tune grain -pix_fmt yuv420p -profile:v high -c:a aac -b:a 256k -shortest -movflags +faststart "$3"
ffprobe -v error -show_entries format=duration,size -of csv=p=0 "$3"
