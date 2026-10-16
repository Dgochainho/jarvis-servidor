# Guião de teste — ESP32-S3-BOX-3 / Spotify

Sempre os mesmos enunciados, sempre pela mesma ordem. Serve para responder a
uma pergunta e só a essa: **esta alteração melhorou ou piorou?**

Correr antes de cada fase e depois de cada fase. Registar no fim do ficheiro.

---

## Preparação

**Servidor** (PowerShell, na pasta `spotify-service`):

```powershell
.\iniciar-servidor.ps1
```

⚠️ **Não correr o `app.py` com a saída para o terminal.** Medido em
2026-09-30: com a saída na consola, o processo bloqueia à espera que o
terminal aceite o texto, ninguém lê o WebSocket, e a BOX estoira o timeout
de envio de PCM. Aparece no monitor como

```
transport_ws: Error transport_poll_write(0)
VOICE: Envio PCM bloqueado durante 5028 ms
VOICE: Nao foi possivel concluir a interacao de voz
```

— que parece rede má e não é. Com a saída em ficheiro: zero falhas.

O comando anterior deste guião (`python app.py 2>&1 | Tee-Object ...`) tinha
exactamente este defeito, porque o `Tee-Object` também escreve na consola.
**A Baseline 1 e a Baseline 2 foram medidas nessas condições.**

Para acompanhar o servidor enquanto corre, noutro separador:

```powershell
Get-Content log-servidor.txt -Wait -Tail 20 -Encoding UTF8
```

Numa janela **nova**. Uma que já estivesse aberta antes continua a descodificar
o ficheiro anterior e mostra lixo.

**BOX** (PowerShell, numa janela à parte). O `idf.py` não existe até se carregar
o ambiente, e isso perde-se quando se fecha a janela — por isso são sempre estas
quatro linhas, por esta ordem:

```powershell
cd "C:\Users\dgoch\Desktop\ProjetoAss Istant\projetos\hello_world"
$env:IDF_TOOLS_PATH = "C:\Espressif"
. C:\esp\v6.0.2\esp-idf\export.ps1
idf.py -p COM9 monitor
```

O **ponto solitário** na terceira linha é obrigatório: sem ele o script corre num
escopo próprio, define as variáveis lá dentro e deita-as fora ao acabar.

O `IDF_TOOLS_PATH` é preciso porque as ferramentas estão em `C:\Espressif` e o
`export.ps1` procura-as, por omissão, em `%USERPROFILE%\.espressif`. Para deixar
de repetir essa linha, uma vez só:

```powershell
[Environment]::SetEnvironmentVariable("IDF_TOOLS_PATH", "C:\Espressif", "User")
```

Sair do monitor: **Ctrl+]** (o Ctrl+C reinicia a BOX).

Ter o Spotify a tocar num dispositivo antes de começar. Ficar a ~1 m da BOX,
com a sala em silêncio, salvo indicação em contrário.

Registar o commit em teste: `git rev-parse --short HEAD` nos dois repositórios.

---

## A — Arranque e descoberta

### T01 · Arranque limpo do servidor
Arrancar o `app.py` com a BOX desligada.

**Esperado:** `Sessão Spotify restaurada automaticamente!` · `mDNS ativo: spotify-service.local -> <ip>:8888` · `[VOICE-WS] Persistente em ws://0.0.0.0:8765/voice`
**Falha se:** pedir autenticação em `/login` sem motivo, ou o mDNS não anunciar.

### T02 · A BOX encontra o serviço
Ligar a BOX com o servidor já a correr.

**Esperado:** `Ligado ao Wi-Fi!` · `Spotify Service encontrado!` · `WebSocket Live persistente ligado ao PC` · `Servidor Live pronto` (READY) · no servidor, `BOX persistente ligada`.
**Falha se:** ficar em `WS persistente ainda indisponivel` mais de ~10 s com o servidor a correr.

---

## B — Spotify pelo LCD *(já funciona — não pode regredir)*

