#!/usr/bin/env bash
# Vendor Google Fonts locally (latin subset) -> assets/fonts + assets/fonts.css
# usage: tools/fonts.sh PROJECT_DIR "family=Anybody:ital,wdth,wght@0,50..150,100..900&family=DM+Mono:wght@400;500"
set -euo pipefail
P=$1; Q=$2; mkdir -p "$P/assets/fonts"; cd "$P/assets"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
curl -s -A "$UA" "https://fonts.googleapis.com/css2?$Q&display=block" > g.css
python3 - <<'PY'
import re,subprocess
css=open('g.css').read();out=[];i=0
for sub,b in re.findall(r'/\* ([\w-]+) \*/\s*(@font-face \{.*?\})',css,re.S):
  if sub!='latin':continue
  url=re.search(r'url\((.*?)\)',b).group(1);fam=re.search(r"font-family: '(.*?)'",b).group(1)
  fn=f"fonts/{fam.replace(' ','')}-{i}.woff2";i+=1;subprocess.run(['curl','-s','-o',fn,url],check=True);out.append(b.replace(url,fn))
open('fonts.css','w').write('\n'.join(out));print(len(out),'font faces')
PY
rm -f g.css
