# Estado do projecto — nota de orientação

**2026-10-20** · Escrito para quem abre este repositório sem o histórico das
conversas. O `CLAUDE.md` na raiz leva as **regras**; isto leva o **estado**.

---

## Onde vivem os documentos

A maior parte da documentação **não está neste repositório**. Está em dois
sítios, e isso é deliberado — o que descreve decisões fica fora, o que se corre
fica aqui.

| Onde | O quê |
|---|---|
| Projeto claude.ai `ESP32-S3-BOX-3_Spotify` | os 19 documentos de desenho e de fecho, por fase |
| Drive `Jarvis / Registos e Testes` | cópia de leitura dos mesmos, mais o `00_INDICE.md` |
| Drive `Jarvis / Camada Visual` | o material da Fase 8 |
| **aqui** | `TESTES.md` (o guião, 30 testes, 5 baselines) e `FASE-0-COMANDOS.md` |

⚠️ **Nada disto é visível a partir do disco.** Quem trabalhar só com os
ficheiros do repositório tem o `CLAUDE.md`, o `TESTES.md` e esta nota — e mais
nada. Se uma decisão parecer arbitrária, está explicada num desses documentos,
não no código.

---

## Fases

**Fechadas:** 0, 1 (1.1–1.4), 2, 3.2, 5, 7.
**Aberta:** 8 — a camada visual.

Três nunca se fizeram, de propósito, e saber porquê evita reabri-las:

- **Fase 4** — suspensa depois da 4.a. Contado o histórico inteiro, a pesquisa
  errou 1 vez em 8, de causa indetectável.
- **Fase 3.1** — nunca abriu. A auto-activação pela própria voz explicava 3 em
  155 turnos; o resto é som externo, aceite por decisão do Dinis.
- **Fase 6** — suspensa. A wake word está nos **86%** e a escada de volume
  contrariou a hipótese que sustentava a ordem das alavancas.

---

## O que está pendente agora

### 1. A 8.a nunca foi vista a funcionar

O `/api/paleta` e a página `/paleta` estão escritos e testados em sandbox contra
a mesma Pillow e a mesma Flask desta máquina, **mas nunca correram aqui**. A
primeira tentativa deu 404 porque o servidor em execução era anterior à
alteração — o `app.py` corre com `use_reloader=False`.

**Falta:** reiniciar o servidor, abrir `http://localhost:8888/paleta` com música
a tocar, e mudar de faixa três vezes.

**Critério:** cores reconhecíveis como sendo daquelas capas, e o
`[PERF] /api/status` com os mesmos tempos de antes.

> **2026-10-20 · feito.** Vista a funcionar nesta máquina, e com commit
> (`bf045a8`). Ideia seguinte para este ramo, enquanto não há hardware: usar a
> paleta para dar cor à interface do LCD da BOX.

### 2. Há dois documentos a discordar sobre a Fase 8

E isto é o mais importante desta nota.

O `Roadmap_Camada_Visual_2026-10-19.md` (Projeto e Drive) foi escrito **sem
conhecimento** de um documento anterior e mais desenvolvido:
`camada_visual__hardware_e_integração_12_10_2026_19_13.pdf`, de 12 de Outubro,
na pasta Drive `Jarvis / Camada Visual`.

**O PDF de 12-10 é o que manda.** Supera o roadmap em quatro pontos:

| | Roadmap de 19-10 | PDF de 12-10 |
|---|---|---|
| painel | um 64×64 | **dois 64×32 em cadeia** — 128×32, porque 64 píxeis de largura dão 10 caracteres e um verso tem 25 a 40 |
| placa | ESP32-S3 DevKit + 13 fios | **Adafruit Matrix Portal S3**, com HUB75 e adaptação de nível a bordo |
| capa | mostrada no painel | **fora do painel**, fica no LCD; o protocolo passa a JSON puro |
| letras (D5) | em aberto | **decidida: só na matriz**; a 3 m o LCD dá letras de 5 mm |

O PDF traz ainda o protocolo do `visual_service.py` (WebSocket 8766, push, o
campo `cols` para o servidor partir os versos), o desenho do relógio, e as
regras de alimentação em estrela.

**Reconciliados a 2026-10-20.** Os dois documentos meus — o roadmap e o
`Fase_8_Camada_Visual.md` — levam agora uma nota de topo datada a dizer em que
pontos estão superados e porquê. O PDF continua a ser o que manda.

Uma coisa que o roadmap acrescenta e o PDF não tem: o **R1** do PDF — a
biblioteca HUB75 ser Arduino-first — parece resolvido pelo componente
`esphome/esp-hub75` do registo da Espressif, que é ESP-IDF nativo, suporta
ESP32-S3 por GDMA, está testado até ao 6.0-rc1 e faz cadeia com `layout_cols`.
Por confirmar na prática.

### 3. Decisões em aberto

| # | Decisão |
|---|---|
| D7 | fita ambiente além da matriz? Há orçamento |
| — | os 95 s de mDNS de 18-10, e o event loop bloqueado horas quando o portátil adormece |
| — | Fase 2.1: o `action_service` duplica os endpoints do Flask |

> **2026-10-20 · decididas.**
> - **D7: sim**, fita ambiente além da matriz.
> - **Os 95 s de mDNS de 18-10:** arquivados. Nunca se repetiram.
> - **O sono do PC:** arquivado. O objectivo é o servidor deixar de depender
>   do portátil, e aí o problema desaparece com ele.
> - **Fase 2.1:** feita no ramo `fase-2.1-accoes-unicas`, falta o T03 com a
>   BOX. Ver `docs/FASE-2.1-desenho.md`.
>
> **2026-10-20, mais tarde · Fase 2.1 fechada.** T31, T03 e T07/T27 passam;
> está no `main`.
