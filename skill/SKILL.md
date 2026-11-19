---
name: moura-lyrics
description: Padrão do canal @moura'slyrics para lyric videos 9:16 com kinetic typography, motion e hero words (HTML + GSAP determinístico → MP4). Use sempre que o usuário pedir um novo lyric video, vídeo de letra, "fazer outra lyric", ou revisar/re-renderizar She Wolf / Elastic Heart.
---

# @moura'slyrics — padrão de lyric video

Kit na branch `moura-lyrics` do repo `thejoaomoura/rea` (orphan, sem código do rea).
Em sessão nova: `~/moura-lyrics` (worktree criado pelo setup do ambiente). Se faltar:
`cd ~/rea && git fetch origin moura-lyrics && git worktree add ~/moura-lyrics moura-lyrics`.
Ferramentas: `bash ~/moura-lyrics/setup/install.sh` (idempotente).
Base de método: skill `bang-motion` (hukum anti-PPT, determinismo, style brief) + `kinetic-typography`, `gsap-*`.

## Fluxo (sempre nesta ordem)
1. **Insumos**: áudio do usuário (+ fotos/referências). Trecho e duração ≤ 1:30.
2. **Transcrever**: `tools/transcribe.sh song.mp3 tr.json` (Groq whisper-large-v3; chave vem do
   network secret do ambiente). Whisper erra letra cantada: corrigir o texto, manter os tempos.
   Trecho duvidoso → retranscrever só ele com `START DUR "prompt com a letra"`.
3. **Analisar**: `tools/analyze.py song.mp3 tr.json A B` → palavras, **notas sustentadas**, BPM/fase,
   baixo por batida (drop/quebra).
4. **Propor antes de codar** (aprovação do usuário): trecho; conceito central da letra; rundown
   `tempo | letra | hero word + efeito | foto`; style brief (paleta com hex e origem, 4–5 fontes
   que alternam por frase, movimento-assinatura, efeito das notas longas, final).
5. **Projeto**: `tools/new-project.sh DIR song.mp3 START DUR` → `tools/fonts.sh DIR "family=…"`.
   Fotos em `DIR/assets/photos/`. Editar CONFIG/PALETTE/FONTS/SCENES do `template/index.html`.
6. **Servir e verificar**: `python3 -m http.server PORT` no DIR; `tools/contact.sh URL out 8 t1 t2…`.
   Olhar as folhas: texto cortado na borda? sobreposição de linhas? elemento que não sai? Corrigir.
7. **Render**: `START=0 node tools/export.cjs "URL?clean=1" frames 30` em background com
   `timeout` 3600000; se morrer (limite/restart), retomar com `START=<último-2>`.
   Correção pontual → re-render só o intervalo (`START`/`END`) e recodificar.
8. **Encode**: `tools/encode.sh frames assets/chorus.mp3 out.mp4` (CRF 20 + maxrate 10M; só CRF
   gerou 500 MB por causa do grão). Checar frames do MP4 final antes de entregar.
9. **Motion blur estilo After Effects** (padrão desde Circus): `tools/export-mb.cjs` (supersampling temporal,
   SAMPLES=4, SHUTTER=180, WORKERS=4 navegadores separados = ~3,4× mais rápido; retomável, pula quadros prontos)
   → `tools/encode-mb.sh subframes audio out.mp4 30 4` (tmix). GIF de prévia: mesmo par com FPS 15, SHUTTER 90.
   Prévias (folha de contato + GIFs) SEMPRE antes do render final, para aprovação.
   Movimento muito rápido (letras atravessando o quadro) com 4 amostras vira estroboscópico (cópias separadas):
   re-renderizar só esse trecho com 12 amostras e sobrepor no MP4 → `tools/mb-splice.sh URL final.mp4 A B 12`.

## Regras do padrão
- **9:16, 1080×1920, 30 fps**; marca d'água `@moura’slyrics` no topo, 30 px, `mix-blend-mode:difference`,
  opacidade .5, visível até o fim (inclusive sobre o fade).
- **Hero word** por frase: a palavra de maior carga recebe fonte própria + efeito que ilustra o
  sentido (falling → quebra; frozen → congela; rubber band → estica; snap → arrebenta). Cor de
  destaque única no vídeo inteiro; o resto em tinta/creme.
- **Momento especial** (o refrão-título): fonte dedicada + material (ouro rachado em She Wolf,
  látex vermelho em Elastic Heart), evolui a cada repetição.
- **Notas sustentadas** sempre ganham interação na tela enquanto a voz segura (gelo nas bordas,
  farelo caindo, elástico puxado, neon desenhando, ondas, brasas).
- **Nada entra ou sai seco**: toda entrada/saída com movimento + motion blur direcional (`blurT`).
  Variar entrada/tamanho/posição entre linhas consecutivas. Câmera muda de ângulo por bloco.
