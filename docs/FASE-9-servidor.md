# Fase 9 — o servidor sai do portátil

**2026-10-21** · Documento de desenho, em construção. Para já só tem a medição.

> **Numeração.** 9 é o primeiro número livre neste repositório. Confirmar nos
> roadmaps do Projeto claude.ai que não está gasto — a colisão de números já
> mordeu este projecto duas vezes.

---

## Porquê

O servidor vive num portátil que adormece, e quando adormece o event loop
pára horas (`50396.8 s` num caso medido). O objectivo, decidido a 2026-10-20,
é ele deixar de depender do portátil — e com isso o sono do PC deixa de ser um
problema, em vez de ser resolvido.

**Destino, por agora:** uma torre HP, modelo regulamentar `TPC-W054-SF`. As
características (CPU, memória, disco) e o sistema operativo **estão por
confirmar** — não se assumem a partir do modelo.

---

## Passo 1 — o que o servidor exige

### Código e dependências

- **Portável.** O que é específico do Windows: o lançador
  `iniciar-servidor.ps1` (PowerShell + `cmd.exe`), o texto do aviso do
  QuickEdit no `live_voice_ws_server.py`, e o caminho do firmware no T34.
  Todos os caminhos do código são relativos ao `__file__`.
- **8 dependências** (`requirements.txt`), todas com rodas para Linux em x86 e
  em ARM: Flask, zeroconf, requests, python-dotenv, google-genai, pydantic,
  Pillow, websockets.

### Estado no disco

| | |
|---|---|
| `.env` | segredos — **não se lê nem se imprime**; copia-se |
| `.spotify_token.json` | o refresh token do Spotify; copiado, evita voltar a autenticar |
| `capas.jsonl` | o corpus da 8.b (~100 KB) |
| `turnos.jsonl` | **transcrições de tudo o que foi dito** (~150 KB) — decidir se vai |
| `letras_cache/` | cache do LRCLIB (~20 KB) |
| `log-servidor*.txt` | 32 ficheiros, ~7 MB |

### Rede

Portas 8888 (HTTP), 8765 (voz), 8766 (camada visual), e o mDNS que anuncia
`spotify-service.local`. **O servidor tem de ficar na rede de casa**: a BOX
encontra-o por mDNS e a voz é sensível à latência. Uma máquina na cloud
obrigava a refazer a descoberta e o caminho da voz.

### Recursos, em repouso

Medido a 2026-10-21 no processo a correr, sem conversa nenhuma:

| | |
|---|---|
| memória | 84 MB (working set), 65 MB privada |
| threads | 6 permanentes, mais as de vida curta do Flask e do `asyncio.to_thread` |
| **CPU** | **30% de um núcleo** numa leitura de 10 s; **55%** num perfil de 30 s com a página `/paleta` aberta |

Um servidor parado não devia gastar isto. Na torre não é problema de
capacidade — mas é trabalho que não devia existir, e foi o primeiro a
investigar.

### De onde vem a CPU em repouso

`py-spy record` sobre o servidor a correr, 30 s a 100 Hz, 1644 amostras com
CPU activa:

| | |
|---|---|
| **`ssl_wrap_socket` (urllib3, linha 411)** | **98%** |
| tudo o resto | 2% |

Repartido pela origem do pedido: um terço o `/api/status` da BOX, um terço o
`/api/paleta` (a página `/paleta` aberta, a pedir de 2 em 2 s), um terço o
`visual_service`.

A linha 411 é o `context.load_verify_locations(...)`: **cada ligação nova volta
a carregar e a interpretar o pacote inteiro de certificados de confiança**. E
cada ida ao Spotify é uma ligação nova, porque o `spotify_client` usa
`requests.request(...)` solto, sem `Session` — paga o carregamento dos
certificados, o TCP e o handshake TLS de raiz, de cada vez.

O projecto já resolveu isto uma vez, noutro sítio. O `cover_service` tem uma
`Session` desde 2026-09-23, com o comentário *"cada requests.get() avulso faz
TCP e TLS de raiz com o i.scdn.co"*. O `spotify_client` ficou de fora.

### O que se prevê, e como se verifica

Com uma `Session` no `spotify_client`, a ligação ao `api.spotify.com`
reaproveita-se entre pedidos. Previsão, para ser confirmada ou desmentida:

1. **CPU em repouso** cai de 30% para poucos por cento.
2. **O tempo de cada ida ao Spotify** desce da mediana de 0,90 s: deixa de
   pagar o TCP e o TLS. Quanto, não se sabe — é o número a medir.

**Isto mexe nas baselines.** O `[PERF] /api/status` está a ser comparado com
os números de Setembro desde a Fase 1.3. Se a previsão 2 se confirmar, o
número muda — para melhor, mas muda, e as comparações a partir daqui têm de
saber que houve um degrau. Fica registado no `TESTES.md` com a data.

---

## Passos seguintes (por escrever)

2. Medir uma conversa de voz: pico de CPU, rede, memória.
3. O desenho da mudança: sistema operativo da torre, o servidor como serviço
   do sistema (arranque e reinício sozinho, log para ficheiro — o problema da
   consola que bloqueia desaparece), a passagem do token e do `.env`, o que
   fazer ao `turnos.jsonl`.
4. A mudança, com o T01 e o T02 no destino.
