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

> **2026-10-21 · a cloud foi considerada e posta de parte.** Pensou-se na
> Cloudflare. Os Workers (incluindo os de Python) não correm este servidor:
> sem threads, sem código nativo (o Pillow), 128 MB, disco efémero. Os
> Containers correm a imagem como está, mas têm disco efémero, foram feitos
> para adormecer, não garantem uma instância sempre ligada, e cobram por tempo
> activo — e o polling da BOX nunca os deixaria adormecer. Qualquer cloud
> obrigava ainda a quatro mudanças que uma máquina em casa não pede: a BOX
> deixava de encontrar o servidor por mDNS e passava a precisar de TLS;
> todos os endpoints, hoje sem autenticação, ficavam expostos na internet
> (incluindo o `/api/voice`, que gasta Gemini); o estado precisava de disco
> persistente; e a latência da voz teria de ser medida de novo. **Decisão:
> uma máquina sempre ligada em casa — a torre, por agora.** Se um dia a cloud
> voltar à mesa, um VPS tem muito menos atrito do que a Cloudflare.

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

> **2026-10-21 · aprovado e feito.** O `spotify_client` passa a ter uma
> `requests.Session`, partilhada pelas threads (o pool do urllib3 é seguro
> entre threads). Os testes sem rede passam, mas não exercitam o Spotify: a
> previsão só se confirma no servidor a correr, depois de reiniciado. Não se
> mediu com um segundo processo ao lado, de propósito: partilharia o ficheiro
> do token, e uma renovação feita por ele podia deixar o servidor sem sessão.
>
> **2026-10-21 · as duas previsões confirmam-se.** CPU em repouso de 33,3%
> para **2,4%** de um núcleo; ida ao Spotify de 1,27 s para **0,16 s** de
> mediana (p90 de 1,63 s para 0,22 s). As ligações HTTPS passam a ficar
> abertas e a ser reaproveitadas. Números completos no `TESTES.md`.
>
> De caminho, uma coisa que não se sabia: o `[PERF] /api/status` só escreve
> acima de 0,5 s. Com a `Session`, quase nenhum pedido lá chega, e o `[PERF]`
> passou a contar só os lentos. A distribuição usada na 8.d também era só a
> dos lentos — sem efeito na âncora do relógio, que usa o `pedido_ms` de
> cada leitura.

---

## Passo 2 — uma conversa de voz

**2026-10-21.** Já com a `Session`. Uma amostra por segundo durante 5 minutos
sobre o processo do servidor: 3 minutos de repouso, depois uma conversa de 5
turnos (19:00:37 a 19:01:56, no `turnos.jsonl`). A página `/paleta` estava
aberta nos dois períodos.

| | repouso | conversa |
|---|---|---|
| CPU, média | 0,5% de um núcleo | 4,6% |
| CPU, p95 | 2,2% | 13,5% |
| CPU, máximo | 4,5% | **92,5%** — um pico isolado, ver abaixo |
| memória | 69–82 MB | 69–81 MB |
| E/S, média | 0,5 KB/s | 41,5 KB/s |
| E/S, máximo | 2,7 KB/s | 555 KB/s |

A E/S é a contagem do Windows por processo, que soma rede e disco — uma
aproximação, não um medidor de rede. A média da conversa bate com o que a voz
deve custar: 16 kHz × 16 bits são 32 KB/s em cada sentido, enquanto se fala ou
se ouve.

**O pico.** Cerca de 3 s acima dos 30%, com 92,5% no segundo mais alto, logo no
início do 3.º turno — cerca de 1,7 s de CPU ao todo. O log não tem hora em cada
linha, e por isso não se consegue atribuir ao certo; o candidato é o
processamento da resposta do Gemini. Isolado, e sem efeito na voz (o turno
correu normal). **Fica em aberto**: se interessar, apanha-se com o `py-spy
record` numa conversa.

**O que isto diz sobre a máquina:** quase nada a exige. Memória abaixo dos
100 MB, CPU média abaixo de 5% de um núcleo a falar, rede na ordem das dezenas
de KB/s. A torre sobra; um Raspberry Pi também chegaria, se um dia a torre der
lugar a uma coisa mais pequena.

## Passo 3 — o desenho da mudança

**2026-10-21.** Decidido: a torre leva **Linux** (vem com Windows). As
características ficam para quando estiver pronta. O `turnos.jsonl` **não vai**:
a torre começa com um registo novo, só com o que for dito depois da mudança.

### M1 — o servidor como serviço do sistema

Um serviço do `systemd`, em vez do `iniciar-servidor.ps1`:

- arranca com a máquina e **reinicia sozinho** se cair (`Restart=on-failure`,
  com 5 s de intervalo);
