# Guião de teste — ESP32-S3-BOX-3 / Spotify

Sempre os mesmos enunciados, sempre pela mesma ordem. Serve para responder a
uma pergunta e só a essa: **esta alteração melhorou ou piorou?**

Correr antes de cada fase e depois de cada fase. Registar no fim do ficheiro.

---

## Preparação

**Servidor** (PowerShell, na pasta `spotify-service`):

```powershell
python app.py 2>&1 | Tee-Object -FilePath "log-servidor.txt"
```

**BOX** (PowerShell, na pasta do firmware):

```powershell
idf.py -p COM9 monitor
```

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

### T18 · Fecho por voz *(Fase 1.4 — ainda não implementado)*
Fazer uma pergunta normal, ouvir a resposta e dizer **"obrigado, é tudo"**.

**Esperado:** o Jarvis despede-se, a despedida toca **inteira**, e o log mostra
`end_conversation` seguido de `SLEEP` e `DONE`. A BOX volta a exigir a palavra de
acordar imediatamente, sem esperar os 30 s.
**Falha se:** a BOX rearmar antes de a despedida acabar de tocar.

### T19 · Falso positivo de despedida *(Fase 1.4)*
Dizer **"obrigado por teres posto essa música"**.

**Esperado:** a conversa **não** termina.
**Critério de aceitação da Fase 1.4.**

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