- **Trocas de fundo motivadas** (pálpebra, tecido, lâmina, snap circular, íris em coração).
- **Final**: corta trecho só instrumental longo; card de título + fade-out de áudio e imagem.
- **Fotos pessoais do usuário: NUNCA recortar o fundo** (pedido explícito). Usar a foto inteira em
  polaroid, adesivo arredondado, fragmentos de moldura, foto esticada, carrossel 3D. Enquadrar
  rosto/corpo inteiro, nunca zoom em partes do corpo.
- Fontes **novas a cada vídeo** (não repetir o conjunto anterior). Usadas: She Wolf = Barlow
  Condensed, Instrument Serif, Space Grotesk, Syne, Italianno, Playfair Display 900i.
  Elastic Heart = Anybody (wdth 50–150), Fraunces (SOFT/WONK), Archivo (wdth), DM Mono.
  Circus = Clash Display, Panchang, Gambetta itálico, Rampart One, Nabla (CIRCUS).
- Paletas usadas: She Wolf `#28161F #EFE8DD #D9B55B`; Elastic Heart `#0E1A2E #E8384F #F3EFE9 #3D6BFF`;
  Circus `#1A0F1F #F4E9D8 #FFC24B` (+ colagem branco/preto/verde `#14934B`).

## Direção que o usuário aprovou (Circus)
- **Câmera 3D de verdade**: cada cena é um grupo em (x,y,z) no mundo; a câmera viaja entre eles (dolly/órbita),
  com foco seletivo por distância (DOF) e deriva lenta durante a cena. Nada de cortes secos entre frases.
- **Cenário em profundidade**: fundos são planos 3D atrás de cada cena (cortina, lona, parede de lâmpadas, neon,
  picadeiro em perspectiva), nunca uma camada chapada de tela. Holofotes são feixes dentro da cena.
- **Holofotes reagem aos graves**: envelope de 30–110 Hz extraído do áudio por quadro (JSON embutido).
- **Texto respira** depois de entrar (CSS `translate` por letra, compõe com o GSAP) e sai passando pela lente.
- Entradas longas e em camadas (montagem da profundidade, rolagem, porta, onda, vindo da lente).
  O rebote seco de 9 quadros foi rejeitado — não usar.
- Fontes de display de fundição (Fontshare: Clash Display, Panchang, Gambetta; Google: Rampart One, Nabla
  colorida 3D). Fontes "padrão de sistema" foram rejeitadas. Mostrar prancha de direções tipográficas antes.

## Armadilhas já vistas
- Texto grande estoura 1080 px (Syne/Anybody largos, wdth alto, câmera com zoom) → testar o pior
  frame do estiramento; limite ~960 px.
- Duas linhas no mesmo lugar: a saída da anterior tem que terminar antes da entrada seguinte.
- `render(t)` que escreve estilo (ex.: cintilação de neon) sobrescreve o fade do GSAP → limitar a
  janela de tempo do efeito ou usar `display:none` na saída.
- GSAP em `<g>` de SVG sobrescreve o atributo `transform` → aninhar dois `<g>` (posição/anim).
- Filtro CSS num pai achata o 3D dos filhos: pôr `perspective` no próprio pai filtrado.
- rembg BiRefNet estoura a memória (e não recortamos fotos pessoais de qualquer jeito).
- Vetorizar imagem de apoio (ex.: lobo): foto de domínio público → `tools/seg.py` + `tools/trace.py`
  (camadas tonais via potrace), depois feather + sombra interna/externa para a borda não ficar dura.
- Desempenho: `filter: blur()` animado em elementos grandes é o que mais custa no Chromium sem GPU. Pré-renderizar
  (canvas → imagem) tudo que é estático (feixes de luz) e trocar `filter: brightness` por overlay com opacidade.
  Várias páginas no mesmo navegador NÃO paralelizam (compositor único) — usar navegadores separados.
- Tweens de câmera que se sobrepõem no tempo: ao pular (seek) para frente, o último a ser criado vence; nunca
  deixar cortes de uma cena invadirem a viagem para a próxima.
- Regex para remover código: âncora estrita, senão apaga bloco vizinho (perdemos uma cena inteira assim).
- Fontes sem glifo de espaço (Gambetta): o `line()` usa margem entre palavras em vez de espaço de texto.
- Background bash morre em 30 min; container pode reiniciar: frames ficam no disco, retomar.

## Referências
`references/she-wolf/index.html` (creme/tinta, ouro rachado via canvas, estilhaços triangulados,
gelo nas bordas, garras, lobo vetorial) e `references/elastic-heart/index.html` (marinho/vermelho
látex, fonte variável esticando, elástico físico, lâmina, snap, carrossel de fotos, íris em coração).
