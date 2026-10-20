# Fase 8.b — a capa dá cor ao LCD

**2026-10-20** · Documento de desenho, em construção. Passos 1 e 2.

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

## Passo 2 — o cálculo do tema

**2026-10-20.** Escrito com 51 capas no `capas.jsonl`: 29 com a dominante
escura, 22 clara; 20 apagadas, 21 médias, 10 garridas.

### O ponto de partida, medido

O tema de hoje está escrito à mão no `display_LCD.c`. O texto dos botões não
está: vem do tema por omissão do LVGL 9.5, que o põe **branco**
(`bg_color_primary`), e o firmware só muda o fundo do botão.

| Par | Cores | Contraste |
|---|---|---|
| texto / fundo | `#444444` sobre `#a8a8a8` | **4,10 : 1** |
| texto do botão / botão | `#ffffff` sobre `#dcdcdc` | **1,37 : 1** |
| botão / fundo | `#dcdcdc` sobre `#a8a8a8` | 1,73 : 1 |

> **2026-10-20 · medido em RGB565.** Passadas as cores para o que o LCD
> mostra (T2), o texto dá **4,22** e não 4,10; o botão 1,72 e o texto do botão
> 1,34. A página `/tema` e o T33 usam estes.

O 4,10 é útil: é um contraste que já se usa todos os dias, e a experiência diz
se chega a 3 m. O 1,37 está muito abaixo de qualquer referência — **a
confirmar a olho** na BOX antes de se tirar conclusões, porque vem de ler o
código do tema e não de ver o ecrã.

### Decisões

**T1 — o servidor calcula, a BOX aplica.** Um módulo novo, `tema_service.py`,
de funções puras: paleta da 8.a entra, cinco cores saem. Sem rede e sem estado,
para se poder testar com o corpus inteiro.

**T2 — duas medidas, cada uma para o que serve.**

- **Contraste: a fórmula do WCAG** (luminância relativa). É a referência
  conhecida e dá números comparáveis com o 4,10 de hoje.
- **Ajustar uma cor: OKLCH.** Mexer na luminosidade em OKLCH mantém o matiz, e
  um vermelho escurecido continua a ser o mesmo vermelho. Em HSL não é assim.

O contraste mede-se **depois de passar a cor para RGB565**, porque é isso que o
LCD mostra. A diferença é pequena mas existe, e o número tem de ser o do ecrã.

**T3 — as cinco cores.**

| Cor | De onde vem | Regra |
|---|---|---|
| `fundo` | a `dominante` | luminosidade e croma limitados (ver T4) |
| `texto` | claro ou escuro, com um toque do matiz do fundo | o que tiver mais contraste; tem de passar `contraste_texto` |
| `botao` | o `realce` | a luminosidade mais próxima da original que passe `contraste_botao` contra o fundo **e** deixe o texto do botão passar `contraste_texto` |
| `texto_botao` | claro ou escuro, como o `texto` | o que tiver mais contraste com o botão |
| `botao_premido` | o `botao` | luminosidade deslocada, mantendo o contraste do texto |

**T4 — o fundo: duas variantes, escolhidas a olhar.** Não se decide no papel:

- **`escuro`** — o fundo é sempre escuro e pouco saturado, mesmo numa capa
  clara. A capa sobressai, e a barra de voz mantém o destaque (resolve a
  questão do verde sobre verde).
- **`segue`** — uma capa clara dá um fundo claro; uma escura, um escuro. Mais
  fiel à capa, mas a barra de voz pode perder destaque.

**T5 — o recurso, quando nada passa.** Um tema neutro calculado pelas mesmas
regras a partir de um cinzento. **Não** é o tema de hoje: o de hoje não passa
os próprios critérios nos botões.

**T6 — a barra de voz não muda de cor.** A página mostra-a, para se julgar se
continua a ver-se em cada fundo.

### Os números, por agora

Nenhum está escolhido. São pontos de partida, e a página `/tema` deixa
mudá-los e ver o efeito nas 51 capas de uma vez.

| Parâmetro | Começa em | Porquê este |
|---|---|---|
| `contraste_texto` | 4,5 | o mínimo do WCAG para texto normal; um pouco acima dos 4,10 de hoje |
| `contraste_botao` | 3,0 | o mínimo do WCAG para elementos que não são texto |
| `fundo_l_max` | 0,30 | (OKLCH) escuro o suficiente para texto claro passar sempre |
| `fundo_c_max` | 0,06 | pouco saturado: a cor é da capa, o fundo só a lembra |
| `claro_l_min` | 0,88 | (só na `segue`) o fundo claro mínimo |

> **2026-10-20 · escolhidos.** Vistas as 52 capas na `/tema`: variante
> **`segue`**, porque dá mais variedade; os outros números ficam nos de
> partida, porque nenhum pareceu mal. Isto contraria a inclinação do passo 1
> para fundos escuros por causa da barra de voz — vista na página com a barra
> em `ouve`, não incomodou. Fica por confirmar na BOX, que é onde a escolha se
> fecha.

### Como se escolhe

1. A página `/tema` mostra o LCD simulado a 1:1 para cada capa do corpus, com
   os números de contraste por baixo e as capas que caíram no recurso
   assinaladas. No topo, o tema de hoje para comparar.
2. Escolhem-se a variante e os números a olhar para as 51 capas.
3. **A confirmação final é na BOX** — o ecrã do browser não é o LCD. Isso já é
   o passo 3.

### Como se prova

