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

**Sair do monitor: `Ctrl+T` seguido de `Ctrl+X`.** (O `Ctrl+]` da documentação
também serve, mas no teclado português o `]` é AltGr+9 e o atalho fica
desconfortável.) **Não fechar a janela no X** — deixa o processo agarrado ao
COM9 e a gravação seguinte falha com *acesso negado*.

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

⚠️ A 2026-10-16 o `Servidor Live pronto` **não apareceu** num arranque, e a BOX
recriou o WebSocket aos 10 s apesar de já estar ligada. É a Fase 7, por fazer.

> **2026-10-19 — Fase 7 fechada.** Quatro arranques seguidos com o READY a
> chegar em ~220 ms. A causa provada foi o servidor recusar a ligação nova
> enquanto segurava a antiga, já morta: o `close(1013)` é um fecho limpo, e um
> fecho limpo matava o cliente WebSocket da BOX de vez. Corrigido dos dois
> lados — ver o T30 e a Baseline 5.
>
> **O arranque de 16-10 em si continua sem explicação fechada:** o log do
> servidor desse dia mostra `READY enviado` nessa ligação, o que não encaixa
> com uma recusa. O instrumento para o apanhar, se voltar, está montado.

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

> **2026-10-16 — estes dois já não são critério de fase nenhuma.** A Fase 3.1
> nunca chegou a abrir: medidos 155 turnos, só 3 caíram durante a própria
> resposta da BOX. A Fase 3.2 ficou aceite por decisão do Dinis — o resto é som
> externo, e não se pede ao programa que ignore conversas alheias sem estragar
> a recepção. O T12 e o T13 continuam a correr-se como observação.

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

### T29 · Escada da wake word

**Não é um teste de passa/falha. É a medição contra a qual a Fase 6 se mede.**

Com a BOX ligada e o indicador de escuta visível (Fase 5), sempre **à mesma
distância**, dizer "Jarvis" quinze vezes e contar quantas acendem verde:

| Degrau | Vezes | Como |
|---|---|---|
| normal | 5 | a voz com que falas com ele todos os dias |
| mais baixo | 5 | como quem não quer acordar ninguém |
| no limite | 5 | sussurro |

Registar **os três números separados**, não o total. O que interessa não é a
taxa global — é se o degrau de baixo se comporta pior do que o de cima.

**Porque é que isto existe:** até à Fase 5 não havia maneira de contar wake
words falhadas. Uma que não dispara não deixa rasto no `turnos.jsonl`, no log
do servidor, nem em parte nenhuma. O indicador é o único instrumento possível,
e esta escada é o que ele mede.

**Cuidado com a contaminação:** o indicador muda o comportamento de quem testa.
Saber imediatamente se resultou faz com que se aprenda a dizer "Jarvis" melhor,
e isso sobe a taxa sem que nada no firmware tenha mudado. Distância fixa reduz
o efeito; não o elimina. Em comparações futuras, desconfiar de melhorias
pequenas.

### T30 · Corte de alimentação à BOX ⚠️

**Tem de ser corte de corrente, não o botão de reset.** Com o reset o servidor
costuma dar pela morte da ligação antes de a BOX voltar, e o caminho que
interessa nem chega a ser percorrido — foi o que aconteceu a 19-10 e por pouco
não se dava o teste por feito sem o ter sido.

Com a BOX ligada e a funcionar, tirar-lhe a ficha e voltar a pô-la.

**Esperado**, no `log-servidor.txt`:

```
[VOICE-WS] Ligação nova de (...); a expulsar a anterior ((...))
[VOICE-WS] Ligação fechada: code=1006
[VOICE-WS] BOX desligada: (a antiga)
[VOICE-WS] BOX persistente ligada: (a nova)
[VOICE-WS] READY enviado
```

e no monitor o `Servidor Live pronto` em poucas centenas de ms, sem o
`WS sem CONNECTED+READY`.

**Falha se:** `Ligação recusada (1013): a anterior não largou o lugar em 5 s`.
A partir da Fase 7.d esse 1013 deixou de querer dizer *já existe uma BOX* e
passa a querer dizer *a anterior está presa* — é um sintoma novo, não o antigo.

**Porque é que o corte de corrente é o teste e o reset não:** sem corrente a
BOX não se despede, o servidor fica com o cadáver agarrado ao lugar até ao
timeout do ping (até ~40 s), e a BOX volta em ~6 s. É a única maneira fácil de
garantir que a ligação nova chega com o lugar ainda ocupado.

