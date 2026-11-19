#!/usr/bin/env bash
# Transcribe a song with Groq Whisper (word + segment timestamps).
# usage: tools/transcribe.sh song.mp3 out.json [start_s duration_s] [prompt]
# The Groq key is injected by the environment proxy (network secret for api.groq.com);
# GROQ_API_KEY is used if present, otherwise a placeholder the proxy overwrites.
set -euo pipefail
IN=$1; OUT=$2; SS=${3:-}; DU=${4:-}; PROMPT=${5:-}
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
if [ -n "$SS" ]; then ffmpeg -v error -y -ss "$SS" -t "$DU" -i "$IN" -ac 1 -ar 16000 -b:a 48k "$TMP/a.mp3"
else ffmpeg -v error -y -i "$IN" -ac 1 -ar 16000 -b:a 48k "$TMP/a.mp3"; fi
args=(-F file=@"$TMP/a.mp3" -F model=whisper-large-v3 -F response_format=verbose_json
      -F "timestamp_granularities[]=word" -F "timestamp_granularities[]=segment" -F language=en)
[ -n "$PROMPT" ] && args+=(-F "prompt=$PROMPT")
curl -sS https://api.groq.com/openai/v1/audio/transcriptions -H "Authorization: Bearer ${GROQ_API_KEY:-proxy-injected}" "${args[@]}" > "$OUT"
python3 - "$OUT" "${SS:-0}" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]));off=float(sys.argv[2])
if 'error' in d: print(d['error']);sys.exit(1)
for s in d.get('segments',[]): print(f"{s['start']+off:7.2f}-{s['end']+off:7.2f} {s['text']}")
PY