### T03 · Botões de transporte
Carregar em `>>`, depois `<<`, depois `PLAY / PAUSE` duas vezes.

**Esperado:** cada um age em menos de ~1 s; o LCD reflete o estado em ≤5 s.
**Falha se:** o `PLAY / PAUSE` ficar invertido face ao estado real.

### T04 · Capa do álbum
Mudar de faixa (para um álbum diferente).

**Esperado:** `Nova capa detectada` · `Capa recebida: 28800 bytes` · a imagem muda no LCD.
**Falha se:** `Tamanho inesperado` ou `Buffer da capa nao existe`.

### T05 · Progresso temporal
Observar 30 s com a música a tocar.

**Esperado:** o contador avança de segundo a segundo e corrige-se a cada sincronização (5 s), sem saltos para trás visíveis.

---

## C — Voz, caminho feliz

### T06 · Pergunta simples
Dizer **"Jarvis"**, esperar pela deteção, depois **"o que está a tocar?"**

**Esperado:** `>>> JARVIS DETETADO <<<` · `WAKE enviado ao PC` · `Fala detetada` · no servidor, a tool `spotify_control` com `current_track` · resposta falada com o nome certo da faixa.
**Medir:** `[PERF] Primeiro áudio Gemini Live WS` — anotar o valor.

### T07 · Comando de transporte
Dizer **"Jarvis"**, depois **"passa esta"**.

**Esperado:** tool call `next`, a faixa muda, e o Jarvis confirma por voz.
**Falha se:** confirmar verbalmente sem a faixa ter mudado.

### T08 · Follow-up sem wake word
Logo a seguir ao T07, sem dizer "Jarvis": **"e quem canta?"**

**Esperado:** `>>> FOLLOW-UP DETETADO SEM JARVIS <<<` e resposta correta na mesma conversa.
**Falha se:** for preciso repetir "Jarvis".

---

## D — Voz, casos maus *(é aqui que se descobrem as coisas)*

### T09 · Jarvis seguido de silêncio ⚠️
Dizer **"Jarvis"** e **não dizer mais nada**. Esperar 10 s. Depois tentar
**"Jarvis"** outra vez.

**Esperado (depois da Fase 1):** a BOX cancela e volta a responder ao segundo "Jarvis".
**Comportamento atual conhecido — bloqueador B1:** falha. Procurar esta sequência no monitor:

```
Comando cancelado: nenhuma fala apos Jarvis
Turno concluido; conversa continua ativa
Conversa ativa; a aguardar nova fala sem Jarvis...
```

A partir daqui o WakeNet está desligado e o segundo "Jarvis" é ignorado.
**Este teste é o critério de aceitação da Fase 1.1.**

### T10 · Comando longo
Dizer **"Jarvis"** e depois falar mais de 12 segundos sem parar.

**Esperado:** `limite maximo de 12 segundos`, o turno fecha ordenadamente e a BOX rearma.
**Falha se:** ficar sem responder a um "Jarvis" seguinte.

### T11 · Servidor reinicia a meio
Com a BOX ligada e em repouso, matar o `app.py` (Ctrl+C) e voltar a arrancá-lo.

**Esperado:** em ≤10 s, `WS sem CONNECTED+READY ha 10000 ms; a forcar recriacao` seguido de nova ligação e `Servidor Live pronto`. Um "Jarvis" a seguir funciona.
**Falha se:** for preciso reiniciar a BOX.

### T12 · Auto-activação pela própria voz
Dizer **"Jarvis"**, depois **"conta-me uma curiosidade sobre o Tame Impala"**
(força uma resposta longa). Ficar em silêncio absoluto enquanto ele fala.

**Esperado:** a BOX não se ativa com a própria voz.
**Falha se:** aparecer `>>> FOLLOW-UP DETETADO SEM JARVIS <<<` enquanto o
altifalante ainda está a tocar. **Critério de aceitação da Fase 3.1.**
Anotar quantas vezes em 3 tentativas.