**O que NÃO se consegue ver neste teste:** a linha
`WebSocket Live fechado pelo servidor (codigo 1012)` no monitor. Quem leva com
o 1012 é a BOX antiga, que está sem corrente e não regista nada. Essa linha só
aparece se uma BOX *viva* for alguma vez substituída.

### T31 · Uma só lista de acções

Sem a BOX e sem rede, na pasta do servidor:

```powershell
.\.venv\Scripts\python.exe teste_accoes_unicas.py
```

Substitui o `send_command` por um falso e verifica que o enum do Gemini **é** a
lista do `action_service`; que cada acção tem a sua linha na descrição que o
Gemini lê; que cada botão (`/api/play`, `/api/pause`, `/api/next`,
`/api/previous`) chama o mesmo método e endpoint que a voz; e o que o botão
responde quando o Spotify devolve 204 e 404.

**Esperado:** `T31 PASSA`.
**Falha se:** qualquer linha `FALHA`. A mais importante é a do 204: antes da
Fase 2.1 o botão respondia 204 **sem corpo**, e a página web dava o comando por
falhado depois de ele ter corrido.

Não prova nada sobre a BOX. Para isso continua a haver o T03.

### T32 · Registo de capas

Sem a BOX e sem rede, na pasta do servidor:

```powershell
.\.venv\Scripts\python.exe teste_registo_capas.py
```

Simula o Spotify e a conversão da capa, e escreve num ficheiro temporário — o
`capas.jsonl` verdadeiro não é tocado. Verifica que uma capa nova fica
registada com a paleta e os nomes; que a mesma capa não se repete, nem depois
de um arranque novo; que nunca se regista a paleta da capa anterior; e que um
registo que falha não custa a capa à BOX.

**Esperado:** `T32 PASSA`.

### T33 · O tema cumpre as próprias regras

Sem a BOX e sem rede, na pasta do servidor:

```powershell
.\.venv\Scripts\python.exe teste_tema.py
```

Para cada capa do `capas.jsonl` e para nove casos extremos fabricados (preto,
branco, vermelho puro, o verde da barra de voz…), nas duas variantes, verifica
que o tema passa os dois contrastes depois de RGB565 ou diz que caiu no
recurso; que as cores são hex válido; que é determinístico. Verifica também as
contas de base (branco/preto = 21) e que parâmetros absurdos no URL da `/tema`
não partem nada.

**Esperado:** `T33 PASSA`.

Não diz se o tema é bonito nem se se lê a 3 m — isso é a página `/tema`, e
depois a BOX.

### T34 · `/api/tema`

Sem a BOX e sem rede, na pasta do servidor:

```powershell
.\.venv\Scripts\python.exe teste_api_tema.py
```

Simula o Spotify e a paleta. Verifica que a tocar devolve o tema da capa com o
URL dela; que sem reprodução, ou sem capa, devolve o neutro e diz que é; que
com o Spotify indisponível ou a paleta a falhar devolve um erro sem cores; que
a resposta cabe no buffer da BOX; e que o `TEMA_NEUTRO` do `display_LCD.c` é
igual ao neutro do servidor — lê o ficheiro do firmware e compara cor a cor.

**Esperado:** `T34 PASSA`. Se o firmware não estiver no sítio do `CLAUDE.md`,
o ponto 4 diz `NÃO VERIFICADO` em vez de passar.

### T35 · Tema da capa na BOX ⚠️

Com a BOX ligada e o firmware da 8.b gravado:

1. Mudar de música três ou quatro vezes, com capas bem diferentes (uma clara,
   uma escura, uma garrida).
2. Pausar até o Spotify deixar de ter reprodução activa.
3. Pôr a tocar uma faixa com nomes compridos.
4. Carregar num botão e manter.

**Esperado:**

- o fundo, o texto e os botões mudam com cada capa, em ≤5 s depois dela, e o
  monitor diz `Tema aplicado: fundo #…`;
- nunca se vê uma capa com o tema da anterior;
- sem reprodução, o tema neutro (fundo `#2e2e2e`);
- o texto dos botões lê-se;
- a linha `PLAYING   1:23 / 3:45` nunca fica por baixo dos botões;
- o botão premido muda de cor e deixa de crescer;
- a barra de voz continua com as cores dela.

