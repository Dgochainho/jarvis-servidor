# Fase 2.1 — uma só lista de acções

**2026-10-20** · Documento de desenho. Escrito antes do código, como as outras.

---

## O problema, medido

O `CLAUDE.md` dizia "o `action_service` duplica os endpoints do Flask". Contado
a 2026-10-20, são **três** listas, não duas:

| Onde | O quê | Quem chama |
|---|---|---|
| `COMANDOS_SIMPLES` em `action_service.py` | pause / resume / next / previous → método e endpoint do Spotify | a voz (Gemini) |
| `SPOTIFY_ACTIONS` em `jarvis_live.py` | o enum das 7 acções que o Gemini vê, a coincidir à mão com os `if` de `execute_spotify_action` | o Gemini |
| `/api/play`, `/api/pause`, `/api/next`, `/api/previous` em `app.py` | o mesmo método e endpoint, escritos outra vez | os botões da BOX **e** a página web |

Já divergem em duas coisas:

- **Nome.** O botão chama `/api/play`; a voz chama `resume`. Os dois fazem
  `PUT /me/player/play`.
- **Tratamento de erro.** A voz passa pelo `_registar_recusa`; os botões
  devolvem o `send_command` em bruto. Uma recusa do Spotify a um botão não deixa
  nenhuma linha `[ACCAO]` no log — é o mesmo buraco que deixou os
  `next -> FALHOU` de 09-30 e 10-03 sem investigação possível.

## Os dois contratos dos botões

Os endpoints dos botões têm **dois** clientes, e cada um lê uma coisa diferente:

| Cliente | O que lê | Onde |
|---|---|---|
| BOX | **só o código HTTP**: 2xx é sucesso, o corpo é ignorado | `display_LCD.c`, `spotify_send_command` |
| página web | **só o campo `success`** do corpo JSON | `templates/index.html`, `sendCommand` |

## Um defeito latente que a medição encontrou

Hoje a rota devolve o código do próprio Spotify: `jsonify(data), 204`. Medido
com a Flask 3.1.3 desta máquina: **uma resposta 204 sai com o corpo vazio.** O
`response.json()` da página web rebenta, cai no `catch`, e o botão da página
dá-se por falhado depois de o comando ter corrido.

Não se tem visto porque o Spotify anda a devolver 200: nos logs desde 30-09 os
botões receberam **37 × 200, 2 × 404, 0 × 204**. Mas o 204 foi o que veio
"durante meses" (ver o T27), e volta quando o Spotify quiser.

## Decisões

**D1 — o `action_service` é a única fonte.** Exporta `ACCOES`, a lista de
todas as acções, tirada da própria tabela de despacho. O `jarvis_live.py` deixa
de ter lista sua: `SPOTIFY_ACTIONS = ACCOES`.

A descrição de cada acção para o Gemini fica onde está, no `jarvis_live.py`,
porque é texto de prompt e não código. O que a protege de divergir é o teste
(T31), não uma verificação no arranque — partir o arranque por causa de uma
frase seria pior do que o defeito.

**D2 — os botões delegam no `action_service`.** Os URLs ficam exactamente como
estão: são contrato com o firmware, e mexer-lhes obrigava a mexer nos dois
lados. Cada rota passa a ser um nome de acção:

| URL | acção |
|---|---|
| `/api/play` | `resume` |
| `/api/pause` | `pause` |
| `/api/next` | `next` |
| `/api/previous` | `previous` |

A tabela de método e endpoint passa a existir **uma vez**, no `COMANDOS_SIMPLES`.

**D3 — o código HTTP do botão.**

- **Sucesso → sempre 200**, nunca o código do Spotify. A BOX aceita qualquer
  2xx, por isso não perde nada; a página web passa a ter sempre corpo. Mata o
  defeito do 204.
- **Recusa → o código do Spotify passa** (404, 403, 401…). A BOX regista
  `Resposta ao comando: HTTP 404`, e isso é a única pista que fica do lado do
  firmware — não se troca por um 502 genérico.
- **Excepção → 500**, com corpo. Antes era o 500 da Flask, sem corpo.

**D4 — o corpo do botão.** `{"success": …, "action": …, "message": …}`. O
`success` mantém-se pelo contrato da página web; o resto é o que a voz já
devolve, e vem de borla.

**D5 — a interface da voz não muda.** `execute_spotify_action` continua a
devolver só o dicionário, com os mesmos campos. Muda só por dentro: o
`_executar_comando_simples` passa a devolver também o código, e quem o chama
pela voz deita-o fora.

## O que fica igual

O `/api/status`, o `/api/voice`, o firmware, o enum que o Gemini vê (mesmos
sete valores, mesma ordem) e as frases que o Jarvis diz.

## Como se prova

**T31 — uma só lista de acções** (novo; sem a BOX, sem rede):

- o `SPOTIFY_ACTIONS` do `jarvis_live` **é** o `ACCOES` do `action_service`;
- cada acção tem uma linha `- nome:` na descrição que o Gemini vê;
- cada botão chama o método e endpoint certos, por um `send_command` simulado;
- com o Spotify a devolver **204**, o botão responde 200 com `success: true`;
- com o Spotify a devolver **404**, o botão responde 404 com `success: false`
  e a recusa fica no log.

**T03** (botões de transporte, com a BOX) e **T07 / T27** (transporte por voz)
correm depois, para provar que nada regrediu.