- corre com um utilizador próprio, sem privilégios de administrador;
- escreve no mesmo `log-servidor.txt` de sempre, e roda o anterior para
  `log-servidor-<data>.txt` a cada arranque, como o `.ps1` faz hoje — os
  hábitos de análise (e os `grep` deste projecto) continuam a servir.

**O problema da consola desaparece, em vez de ser contornado.** O aviso do
`CLAUDE.md` (*"nunca corras `python app.py` com a saída no terminal"*) existe
porque a consola do Windows bloqueia o processo. Um serviço não tem consola.

O `iniciar-servidor.ps1` fica, para quem correr o servidor no portátil em
desenvolvimento.

### M2 — instalação

- **Distribuição:** uma com suporte longo e Python 3.12 ou mais recente —
  Ubuntu Server 24.04 LTS ou Debian 13. O servidor foi sempre corrido em 3.12;
  com outra versão, os testes T31–T37 dizem se alguma coisa mudou.
- **Código:** `git clone` do `jarvis-servidor`, ramo `main`. Actualizar passa
  a ser `git pull` e reiniciar o serviço.
- **Dependências:** `requirements-lock.txt` num venv.
- **Ligação por cabo**, se der. A voz são 32 KB/s em cada sentido e não gosta
  de cortes; o Wi-Fi da BOX já é a parte frágil, não vale a pena juntar outra.

### M3 — o que passa do portátil para a torre

| | vai? | como |
|---|---|---|
| `.env` | sim | à mão (pen ou `scp`), **nunca pelo git** |
| `.spotify_token.json` | sim | à mão; com ele não é preciso voltar a fazer login |
| `capas.jsonl` | sim | o corpus da 8.b; decidido a 2026-10-21 — *"vai ser importante mais tarde"* |
| `letras_cache/` | sim | poupa pedidos ao LRCLIB; se faltar, refaz-se sozinha |
| `turnos.jsonl` | **não** | decidido |
| `log-servidor*.txt` | não | ficam no portátil, com a história até hoje |

Se o token alguma vez não servir na torre, o login do Spotify volta para o
`/callback` do `SPOTIFY_REDIRECT_URI`, que hoje aponta para o portátil — fica
anotado, não se resolve antes de ser preciso.

### M4 — o portátil tem de deixar de ser servidor

**Dois servidores a anunciar `spotify-service.local` na mesma rede é o B5 outra
vez** — a BOX pode ir ter com o errado, e nada o diz. Antes de a torre arrancar
o serviço pela primeira vez, o servidor do portátil pára e não volta a ser
arrancado. O nome da torre na rede **não** pode ser `spotify-service`: esse é
o do serviço, que o `zeroconf` anuncia, e o Linux anuncia o da máquina à parte.

### M5 — a torre não pode adormecer nem ficar desligada

- Suspensão e hibernação desligadas no sistema (num Linux de servidor já vêm
  assim; num de secretária, não).
- Na BIOS, ligar sozinha quando volta a corrente, para uma falha de luz não
  deixar o Jarvis em baixo até alguém carregar no botão.

### M6 — rede

As portas 8888, 8765 e 8766 em TCP, e a 5353 em UDP para o mDNS, abertas **só
para a rede local** na firewall da torre. Nada é aberto no router: o servidor
continua invisível de fora, que é o que permite os endpoints não terem
autenticação.

### Como se prova

Na torre, por esta ordem:

1. **T31–T37** sem a BOX (o T34 vai dizer `NÃO VERIFICADO` no ponto do
   firmware, porque o caminho é de Windows — é o comportamento previsto).
2. **T01** arranque limpo e **T02** a BOX encontra o serviço — os dois que
   esta mudança pode partir.
3. **T03** botões, **T07** voz, **T38** a matriz.
4. **T39, novo — o servidor volta sozinho:** matar o processo e ver o
   `systemd` reiniciá-lo; desligar a torre da corrente e ver tudo voltar,
   com a BOX a reencontrá-la sem ninguém tocar em nada.

## Passos seguintes

4. ~~Escrever o serviço e o guia de instalação~~ — feito a 2026-10-21, em
   `deploy/`: `jarvis.service`, `arrancar.sh` (o equivalente do `.ps1`),
   `actualizar.sh` (git pull, testes, e só então restart) e `INSTALAR.md`,
   passo a passo. O `.gitattributes` garante LF nos scripts. Não foi corrido
   em Linux nenhum: só a sintaxe dos scripts foi verificada.
5. A mudança, quando a torre estiver pronta — com as características dela
   registadas aqui.

Depois da mudança, actualizar o que deixa de ser verdade: a secção *Arrancar*
do `CLAUDE.md` (passa a ser o serviço, não o `.ps1`), o aviso da consola que
bloqueia (deixa de se aplicar na torre), e *O outro lado* no `CLAUDE.md` do
firmware, que diz onde vive o servidor.
