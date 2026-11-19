#!/usr/bin/env bash
# Idempotent toolchain for @moura'slyrics lyric videos. Safe to run on every new container.
set -u
SK=$HOME/.claude/skills; mkdir -p "$SK"
KIT=$(cd "$(dirname "$0")/.." && pwd)
# kit skill
mkdir -p "$SK/moura-lyrics" && cp "$KIT/skill/SKILL.md" "$SK/moura-lyrics/SKILL.md"
# bang-motion skill
if [ ! -f "$SK/bang-motion/SKILL.md" ]; then
  rm -rf /tmp/bm && git clone -q --depth 1 https://github.com/bangtutorial/bang-motion /tmp/bm && rm -rf /tmp/bm/.git && cp -r /tmp/bm "$SK/bang-motion"
fi
# community motion/typography skills
add(){ [ -d "$SK/$2" ] || (cd /tmp && npx -y skills add "$1" -g -y -a claude-code >/dev/null 2>&1) || true; }
add remotion-dev/skills remotion-best-practices
add greensock/gsap-skills gsap-core
add iart-ai/kinetic-typography-skills kinetic-typography
add lottiefiles/motion-design-skill motion-design
add kylezantos/design-motion-principles design-motion-principles
add shadcn-labs/snapcn@remotion-kinetic-typography remotion-kinetic-typography
# CLIs / libs
command -v remotion >/dev/null 2>&1 || npm i -g @remotion/cli >/dev/null 2>&1 || true
python3 -c "import scipy,potrace" 2>/dev/null || pip install -q scipy potracer >/dev/null 2>&1 || true
echo "moura-lyrics toolchain ready"
