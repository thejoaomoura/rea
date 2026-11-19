# @moura'slyrics — lyric video kit

Kinetic-typography lyric videos (9:16) built as deterministic HTML + GSAP and rendered frame by frame to MP4.
The standard (workflow, rules, pitfalls) lives in [`skill/SKILL.md`](skill/SKILL.md).

| Path | What |
|---|---|
| `template/index.html` | engine: camera rig, text/entry vocabulary, motion blur, photo frames, particles, export API |
| `tools/` | `transcribe.sh` (Groq Whisper), `analyze.py` (words, sustained notes, tempo, drops), `new-project.sh`, `fonts.sh`, `contact.sh` + `snap.cjs` (QC sheets), `export.cjs` (resumable frame export), `encode.sh`, `seg.py`/`trace.py` (vectorize public-domain art) |
| `references/` | full source of finished videos (She Wolf, Elastic Heart) — media not included |
| `setup/install.sh` | idempotent toolchain (skills, Remotion CLI, Python libs) |

Media (audio, photos, fonts, frames, MP4) is never committed.
