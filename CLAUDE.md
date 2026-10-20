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
```

---

## Estado

Fases 0, 1, 2, 3.2, 5 e 7 fechadas. A **Fase 8 — camada visual** está aberta:
a 8.a (paleta da capa) acabou de ser escrita — `/api/paleta` e a página
`/paleta`.

Em aberto, sem pressa:

- **Fase 2.1** — o `action_service` duplica os endpoints do Flask, e as listas
  de acções já divergiram uma vez
- **o sono do PC** — o event loop bloqueia horas quando o portátil adormece
  (`50396.8 s` num caso medido), e o aviso que aparece culpa o QuickEdit, que é
  a causa errada

---

## O outro lado

O firmware vive em
`C:\Users\dgoch\Desktop\ProjetoAss Istant\projetos\hello_world`.

Os dois lados partilham um contrato de mensagens: **WAKE / START / PCM / END /
CANCEL** da BOX para o servidor, **READY / PCM / DONE / SLEEP / ERROR** do
servidor para a BOX. Mexer num lado sem o outro parte a voz.