**Falha se:** alguma destas não acontecer. O que não se vê no monitor: o
servidor não regista nada por cada tema servido além da linha do
`GET /api/tema`.

### T36 · `lyrics_service`

Sem rede, na pasta do servidor:

```powershell
.\.venv\Scripts\python.exe teste_letras.py
```

O LRCLIB é simulado e o LRC é **inventado para o teste** — letra real não
entra no repositório. Verifica a leitura do LRC (tempos repetidos, metadados,
`[offset:]`), a quebra em filas de 21, as regras do L2, a transliteração do
L3, os pedidos ao LRCLIB (duração, sufixos, 503 a 1-2-4 s), a cache e a
expiração do "não há".

**Esperado:** `T36 PASSA`.

### T37 · `visual_service`

Sem a BOX e sem rede externa, na pasta do servidor:

```powershell
.\.venv\Scripts\python.exe teste_visual.py
```

O Spotify, a paleta e o LRCLIB são simulados; o WebSocket é real, numa porta
livre. Verifica o relógio (âncora a meio do pedido, leitura lenta ignorada),
os campos das mensagens, o "sem letra" com título e artista, o que um cliente
recebe ao ligar e numa faixa nova, a recusa de um caminho errado e a falha do
arranque com a porta ocupada (B5).

**Esperado:** `T37 PASSA`.

### T38 · Letras na matriz virtual, de ouvido ⚠️

Com o servidor reiniciado, `http://localhost:8888/matriz` aberto, e música a
tocar:

1. Três músicas com letra, de ritmos diferentes.
2. Uma sem letra (uma das instrumentais do `capas.jsonl`).
3. Uma pausa, e uma retoma.
4. Um salto para o meio da música, no telemóvel.
5. Afinar o offset até a linha mudar com a voz, e anotar o valor.

**Esperado:** a linha muda com a voz, com um erro que não se nota; sem letra,
o título e o artista; a pausa e o salto corrigem-se em ≤ ~6 s (L5).

**Falha se:** a letra andar sistematicamente adiantada ou atrasada mais do que
o offset consegue compensar, ou se derivar ao longo da música.

O valor do offset é um resultado: se for longe de zero, a âncora do L4 está a
falhar por alguma razão que a medição não viu.

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

> **Corrigido a 2026-10-16.** A atribuição à cauda da própria voz da BOX estava
> errada. Medidos 155 turnos concluídos: 17 sem fala reconhecida (11%), e dos
> 11 com dados de tempo, **apenas 3 caíram durante a própria resposta**. Os
> outros são som externo — outras pessoas a falar na sala. Decisão do Dinis:
> aceitar. Não se pede ao programa que ignore conversas alheias sem estragar a
> recepção do resto.

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

---

## Baseline 4 — 2026-10-16 · wake word

Firmware: Fase 5 (indicador de escuta). Nada mudou no reconhecimento — o
indicador não toca no WakeNet. Esta baseline mede o que **sempre** lá esteve e
nunca tinha sido medido.

### T29 · escada

```
normal      4/5
mais baixo  5/5
no limite   4/5    (sussurro)
```

Mais uma série anterior, de exploração livre com o volume a variar: **17/20**.

**Total: 30 em 35 — cerca de 86%.** Duas séries independentes a concordar.
Aproximadamente **1 em cada 7 "Jarvis" falha.**

### O que a escada diz, e que contraria a hipótese de partida

**Não há gradiente de volume.** O sussurro foi tão bem como a voz normal.

Com uma taxa de fundo de 86%, um degrau de 5 tentativas dá 5/5 em 46% das vezes
e 4/5 em 39%. Um resultado de 4-5-4 é precisamente o mais provável se os três
degraus forem iguais. Não há ali sinal nenhum.

Isto derruba a hipótese em que assentava a ordem das alavancas da Fase 6. Se a
BOX ouve um sussurro, **não é um problema de nível** — o microfone e o AFE têm
folga de sobra, e o AGC, que existe para normalizar o nível, deixa de ser o
candidato óbvio.

O que resta é a queixa original: *"custa acertar com o tom"*. Um modelo
treinado com voz sintetizada (`wn9_jarvis_tts`) falha em **certas pronúncias**,
não em certos volumes — e o sintoma bate certo.

### Limite desta medição

Cinco tentativas por degrau só detectam um efeito grande. Se o degrau do
sussurro tivesse dado 1/5, era sinal; dar 4/5 não prova que não há efeito
nenhum, prova que não há um efeito grande.

