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

## Registo

Baseline esperada hoje: **T01–T08, T10, T11 passam · T09 falha (B1) · T12, T13 por medir · T14, T15 falham por desenho.**

| Data | Commit servidor | Commit firmware | T01 | T02 | T03 | T04 | T05 | T06 | T07 | T08 | T09 | T10 | T11 | T12 | T13 | T14 | T15 | Latência T06 | Notas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | | | | | | | | | |

Legenda: `OK` · `FALHA` · `—` (não aplicável) · `?` (inconclusivo)

Guardar o `log-servidor.txt` e o output do monitor de cada execução numa pasta
`testes/<data>/`. É o que permite comparar dois dias diferentes.