**T33 — o tema cumpre as próprias regras** (sem BOX e sem rede): para cada capa
do corpus e para casos extremos fabricados (preto, branco, cinzento médio,
vermelho puro, amarelo), o tema passa os dois contrastes depois de RGB565, ou é
o recurso e diz que é.

## Passo 3 — a BOX aplica o tema

**2026-10-20.** Confirmado na BOX antes de desenhar: o texto dos botões é
branco e lê-se mal, "mas não impossível de discernir" — bate com os 1,34 : 1.
E com nomes compridos, o fim do texto fica por baixo dos botões.

### Servidor

**S1 — `/api/tema`, um endpoint próprio.** Não é um campo no `/api/status`
(regra do `CLAUDE.md`) nem no `/api/paleta` (que é da camada visual e tem outro
cliente). Devolve as cinco cores e o URL da capa a que dizem respeito:

```json
{"activo": true, "origem": "capa", "capa": "https://i.scdn.co/…",
 "fundo": "#…", "texto": "#…", "botao": "#…",
 "botao_premido": "#…", "texto_botao": "#…"}
```

Sem reprodução: `activo: false`, `origem: "neutro"`, e o tema neutro. Com o
estado do Spotify indisponível, ou a paleta a falhar: um erro, e a BOX fica com
o tema que tem.

**S2 — é barato por construção.** A BOX pede o tema logo depois da capa, e a
paleta dessa capa já está na cache do `cover_service` (calculada de borla no
`get_rgb565`); o estado do Spotify vem da cache de 3 s. Nenhum pedido novo ao
Spotify nem ao CDN no caso normal.

### Firmware

**F1 — quando se pede.** No ciclo de 5 s do `spotify_task`, sempre que a capa
mostrada não tem ainda o tema dela. Isso cobre a capa nova e também a nova
tentativa quando o pedido falhou, sem estado extra.

**F2 — só se aplica o tema da capa que está no ecrã.** O `capa` da resposta
tem de ser igual ao URL da capa mostrada. Se a música mudou entre os dois
pedidos, o tema fica para o ciclo seguinte. Assim nunca há uma capa com o tema
de outra.

**F3 — sem reprodução, o tema neutro, sem pedido.** O neutro existe também no
firmware, como constante, para o arranque e para quando o servidor não
responde. É uma segunda cópia de uma coisa que tem de concordar — e isso já
mordeu este projecto —, por isso o T34 lê o `display_LCD.c` e compara.

**F4 — o que muda de cor.** O fundo do ecrã, o texto, o fundo dos três botões
(normal e premido) e o texto dos botões. **A barra de voz não muda** (T6).

**F5 — o botão premido.** O tema do LVGL sobrepõe-lhe preto a 35/255 e faz o
botão crescer. Tira-se com `lv_obj_remove_theme(botao, LV_PART_MAIN |
LV_STATE_PRESSED)`, para o `botao_premido` calculado ser o que se vê. O botão
deixa de crescer ao toque; a mudança de cor fica como sinal. Corrige-se de
caminho o `lv_color_hex(999999)`.

**F6 — o texto deixa de ficar por baixo dos botões.** Duas mudanças:

- a linha `PLAYING   1:23 / 3:45` passa para um texto próprio, logo acima dos
  botões, e nunca é cortada — é a que interessa;
- o resto (`SPOTIFY`, faixa, artista, álbum) continua centrado ao lado da
  capa enquanto couber. Quando não cabe, sobe o que for preciso e, se ainda
  assim não couber, é cortado com reticências no fim — perde-se o fim do nome
  do álbum, não a hora.

A página `/tema` passa a desenhar assim também.

### Como se prova

- **T34 — `/api/tema`** (sem BOX, sem rede): devolve o tema da capa que está a
  tocar, o neutro sem reprodução, um erro quando o Spotify falha, e o neutro do
  firmware é igual ao do servidor.
- **T35 — na BOX:** mudar de música várias vezes e ver o tema mudar com a capa;
  pausar até o Spotify deixar de ter reprodução e ver o neutro; um nome
  comprido não pode tapar a hora; o botão premido muda de cor.

## Questões anotadas no passo 1


> **2026-10-20 · passo 2.** As duas primeiras deixaram de ser do passo 3: a
> barra de voz é a T6 e a variante `escuro` da T4; o contraste mínimo é o
> parâmetro `contraste_texto`, escolhido na página `/tema`. Ficam aqui pelo
> rasto.

- **A barra de voz não muda de cor** (é sinal de estado lido da sala), mas um
  fundo verde ou âmbar rouba-lhe saliência. Moldura neutra, ou fundo limitado a
  escuros pouco saturados?
- **Razão de contraste mínima.** O WCAG dá 4.5:1 para texto de 14 px como ponto
  de partida; um LCD em RGB565 a 3 m não é um monitor.
- O estado premido de dois botões usa `lv_color_hex(999999)` em decimal
  (`display_LCD.c` l. 1709 e 1759) — dá `0x0F423F`, não cinzento. O tema
  substitui estas linhas.
- **O tema do LVGL também mexe no botão premido.** Além do `bg_color` do
  firmware, o estilo `pressed` do tema por omissão sobrepõe-lhe preto a 35/255
  (`recolor`) e faz crescer o botão (`LV_THEME_DEFAULT_GROW=y`). O
  `botao_premido` calculado tem de ser visto na BOX com isso por cima, ou o
  firmware tem de tirar esse estilo.