Os 86% globais, esses, assentam em 35 tentativas e são o número a bater.

### Decisão

**Fase 6 suspensa.** O Dinis considerou o estado actual suficiente e não quis
mais alterações por agora. As alavancas ficam identificadas e por usar; os 86%
ficam como referência para quando se lhes pegar.

---

## Baseline 5 — 2026-10-19 · fecho da Fase 7

Firmware: `enable_close_reconnect` + log no `WEBSOCKET_EVENT_CLOSED` ·
Servidor: a ligação nova expulsa a anterior, e as recusas deixam de ser mudas

### Resultados

| Teste | Estado | Nota |
|---|---|---|
| T02 BOX encontra o serviço | **OK** | quatro arranques, READY em ~220 ms |
| T30 Corte de alimentação | **OK** | a expulsão disparou; ver abaixo |

### T30 — a prova

```
17:45:27  (último /api/status da BOX antiga)
          Ligação nova de (60613); a expulsar a anterior ((52039))
          Ligação fechada: code=1006
          BOX desligada: (52039)
          BOX persistente ligada: (60613)
          READY enviado
```

O `code=1006` aparece **depois** do nosso pedido de fecho: fomos nós que o
provocámos. Ou seja, o lugar estava mesmo ocupado pelo cadáver quando a BOX
nova chegou — o servidor ainda não tinha dado pela morte. Antes da 7.d aquela
primeira linha teria sido um `1013`, e antes da 7.b esse 1013 teria matado o
cliente da BOX e custado os 10 segundos.

### O que este baseline não prova

- **O arranque de 16-10 continua por explicar.** O log do servidor desse dia
  mostra `READY enviado` na ligação em causa, o que não encaixa com uma recusa
  por 1013. Corrigiram-se dois defeitos reais e provados; o sintoma original
  nunca chegou a ser reproduzido. A instrumentação da 7.a fica montada.
- **A 7.c não foi feita.** O `VOICE_WS_STALE_RECREATE_MS` de 10 s continua a
  ser a rede de segurança, e continua largo de mais para o arranque. Só deixou
  de ser preciso.
- **Os 95 s de mDNS de 18-10** não foram investigados. Aconteceram contra um
  servidor que tinha passado horas com o event loop bloqueado (o portátil a
  dormir). É hipótese, não conclusão, e é candidato a fase própria.

## Fase 2.1 — 2026-10-20 · uma só lista de acções

Desenho em `docs/FASE-2.1-desenho.md`.

### Resultados

| Teste | Resultado | Nota |
|---|---|---|
| T31 Uma só lista de acções | **OK** | 27 verificações, 0 falhas |
| T03 Botões de transporte | **OK** | 20-10 17:15: `<<` ×2, `>>` ×3, `pause` → `play`, todos 200; sem recusas `[ACCAO]` |
| T07 / T27 Transporte por voz | **OK** | 20-10 17:17: `next`, `pause` e `resume`, todos `-> ok` no registo |

### O que este registo não prova

- **Que a BOX não regrediu.** O T31 simula o Spotify e chama as rotas pela
  Flask; prova o contrato do lado do servidor, não o firmware. O firmware só lê
  o código HTTP e esse contrato mantém-se (sucesso passa de 200/204 a sempre
  200, ambos 2xx), mas fica por ver com o T03.

  > **2026-10-20 · visto.** O T03 correu com o servidor novo: o `pause`
  > seguido de `play` mostra que a BOX trocou o estado certo duas vezes.

### Observado de passagem, sem correcção

Um caso, por isso só fica registado. O reconhecimento ouviu **"Tchpausa a
música"** quando foi dito "despausa"; o Gemini chamou `pause` com a música já
em pausa, e o Spotify respondeu:

```
[ACCAO] pause recusado com 403: "Player command failed: Restriction violated"
```

O Jarvis disse "Não consegui pausar a música agora", quando a verdade era "já
está em pausa". Duas coisas a ver se se repetirem: o 403 de pausar o que já
está parado merece uma frase própria, e "despausa" pode precisar de um exemplo
na descrição do `resume`. A linha `[ACCAO]` com o corpo da recusa é o que
permitiu perceber isto no próprio dia.
- **O defeito do 204 nunca foi observado em campo.** Nos logs desde 30-09 os
  botões receberam 37 × 200, 2 × 404 e nenhum 204. Foi encontrado pela
  medição, não por um sintoma.