### T13 · Falso positivo em ruído
Logo após uma resposta, fazer um ruído não-falado perto da BOX (bater palmas,
arrastar uma cadeira) dentro da janela de 30 s.

**Esperado:** ignorado.
**Falha se:** abrir um turno. **Critério da Fase 3.2.** Anotar em 3 tentativas.

---

## E — Ainda não implementado *(falha esperada hoje)*

### T14 · Pesquisa e reprodução
Dizer **"Jarvis"**, depois **"põe Arctic Monkeys"**.

**Hoje:** `Pesquisa e reprodução ainda não implementadas.`
**Critério de aceitação da Fase 2.3.**

### T15 · Volume
Dizer **"Jarvis"**, depois **"mete o volume a quarenta"**.

**Hoje:** `Controlo de volume ainda não implementado.`
**Critério de aceitação da Fase 2.2.**

---

## F — Contrato de conversa e fallback *(Fases 1.1 e 1.2)*

### T16 · Timeout de follow-up
Fazer uma pergunta normal, ouvir a resposta, e depois ficar em **silêncio
absoluto mais de 40 s**.

**Esperado:** aos ~30 s o servidor envia `SLEEP` e a BOX regista
`SLEEP recebido; conversa Gemini terminou`. Um "Jarvis" a seguir funciona.
**Falha se:** a BOX continuar a aceitar fala sem wake word passados 45 s.

### T17 · SLEEP perdido ⚠️
Com a conversa activa e a BOX em follow-up, **matar o servidor** (Ctrl+C) e
manter silêncio absoluto 45 s.

**Esperado:** `Sem SLEEP do servidor apos 40 s; Jarvis rearmado localmente`.
**Falha se:** a BOX ficar presa em follow-up à espera de uma mensagem que já
não pode chegar.

Este é o único teste que valida a camada 3 da Fase 1.1 — a rede de segurança
local. É também o mais fácil de dar por passado sem o ser: se a BOX recuperar
por outro caminho (por exemplo `Nao foi possivel armar Live`), o timeout **não**
foi exercitado e o resultado é inconclusivo, não `OK`. Procurar a linha exacta.

### T18 · Fecho por voz
Fazer uma pergunta normal, ouvir a resposta e dizer **"obrigado, é tudo"**.

**Esperado:** o Jarvis despede-se, a despedida toca **inteira**, e o log mostra
`end_conversation` seguido de `SLEEP` e `DONE`. A BOX volta a exigir a palavra de
acordar imediatamente, sem esperar os 30 s.
**Falha se:** a BOX rearmar antes de a despedida acabar de tocar.

### T19 · Falso positivo de despedida
Dizer **"obrigado por teres posto essa música"**.

**Esperado:** a conversa **não** termina.
**Falha se:** o `end_conversation` aparecer no log deste turno.

### T20 · Fallback HTTP sem a BOX
Com o `app.py` a correr, na pasta do servidor:

```powershell
python teste_fallback_http.py
```

**Esperado:** `PASSA`, HTTP 200, e alguns segundos de áudio devolvido. No log do
servidor aparece `[LIVE] Tu: ...`.
**Falha se:** zero bytes — é a assinatura do B2, em que a excepção morria dentro
do gerador e o Flask fechava a resposta vazia.

Este teste existe porque o caminho HTTP só corre no firmware quando a sessão
WebSocket **nunca chega a armar** (`voice.c`, l. 1627-1647), o que é raro e
difícil de provocar à mão. Foi por isso que o B2 sobreviveu meses sem ninguém
dar por ele: o ramo estava sempre a rebentar, mas quase nunca era chamado.

### T21 · Fecho por voz sem áudio ⚠️

O Gemini nem sempre despede-se e fecha no mesmo turno: por vezes diz "Até à
próxima!" num turno e chama o `end_conversation` no turno seguinte, que então
não tem áudio nenhum.

