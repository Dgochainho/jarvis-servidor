# Fase 8.b — a capa dá cor ao LCD

**2026-10-20** · Documento de desenho, em construção. Para já só tem o passo 1.

---

## A ideia

O fundo, o texto e os botões do LCD da BOX mudam de cor conforme o álbum que
está a tocar, com o contraste garantido por construção. O servidor calcula o
tema a partir da paleta da 8.a; a BOX só aplica as cores, uma vez por cada capa
nova, sem tocar no `/api/status`.

Antes de se escolher qualquer número (quão escuro o fundo, que razão de
contraste mínima), é preciso um conjunto de capas reais. Escolher limiares com
duas capas foi o que custou o documento da Fase 4.

## Passo 1 — o instrumento

**O que regista:** cada capa **nova** que a BOX pede, uma linha por capa em
`capas.jsonl`, com:

- `ts`, `capa` (o URL do CDN do Spotify, que é estável e permite voltar a
  descarregar a imagem no passo 2);
- `faixa`, `artista`, `album`, para se saber de que capa se está a falar
  quando se julgar o tema;
- a paleta inteira da 8.a: `dominante`, `realce`, `mais_viva` e as 8 cores.

**Decisões:**

- **Onde se pendura.** No `/api/cover.rgb565`, e não no `/api/status` nem no
  `/api/paleta`. É o pedido que a BOX faz exactamente uma vez por cada capa
  nova, e a paleta já foi calculada aí, de borla. Fica de fora quem ouve com a
  BOX desligada — e está bem assim, porque o que se quer julgar é o que a BOX
  mostra.
- **Depois das medições.** A linha escreve-se depois de fechado o `[PERF]` do
  pedido, para os tempos continuarem comparáveis com os de Setembro.
- **Uma linha por capa, não por vez que toca.** Um álbum ouvido dez vezes não
  deve pesar dez vezes na escolha de um limiar. O módulo lembra-se dos URLs que
  já escreveu, incluindo os de arranques anteriores.
- **Nunca levanta excepção.** Como o `turn_log`: o registo é para observar o
  sistema, não para fazer parte dele.
- **Fora do git** (`*.jsonl`). Não tem transcrições, mas é histórico de audição.

**Quando chega:** não antes de ~50 capas. É um palpite para começar, não um
limiar — o que interessa é que haja capas escuras, claras, saturadas e quase
monocromáticas em número suficiente para ver padrões. `python capas_log.py`
diz quantas há e de que tipo.

## Passos seguintes (por escrever)

2. Desenho do cálculo do tema, e uma página `/tema` com o LCD simulado, em
   grelha, para todas as capas do corpus.
3. Firmware: pedir o tema na troca de capa e aplicar as cores.

Questões já identificadas para o passo 2:

- **A barra de voz não muda de cor** (é sinal de estado lido da sala), mas um
  fundo verde ou âmbar rouba-lhe saliência. Moldura neutra, ou fundo limitado a
  escuros pouco saturados?
- **Razão de contraste mínima.** O WCAG dá 4.5:1 para texto de 14 px como ponto
  de partida; um LCD em RGB565 a 3 m não é um monitor.
- O estado premido de dois botões usa `lv_color_hex(999999)` em decimal
  (`display_LCD.c` l. 1709 e 1759) — dá `0x0F423F`, não cinzento. O tema
  substitui estas linhas.
