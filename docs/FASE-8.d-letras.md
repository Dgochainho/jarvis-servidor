# Fase 8.d — letras sincronizadas

**2026-10-20** · Documento de desenho, escrito antes do código. Por discutir.

O documento que manda é o PDF de 12-10
(`camada_visual__hardware_e_integração_12_10_2026_19_13.pdf`, Drive
`Jarvis / Camada Visual`). Este concretiza os passos 2 e 3 da ordem de trabalho
dele — `lyrics_service` e `visual_service` — e acrescenta uma matriz virtual no
browser no lugar do cliente de terminal. Onde não diz nada, segue o PDF.

> **Numeração.** O `Fase_8_Camada_Visual.md` já chamava **8.d** às letras, e
> é esse o número que fica. A "8.b" deste repositório (o tema do LCD) colide
> com a "8.b · Decidir a D4" desse documento — a D4 foi fechada pelo PDF, mas
> fica registado.

---

## A ideia

As letras aparecem na matriz de 128×32 (D5 do PDF), sincronizadas com a
música. O servidor busca a letra ao LRCLIB, parte-a em filas de 21 caracteres e
manda-a inteira ao nó por WebSocket, com o relógio da reprodução; o nó decide
localmente, a 30 fps, que linha está activa.

Enquanto não há hardware, o nó é uma página no browser que fala exactamente o
mesmo protocolo. Quando o Matrix Portal chegar, troca-se a página pelo nó e o
servidor não muda.

---

## Passo 0 — a medição

`diagnostico_letras.py`, sobre as 78 faixas do `capas.jsonl` (uso real, não
uma lista escolhida). Três corridas no mesmo dia; os números abaixo são os da
última, e as outras duas diferem só nos erros.

### Cobertura

| | faixas | |
|---|---|---|
| **letra sincronizada** | **49** | 63% |
| só texto, sem tempos | 2 | 3% |
| marcada instrumental | 1 | 1% |
| **não existe no LRCLIB** | **26** | 33% |
| erro | 0 | — |

As 26 "não existe" tiveram **zero resultados** na pesquisa — não é o critério
de comparação a falhar. Só uma tinha um sufixo no nome (`(feat. …) - Live From
Malibu`). Pelo tipo de música (jazz e lo-fi instrumentais) são quase todas
faixas sem letra que o LRCLIB não marca como instrumentais porque nem as tem.

**Consequência:** um terço do que se ouve aqui não tem letra. A matriz tem de
ter alguma coisa digna para mostrar nesse caso, e não é um caso de erro.

### O LRCLIB recusa a espaços

| corrida | pedidos com 503 |
|---|---|
| 1.ª, sem repetição | 19 de 77 falharam |
| 2.ª, com repetição | 26 de 77 precisaram de repetir; 3 falharam à 4.ª |
| 3.ª, com repetição | 6 de 78 precisaram de repetir; nenhum falhou |

Muito variável de corrida para corrida. Quando responde, é rápido: mediana
0,08 s, máximo 1,6 s.

**Consequência:** repetir com espera crescente é obrigatório, e a letra (ou a
ausência dela) tem de ficar em cache no disco, para a mesma faixa não voltar a
perguntar.

### Comprimento das linhas

Nas 49 letras sincronizadas, 1972 linhas:

| | linhas | |
|---|---|---|
| cabe numa fila de 21 | 558 | 28% |
| precisa de duas filas | 1069 | 54% |
| precisa de três filas | 314 | 16% |
| não cabe em três filas | 31 | 1,6% |

A mais comprida tem 88 caracteres.

**Consequência:** o arranjo do PDF — *"um verso inteiro partido em duas filas
mais a linha seguinte em tom apagado"* — serve **82%** das linhas. As outras
precisam de regra própria (L2).

### Caracteres fora do Latin-1

3 das 49 letras. Só dois caracteres, ambos de transliteração óbvia:

| | ocorrências | passa a |
|---|---|---|
| `’` (aspa tipográfica) | 3 | `'` |
| `е` (e **cirílico**, igual à vista ao latino) | 4 | `e` |