Difícil de provocar à vontade. Verifica-se **a posteriori**, no registo: procurar
turnos com `end_conversation` e `1.º áudio —`.

**Esperado:** `resultado: done`, e no log
`Fecho por voz sem áudio: a despedida foi no turno anterior`.
**Falha se:** `RuntimeError: Gemini Live terminou sem devolver áudio`. Era o
comportamento até 2026-09-27: a conversa acabava pelo caminho do erro em vez do
caminho do fecho. Funcionava por acidente, porque a BOX também rearma com
`ERROR`.

### T22 · Pôr a tocar por nome

Com o Spotify a tocar noutra coisa, dizer:
**"Jarvis, põe Let It Happen dos Tame Impala"**.

**Esperado:** a faixa certa começa a tocar e o Jarvis diz
*"A tocar Let It Happen, de Tame Impala."* No registo:

```
tool: spotify_control({'action': 'play_search', 'query': '...', 'tipo': 'track'}) -> ok
```

**Falha se:**

- a acção for `next` em vez de `play_search` — o modelo não percebeu que havia
  um nome. Foi o que aconteceu a 10-03, e a correcção foi pôr uma descrição com
  exemplos no parâmetro `action`; o `enum` sozinho não chega.
- o Jarvis disser que não consegue tocar músicas específicas. Até 2026-09-28
  dizia-o, e tinha razão.
- aparecer `Não consegui pesquisar no Spotify agora.` — ver T28.

### T23 · Tipo correcto

Três pedidos seguidos: **"põe Tame Impala"** (artista), **"põe Do I Wanna
Know"** (faixa), **"põe o álbum Currents"** (álbum).

**Esperado:** no registo de turnos, o `tipo` enviado é `artist`, `track` e
`album`, pela ordem certa, e os três tocam.
**Falha se:** o `tipo` não bater certo. Quem o decide é o Gemini (decisão D3),
porque "Tame Impala" é um artista e "Do I Wanna Know" é uma faixa, e nenhuma
regra fixa deste lado acerta nos dois.

Importa porque faixas tocam por `uris` e o resto por `context_uri` — são ramos
diferentes do código.

**Corrido a 2026-10-14**, com `artist`, `track` e `album` todos a `ok`. Foi a
primeira vez que o `context_uri` correu em campo.

### T24 · Sem dispositivo activo

Fechar o Spotify em **todos** os dispositivos. Dizer **"Jarvis, põe Tame
Impala"**.

**Esperado:** resposta falada a dizer que não há nenhum dispositivo activo e que
é preciso abrir o Spotify. Decisão D7 — dizer e parar, sem adivinhar um
dispositivo e pôr música a tocar noutro sítio da casa.
**Falha se:** excepção no log, silêncio, ou o turno abortar.

Confirmar também no `log-servidor.txt` a linha do `_registar_recusa`, que leva a
resposta inteira do Spotify:

```
[ACCAO] play_search recusado com 404: {
  "error" : {
    "status" : 404,
    "message" : "Player command failed: No active device found",
    "reason" : "NO_ACTIVE_DEVICE"
  }
}
```

**Corrido a 2026-10-14.** Passou, e foi a primeira vez que o `_registar_recusa`
da Fase 2 chegou a correr.

### T25 · Pesquisa sem resultados

Sem a BOX, na pasta do servidor:

```powershell
.\.venv\Scripts\python.exe teste_sem_resultados.py
```

**Esperado:** `PASSA`, com `ok: True` e a mensagem *"Não encontrei nada com o
nome ..."*.
**Falha se:** `ok: False`. Não encontrar não é uma avaria — se for tratado como
erro, o Jarvis pede desculpa de uma coisa que não aconteceu.

**Não é um teste de voz, e isso foi medido.** O enunciado original era dizer
*"Jarvis, põe zxqwverty"*. Não serve por duas razões:

1. "zxqwverty" dito em voz alta não chega ao servidor como "zxqwverty" — chega
   como outra coisa que o Gemini percebeu, e essa outra coisa costuma existir.
2. **A pesquisa do Spotify nunca devolve vazio.** Medido a 2026-10-07: sete
   strings de consoantes aleatórias, até 45 caracteres, nos quatro tipos —
   *todas* devolveram pelo menos um resultado.

Por isso o script tem duas fases: tenta encontrar uma string que o Spotify
recuse e, se não conseguir, substitui o `search` por um que devolve lista vazia
e corre o mesmo `execute_spotify_action`. Deixa de provar que a API devolve
vazio e passa a provar que o nosso código trata o vazio como deve — que é a
parte que nos pertence. O script diz qual das duas aconteceu, e um
`PASSA (simulado)` **regista-se como "OK (simulado)"**, não como "OK".

> **O que este teste descobriu, e é mais importante do que ele.** Se o Spotify
> devolve sempre alguma coisa, então ao pedir uma música que não existe o
> Jarvis não diz "não encontrei": põe a tocar o que calhou ser mais parecido,
> com toda a convicção. O ramo vazio é quase teórico; o falso positivo de
> pesquisa é real e não tem teste nenhum. Candidato a uma fase própria —
> comparar o nome devolvido com o pedido e, abaixo de certa semelhança,
> perguntar em vez de tocar.

### T26 · Volume por voz

Dizer **"mete o volume a 40%"**, depois **"põe no máximo"**.

**Esperado:** `set_volume` com `volume: 40` e depois `volume: 100`, ambos `ok`,
e o volume muda mesmo no dispositivo.
**Falha se:** `403` — vários altifalantes e televisões Spotify Connect não
aceitam controlo de volume de fora. Nesse caso não é bug nosso, mas a mensagem
tem de o dizer.

### T27 · Comando de transporte devolve 2xx ⚠️

Dizer **"muda de música"** e confirmar que a faixa muda **e** que o registo diz
`-> ok`.

**Esperado:** `spotify_control({'action': 'next'}) -> ok`.
**Falha se:** `FALHOU` com a faixa a mudar à mesma. Esse é o sintoma exacto do
bug encontrado a 2026-10-05:

```
tu:     Muda de música, não gosto desta.
tool:   spotify_control({'action': 'next'}) -> FALHOU
        O Spotify respondeu com erro 200.
```

O `send_command` só aceitava **204** como sucesso, que é o que a documentação
promete nos endpoints do player. Quando veio 200, o código tratou a resposta de
sucesso mais comum que existe como recusa, e o Jarvis pediu desculpa por uma
coisa que tinha feito. A regra agora é 2xx.

Este teste é o mais fácil de dar por passado sem o ser: **ouvir a música mudar
não chega**, porque ela muda nos dois casos. Tem de se olhar para o registo.

### T28 · Pesquisa Spotify (diagnóstico)

Sem a BOX, na pasta do servidor:

```powershell
.\.venv\Scripts\python.exe diagnostico_pesquisa.py
```

**Esperado:** `Sessao Spotify restaurada`, e as quatro variantes a **200**.
**Falha se:** alguma der 403. O script imprime o corpo da resposta, que é onde
o Spotify diz o que recusou.

Existe por causa de 2026-10-04, em que o `GET /search` devolvia
`403 Insufficient client scope`. A causa era o `market=from_token`, que manda o
Spotify ir ver o país da conta e por isso exige o scope `user-read-private`, que
não pedimos. Está agora escrito à mão (`MERCADO = "PT"`). Se um dia alguém puser
`from_token` outra vez, este teste apanha-o antes de a BOX apanhar.

---

## Registo

Legenda: `OK` · `FALHA` · `—` (não medido) · `?` (inconclusivo)

## Baseline 1 — 2026-09-22

Firmware `2849c97` (`v0-funcional-2-g2849c97`) · Servidor `94b14d2`
RSSI da BOX: **-73 dBm** (variou entre -73 e -80 ao longo da sessão)

