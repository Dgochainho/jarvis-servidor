# Jarvis — servidor

Serviço local que faz de ponte entre a ESP32-S3-BOX-3 e o Spotify, e que
hospeda a conversa de voz com o Gemini Live.

**Escreve em português de Portugal** — código, comentários, logs e mensagens de
commit. O projecto inteiro está assim.

---

## Arrancar

```powershell
.\iniciar-servidor.ps1
```

⚠️ **Nunca corras `python app.py` com a saída no terminal.** Medido a
2026-09-30: com a saída na consola o processo bloqueia à espera que o terminal
aceite o texto, ninguém lê o WebSocket, e a BOX estoira o timeout de envio de
PCM. Parece rede má e não é. O `Tee-Object` tem exactamente o mesmo defeito,
porque também escreve na consola.

O Python é o do venv: `.\.venv\Scripts\python.exe`.

---

## O método deste projecto

Sete fases fechadas assim. É para manter.

1. **Documento de desenho antes do código.** Decide-se por escrito, discute-se,
   só depois se implementa.
2. **Medir antes de construir.** Cinco vezes um sintoma que parecia do sistema
   era artefacto das condições de medição. Quando uma hipótese não tem número,
   o primeiro passo é o instrumento, não a correcção.
3. **Nada se reescreve quando a realidade contraria.** A correcção vai numa
   nota em citação, datada, dentro do próprio documento. O rasto do raciocínio
   vale mais do que um documento limpo.
4. **Nenhum limiar se escolhe com dois casos.** Já custou um documento de
   desenho inteiro, na Fase 4.
5. **Uma fase pode fechar sem código**, se a medição mostrar que o problema não
   era o que se pensava. Já aconteceu três vezes.

---

## Armadilhas que já morderam

| | |
|---|---|
| `/api/status` | está no ciclo de polling da BOX, de 5 em 5 s, e tem medição `[PERF]` desde a Fase 1.3, comparável com as baselines de Setembro. **Não lhe acrescentes trabalho.** |
| `send_command` | aceita **2xx**, não só 204. O Spotify devolve 200 em endpoints que a documentação promete 204, e tratar isso como recusa fez o Jarvis pedir desculpa por coisas que tinha feito |
| `MERCADO = "PT"` | escrito à mão de propósito. O `market=from_token` manda o Spotify ver o país da conta, exige o scope `user-read-private` e devolve 403 |
| pesquisa do Spotify | **nunca devolve vazio.** Pedir uma música que não existe põe a tocar a mais parecida, com toda a convicção. Medido com sete strings aleatórias nos quatro tipos |
| `turnos.jsonl` | fora do git — contém transcrições de tudo o que foi dito |
| `.env` | não o leias para o contexto nem o imprimas |

---

## Testes

O `TESTES.md` é o guião: 30 testes e cinco baselines. Correr antes e depois de
cada fase, e registar no fim do ficheiro.

**Os números dos testes não se reutilizam.** Já houve uma colisão em T22-T24 e
deu trabalho a desfazer.

Os que correm sem a BOX ligada:

```powershell
.\.venv\Scripts\python.exe teste_sem_resultados.py     # T25
.\.venv\Scripts\python.exe diagnostico_pesquisa.py     # T28
python teste_fallback_http.py                          # T20
.\.venv\Scripts\python.exe teste_accoes_unicas.py      # T31
.\.venv\Scripts\python.exe teste_registo_capas.py      # T32
.\.venv\Scripts\python.exe teste_tema.py               # T33
.\.venv\Scripts\python.exe teste_api_tema.py           # T34
.\.venv\Scripts\python.exe teste_letras.py             # T36
.\.venv\Scripts\python.exe teste_visual.py             # T37
```

E o instrumento da 8.d, que **fala com o LRCLIB** (manda nomes de faixas do
`capas.jsonl`): `diagnostico_letras.py`. Não guarda nem imprime letras.

---

## Estado

Fases 0, 1, 2, 2.1, 3.2, 5, 7 e 8.b fechadas. A **Fase 8 — camada visual** está aberta:
a 8.a (paleta da capa) está feita e vista a funcionar — `/api/paleta` e a
página `/paleta`.

A **Fase 2.1** — uma só lista de acções — está fechada (2026-10-20, desenho em
`docs/FASE-2.1-desenho.md`). Os botões e a voz passam pela mesma tabela do
`action_service`; o enum do Gemini vem de `ACCOES`. **Uma acção nova entra no
`action_service` e em mais lado nenhum** — a não ser a sua linha na descrição
do `jarvis_live`, que o T31 verifica.

A **8.b** — a capa dá cor ao LCD — está fechada (2026-10-20, desenho em
`docs/FASE-8.b-tema.md`). O `tema_service.py` calcula cinco cores a partir da
paleta, com o contraste garantido; o `/api/tema` serve-as à BOX, que as pede
uma vez por cada capa nova. O `capas.jsonl` continua a juntar capas, e a página
`/tema` mostra o LCD simulado para todas — **para comparar regras, não para
prever a cor exacta: o LCD não mostra as cores como o browser.** O tema neutro
existe nos dois lados; o T34 compara-os.

A **8.d** — letras sincronizadas — está feita do lado do servidor (2026-10-20,
desenho em `docs/FASE-8.d-letras.md`). O `lyrics_service` busca ao LRCLIB e
parte em filas de 21; o `visual_service` faz push em `:8766/visual` com as
mensagens do PDF de 12-10; a página `/matriz` é o nó, no browser, até haver
hardware. O T38 passou de ouvido; falta anotar o valor do offset afinado. O que
resta é o nó verdadeiro, quando o Matrix Portal chegar — e herda as regras do
cabeçalho do `pagina_matriz.py`.

| | |
|---|---|
| `fontes/fonte_5x8.json` | **a mesma fonte nos três lados** — servidor, matriz virtual, nó. O que não está nela não chega ao nó |
| `letras_cache/` | fora do git: é texto de terceiros, para uso pessoal. **Letra real nunca entra no repositório**, nem nos testes |
| porta 8766 | se estiver ocupada, o arranque falha (B5), como a 8765 |

Fora da lista, por decisão de 2026-10-20: o **sono do PC**, porque o servidor
vai deixar de viver no portátil.

---

## O outro lado

O firmware vive em
`C:\Users\dgoch\Desktop\ProjetoAss Istant\projetos\hello_world`, e no GitHub em
`Dgochainho/jarvis-firmware` (privado, desde 2026-10-20). As credenciais do
Wi-Fi estão no `main/wifi_credenciais.h`, fora do git.

Os dois lados partilham um contrato de mensagens: **WAKE / START / PCM / END /
CANCEL** da BOX para o servidor, **READY / PCM / DONE / SLEEP / ERROR** do
servidor para a BOX. Mexer num lado sem o outro parte a voz.