## Fase 8.b, passo 1 — 2026-10-20 · registo de capas

Desenho em `docs/FASE-8.b-tema.md`.

| Teste | Resultado | Nota |
|---|---|---|
| T32 Registo de capas | **OK** | 9 verificações, 0 falhas |
| T31 Uma só lista de acções | **OK** | repetido neste ramo |

Não prova que o registo corre em campo: isso vê-se na primeira capa nova com a
BOX ligada, pela linha `[CAPAS] Nova capa registada (1)` no log do servidor.

## Fase 8.b, passo 2 — 2026-10-20 · cálculo do tema e página `/tema`

| Teste | Resultado | Nota |
|---|---|---|
| T33 O tema cumpre as próprias regras | **OK** | 9 extremos + 52 capas, nas duas variantes; nenhum recurso |
| T31, T32 | **OK** | repetidos neste ramo |

Com os números de partida, os piores contrastes do corpus são texto 12,58,
botão/fundo 3,00, texto do botão 4,50 e texto premido 4,50 — os botões ficam
encostados aos mínimos, porque a procura escolhe a luminosidade mais próxima da
cor da capa que ainda passe. O tema de hoje, medido da mesma maneira: texto
4,22, botão/fundo 1,72, texto do botão 1,34.

## Fase 8.b, passo 3 — 2026-10-20 · a BOX aplica o tema

| Teste | Resultado | Nota |
|---|---|---|
| T34 `/api/tema` | **OK** | 15 verificações; neutro do firmware = do servidor |
| T31, T32, T33 | **OK** | repetidos |
| T35 Tema da capa na BOX | **OK** | tudo visto na BOX: "incrível, perfeito" |

A página `/tema` passou a desenhar o texto como a BOX (F6). Com as 57 capas do
corpus e a Montserrat carregada: 42 textos centrados, 16 a subir para não
chegar à linha de estado, nenhum cortado.

### T35 — o que a BOX mostrou

Corrido com o firmware `c5fdf9d` gravado e o servidor reiniciado. Todos os
pontos do teste passaram. A única ressalva, dita de passagem: **o LCD não é a
simulação** — as cores no ecrã da BOX diferem das da página `/tema` —, mas o
resultado no LCD foi julgado "muito bom". Não se mediu a diferença; fica
registada como facto, não como defeito.

> **2026-10-20 · o `c5fdf9d` passou a `752ae47`.** O histórico do firmware foi
> reescrito antes do primeiro push para o GitHub, para tirar a password do
> Wi-Fi do `wifi.c`. O código é o mesmo; só o identificador mudou.

## Fase 8.d — 2026-10-20 · letras sincronizadas, até à matriz virtual

Desenho em `docs/FASE-8.d-letras.md`. Medição prévia no `diagnostico_letras.py`:
63% das faixas do corpus com letra sincronizada, 33% sem letra no LRCLIB.

| Teste | Resultado | Nota |
|---|---|---|
| T36 `lyrics_service` | **OK** | 31 verificações |
| T37 `visual_service` | **OK** | 22 verificações, com WebSocket real |
| T31 a T34 | **OK** | repetidos |
| T38 Letras de ouvido | **OK** | julgado "muito bom", com o **offset a 0** |

O T36 falhou à primeira por um erro **do teste**: a frase escrita para ocupar
"exactamente três filas" ocupava quatro. E a verificação "três filas, uma
entrada" tinha passado por acaso, porque a linha foi dividida no tempo e a
primeira metade tinha três filas. Corrigidas as duas, e a verificação passou a
exigir que não haja divisão.

### T38 — o que ficou por medir

Passou de ouvido, com o servidor novo e a `/matriz` aberta. **O valor do offset
afinado não foi anotado**, e é ele que diz se a âncora do L4 acerta sozinha:
perto de zero, acerta; longe, há uma parte do atraso que a medição dos logs não
viu. Fica para a próxima sessão com música, antes de o nó verdadeiro herdar o
mesmo relógio.

> **2026-10-20 · anotado: o offset fica sempre a 0.** Não foi preciso mexer-lhe
> em nenhuma das músicas. A âncora a meio da ida ao Spotify chega sozinha, sem
> correcção de ouvido — e o nó pode herdar o relógio tal como está. Um aviso:
> isto foi com o browser no mesmo PC do servidor. No nó a ligação passa pelo
> Wi-Fi, e esse atraso, de dezenas de milissegundos, não entrou nesta conta.