| Teste | Resultado | Nota |
|---|---|---|
| T01 Arranque do servidor | OK | |
| T02 BOX encontra o serviço | OK | |
| T03 Botões de transporte | OK | |
| T04 Capa do álbum | OK | 28800 bytes |
| T05 Progresso temporal | OK | |
| T06 Pergunta simples | OK | ver latências abaixo |
| T07 Comando de transporte | OK | tool call `next`, faixa mudou |
| T08 Follow-up sem wake word | OK | |
| **T09 Jarvis + silêncio** | **FALHA** | **B1 confirmado — ver abaixo** |
| T10 Comando longo | OK | corte exacto a 12,00 s / 384000 bytes |
| T11 Servidor reinicia | OK (informal) | recuperou sozinho por mDNS várias vezes |
| T12 Auto-activação | — | critério da Fase 3, não medido |
| T13 Falso positivo em ruído | — | critério da Fase 3, não medido |
| T14 Pesquisa e reprodução | FALHA | por desenho, não implementado |
| T15 Volume | FALHA | por desenho, não implementado |

### Latências medidas

Do `END enviado` ao `A reproduzir resposta`:

| Tipo de turno | Medições | Intervalo |
|---|---|---|
| Primeiro turno (abre sessão Gemini) | 3,79 s · 4,88 s · 2,65 s | **2,7 – 4,9 s** |
| Follow-up (reutiliza sessão) | 1,02 s · 1,22 s | **1,0 – 1,2 s** |

A reutilização da sessão Gemini vale cerca de **3 segundos por turno**. É o número a defender em qualquer alteração futura ao ciclo de vida da conversa.

### T09 — o que realmente acontece

```
I (592353)  >>> JARVIS DETETADO <<<
W (596353)  Comando cancelado: nenhuma fala apos Jarvis     ← timeout de 4 s, correcto
I (596353)  CANCEL enviado ao servidor Live
I (596363)  Interacao de voz concluida com sucesso           ← a BOX lê "sucesso"
I (596383)  Turno concluido; conversa continua ativa
I (596383)  Conversa ativa; a aguardar nova fala sem Jarvis... ← WakeNet desligado
...
I (607393)  >>> FOLLOW-UP DETETADO SEM JARVIS <<<            ← o 2.º "Jarvis", 11 s depois
```

O segundo "Jarvis" **não** rearmou a palavra de acordar. Foi tratado como fala de
follow-up e transmitido ao Gemini como se fosse um comando.

**A formulação correcta do sintoma não é "a BOX fica surda".** Ela continua a
responder — deixa é de **exigir** a palavra de acordar, indefinidamente. Do lado
do servidor, o CANCEL termina a conversa e volta ao ciclo de espera sem enviar
`SLEEP`, e o estado `WAIT_FOLLOWUP_SPEECH` da BOX não tem timeout local. A partir
daí qualquer som que active o VAD abre um turno e é enviado para o Gemini.

Visto assim é pior do que parecia: não é perda de funcionalidade, é perda do
portão de privacidade.

Guardar o `log-servidor.txt` e o output do monitor de cada execução numa pasta
`testes/<data>/`. É o que permite comparar dois dias diferentes.

---

## Baseline 2 — 2026-09-27

Firmware `543f6ae` · Servidor: Fases 1.2, 1.3 e 1.4
Medido com `python ver_turnos.py` sobre 32 turnos reais.

### Latência

```
                                total    modelo    n
  1.º turno (abre sessão)      3.53 s    2.95 s    5
  follow-up (reutiliza)        1.10 s    1.09 s    22
```

Contra a Baseline 1 (2,7–4,9 s e 1,0–1,2 s): **sem regressão**. A reutilização
da sessão Gemini vale ~2,4 s por turno e continua a ser o número a proteger.

A coluna `modelo` desconta o tempo passado dentro das ferramentas (mediana
0,82 s). Sem essa separação, um turno com `spotify_control` e outro sem
ferramenta não são comparáveis — foi o erro de medição cometido na 1.3.