Nenhuma letra noutra escrita nesta amostra. A política do PDF (*"ou translitera,
ou envia uma fila vazia"*) fica com as duas metades: translitera o que tem
equivalente, e o que sobrar desiste da linha.

### O relógio

Das 30 791 idas ao Spotify registadas nos logs (`[PERF] /api/status`):

| mediana | p10 | p90 | p99 |
|---|---|---|---|
| 0,90 s | 0,74 s | 1,33 s | 10 s |

O `server_time_ms` do `get_status` é carimbado **quando a resposta chega**, e o
`progress_ms` refere-se a um instante a meio do pedido. Usá-los como estão põe
a letra ~0,45 s atrasada, com ±0,3 s de variação de leitura para leitura.

---

## Decisões propostas

**L1 — o fornecedor.** LRCLIB, como no PDF.

- Primeiro `/api/get` com faixa, artista, álbum e **duração** — o `get_status`
  já a tem, e a duração escolhe a versão certa. Se não houver, `/api/search`,
  com o critério do diagnóstico.
- 503 → repetir a 1, 2 e 4 s.
- Cache no disco, por id da faixa no Spotify, **incluindo o "não há"**: a
  mesma faixa nunca pergunta duas vezes. O "não há" expira ao fim de 30 dias
  (o LRCLIB é contribuído e vai crescendo); o "há" não expira.
- Tirar os sufixos `(feat. …)`, ` - Remastered`, ` - Live …` só na segunda
  tentativa, e só se a primeira der vazio.

**L2 — as filas.** O servidor parte, o nó desenha (PDF).

- Partir por palavras em filas de até 21. Uma palavra com mais de 21 corta-se.
- **≤ 2 filas** (82%): a linha nas filas 1-2, a seguinte apagada na fila 3.
- **3 filas** (16%): as três filas, sem a seguinte.
- **> 3 filas** (1,6%): a linha divide-se em duas entradas no tempo — as
  primeiras três filas, e o resto a meio do intervalo até à linha seguinte.
  Quem divide é o servidor; o nó continua a receber só entradas de ≤ 3 filas.
- O `cols` e o `filas` vão na mensagem (PDF), para o nó recusar o que não cabe.

**L3 — caracteres.** O servidor garante que só chega ao nó o conjunto da fonte.

- Tabela de transliteração: aspas e travessões tipográficos, e as letras
  cirílicas e gregas que são iguais às latinas à vista.
- Depois disso, o que estiver fora do conjunto: decomposição Unicode (tirar o
  acento) se der um carácter do conjunto; senão a **linha** fica vazia — não a
  letra inteira.
- **O conjunto é o da fonte do nó, não o Latin-1 em abstracto.** Ver a
  questão em aberto Q1.

**L4 — o relógio.** O do PDF, mais duas correcções que saem da medição.

- O `get_status` passa a guardar quanto demorou o pedido (`pedido_ms`). A
  âncora é **o meio do pedido**: `server_time_ms - pedido_ms / 2`.
- Uma leitura com o pedido acima de 2 s não corrige o relógio (o p99 é 10 s).
- O resto é o PDF: a letra inteira vai de uma vez quando a faixa muda; cada
  mensagem leva `progress_ms` e `server_time_ms`; o `estado` a 1 Hz corrige a
  deriva; o nó decide localmente a 30 fps.
- Um **offset** global ajustável na matriz virtual, para afinar de ouvido o
  que nenhuma medição dá — a latência do próprio altifalante, por exemplo.

**L5 — de onde vem o estado, sem pesar no `/api/status`.** O `visual_service`
lê `spotify.get_status(max_age_seconds=5)` uma vez por segundo. Com a BOX
ligada, reaproveita o polling dela; com a BOX desligada, faz no máximo uma ida
ao Spotify a cada 5 s. O `/api/status` fica intocado.

O custo disto: uma pausa ou um salto na música vê-se na matriz com até ~6 s de
atraso. Para letras, aceitável; se não for, encurta-se o `max_age` só para o
`visual_service`.

**L6 — sem letra.** Um terço das faixas. A matriz mostra o título na fila 1 e o
artista na fila 2, com as cores da paleta — o que o PDF chama *"uma fila vazia
com o título"*, alargado ao artista porque há espaço.

**L7 — o `visual_service`.** WebSocket em `:8766/visual`, só push, com as
mensagens `track`, `letras` e `estado` do PDF. `websockets` 16, como o servidor
de voz, numa thread própria. **Se a porta não abrir, o arranque falha** (B5).

**L8 — a matriz virtual.** Uma página `/matriz`, servida pelo Flask, que liga
ao `:8766/visual` e desenha 128×32 LEDs num canvas, com a mesma fonte e as
mesmas regras que o nó vai ter. Mostra também o desvio do relógio e o offset.

---

## Questões em aberto

**Q1 — a fonte do nó.** O PDF fala de "um tipo de letra 5×8 num bloco de 6
píxeis". A fonte por omissão da Adafruit GFX é a de 5×7 do **CP437** — e o
CP437 **não tem `ã` nem `õ`**, que em letras em português aparecem em quase
todos os versos. Ou o nó leva uma fonte com o Latin-1 completo, ou o servidor
translitera o `ã` para `a` e as letras em português perdem os tis.

A proposta: escolher já uma fonte 5×8 com o Latin-1 inteiro e de domínio
público — a `5x8` do X11 (`misc-fixed`) é a candidata óbvia — e usá-la **nos
dois lados**: a matriz virtual desenha com ela, e o nó vai levar a mesma
tabela. Isso obriga a descarregar o ficheiro BDF da fonte.

**Q2 — o nó a reconectar e o brilho (R4 do PDF).** Ficam para quando houver
nó; a matriz virtual não tem brilho a sério para afinar.

---

## Como se prova

- **T36 — `lyrics_service`** (sem rede): LRC **fabricado** para o teste — nunca
  letra real no repositório —, quebra em filas, as quatro regras do L2,
  transliteração, cache com o "não há" e a expiração, os 503.
- **T37 — `visual_service`** (sem rede): as mensagens têm o formato do PDF, a
  âncora a meio do pedido, a leitura lenta ignorada, o `/api/status` igual.
- **T38 — na matriz virtual, de ouvido**: três músicas com letra, uma sem, uma
  pausa, um salto; a linha muda com a voz, dentro de um erro que não se note.