### Resultados

| Teste | Estado |
|---|---|
| T01–T08, T10, T11 | OK |
| T09 | **OK** — corrigido na Fase 1.1 |
| T14, T15 | falha esperada (Fase 2) |
| T16 | OK |
| T17 | por repetir em condições — ver a nota do próprio teste |
| T18 | **OK** — `"Não, obrigado. É tudo."` fechou a conversa |
| T19 | **OK** — `"Obrigado por teres passado a música."` **não** fechou |
| T20 | OK — 166 400 e 182 420 bytes em duas execuções |
| T21 | **FALHOU e foi corrigido** na mesma sessão |
| T12, T13 | ver abaixo |

### T12/T13 — mediu-se sem se ter medido de propósito

O registo de turnos deu o primeiro número do problema F3/3.2:

**5 dos 27 turnos concluídos (19%) correram até ao fim sem o Gemini transcrever
nada.** Ninguém falou; o VAD disparou sozinho e, em follow-up, o WakeNet está
desligado.

Pormenor que aponta para a causa: a transcrição `"¿Qué es esto?"` aparece
**duas vezes**, em sessões separadas (14:08:15 e 17:51:08). Ruído ambiente
aleatório não produz duas vezes a mesma transcrição. É mais compatível com uma
fonte acústica repetida — provavelmente a cauda da própria voz da BOX, que sem
AEC não há nada a filtrar.

Isto passa a ser o critério de aceitação da Fase 3.2: **19%, medido.**

---

## Baseline 3 — 2026-10-06 · fecho da Fase 2

Servidor: `spotify_client.MERCADO`, `send_command` 2xx, `action_service` sem
salto HTTP · Firmware: `VOICE_SPEAKER_VOLUME`

Uma única sessão de voz, seis turnos:

```
17:27:26  Mudar de música.                              next        -> ok
17:27:53  Agora eu preciso que me metas o Let It
          Happen do Tame Impala.                        play_search -> ok
17:28:05  Agora mete o volume a 60%.                    set_volume  -> ok
17:28:40  (pergunta normal, sem ferramenta)                         -> ok
17:28:48  Nada, podes retirar.                          end_conv.   -> ok
```

### Resultados

| Teste | Estado | Nota |
|---|---|---|
| T22 Pôr a tocar por nome | **OK** | `play_search`, `tipo: track`, faixa certa |
| T23 Tipo correcto | **OK** | 14-10: artist, track e album; `context_uri` em campo |
| T24 Sem dispositivo activo | **OK** | 14-10: 404 NO_ACTIVE_DEVICE, dito em voz alta |
| T25 Pesquisa sem resultados | **OK (simulado)** | a API nunca devolve vazio — ver o teste |
| T26 Volume por voz | **OK** | 60% |
| T27 Transporte devolve 2xx | **OK** | `next -> ok`; era `FALHOU / erro 200` |
| T28 Pesquisa (diagnóstico) | **OK** | quatro variantes a 200 |
| T14, T15 | **substituídos** | eram "não implementado"; passam a T22 e T26 |

### F4 — a pesquisa acerta sempre, mesmo quando devia falhar

Dois dos oito turnos de 14-10 puseram a tocar uma coisa que não foi pedida, sem
nenhum sinal de que algo tinha corrido mal:

```
tu:     Puente Canakkale
jarvis: A tocar Çanakkale de CVRTOON.
tool:   play_search({'query': 'Canakkale', 'tipo': 'track'}) -> ok
        (o Dinis corrigiu no turno seguinte: "Desculpa, é Takanaka")

tu:     Pon agora a tocar Timbalada.
tool:   play_search({'query': 'Tame Impala', 'tipo': 'artist'})
```

O segundo é o mais sério, e não é da pesquisa: o utilizador disse **Timbalada**
— que é uma banda real — e o modelo enviou **Tame Impala**, por ser o que se
andava a tocar. Uma substituição silenciosa, antes de a pesquisa sequer começar.

Juntando ao que o T25 mediu (a API nunca devolve vazio), há dois caminhos para o
mesmo sintoma:

| Onde | O que acontece |
|---|---|
| no modelo | troca o nome mal percebido por um parecido que tem em contexto |
| no Spotify | devolve sempre o mais próximo, por muito distante que seja |

Em nenhum dos dois há como o sistema dizer "não tenho a certeza". O `ok` é
sempre `True`, a resposta é sempre convicta, e a correcção fica toda do lado do
utilizador — que tem de ouvir a música errada para perceber.

**2 em 8 turnos nesta sessão.** É um número pequeno e de uma sessão só, mas é o
primeiro que existe. Fica como critério para uma fase própria.

> **Correcção, 2026-10-14 (à noite) — o número acima está mal construído, e o
> F4 é muito menor do que eu escrevi.**
>
> Fui contar o histórico inteiro em vez de uma sessão. Das **14** chamadas
> `play_search` que existem, **6 nunca chegaram a tocar nada** (cinco mortas
> pelo 403 da pesquisa, uma pelo 404 sem dispositivo). Sobram **8** que
> puseram mesmo música a tocar.
>
> Dessas 8, **uma** tocou a coisa errada: o Çanakkale. E a causa dessa é a
> **A** — a transcrição ouviu outra coisa — que esta fase não resolve nem
> pretende resolver.
>
> Os dois casos que eu tinha classificado como substituição a sério nunca
> chegaram ao altifalante: o Timbalada morreu no 404 e o soletrado no 403.
> Nenhum deles foi uma música errada que alguém tenha ouvido.
>
> E o Timbalada tem contexto que eu não tinha olhado: aconteceu **um turno
> depois** de o Dinis ter dito *"põe o álbum Currents do Tame Impala"*. O
> modelo tinha o nome fresco e um "Timbalada" foneticamente próximo. Em uso
> normal essa sequência não acontece — foi a própria sessão de testes a
> fabricá-la.
>
> Contado assim, o F4 é **1 em 8**, de causa indetectável. O Dinis disse que
> em uso normal funciona na grande maioria das vezes, e os dados dão-lhe
> razão.
>
> É o mesmo padrão da Fase 3.2: um sintoma que parecia do sistema e era
> artefacto das condições de medição. A diferença é que desta vez custou um
> documento de desenho, não uma semana de hipóteses erradas.
>
> **O que fica:** a 4.a já está feita e não custa nada — é só registo. Deixa
> de haver razão para a 4.b e a 4.c até os dados de uso real mostrarem alguma
> coisa. A prioridade passa para a **Fase 3.1**.

### O que este baseline não prova

- **T22 só foi exercitado com `tipo: track`.** Artista e álbum usam
  `context_uri` e não `uris` — é outro ramo do código, e continua por testar em
  campo.
- **O `PYTHONIOENCODING=utf-8`** foi posto para o `UnicodeEncodeError` que matou
  um turno a 10-03 (transcrição em devanágari). Não voltou a aparecer, mas
  também não voltou a aparecer devanágari: está corrigido por construção, não
  por observação.
- **Turnos sem fala reconhecida** (F3) não foram medidos nesta sessão — seis
  turnos não dão número nenhum.

### Latência

Sem medição nova com `n` suficiente. Os valores desta sessão
(`1.º áudio` entre 3,3 e 9,4 s nos turnos com ferramenta) estão dentro do
esperado, mas seis turnos não substituem a Baseline 2.

Nota sobre o turno das 17:27:53: 9,37 s, dos quais 3,28 s em ferramenta. É o
turno mais lento dos seis, e é o `play_search` — duas chamadas à API do Spotify
(pesquisa + reprodução) em vez de uma. Vale a pena voltar a medir com mais
amostras antes de decidir se é para optimizar.
