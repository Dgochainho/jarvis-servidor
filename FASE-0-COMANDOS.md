# Fase 0 — comandos a correr

Tudo o que é ficheiro já está no sítio. Falta o que precisa de shell.
Correr por esta ordem: a ordem é o que protege os segredos.

---

## 1 · Confirmar o git (uma vez só)

```powershell
git --version
git config --global user.name
git config --global user.email
```

Se o nome ou o email vierem vazios:

```powershell
git config --global user.name "Dinis"
git config --global user.email "ai@lobais.com"
```

---

## 2 · Repositório do servidor

O `.gitignore` e o `requirements.txt` já lá estão.

```powershell
cd C:\Users\dgoch\Scripts\spotify-service

git init
git add .
git status
```

**PARAR AQUI E CONFERIR.** Na lista de ficheiros a commitar **não** pode
aparecer nenhum destes:

- `.env`
- `.spotify_token.json`
- `.venv/`
- `command.wav`, `gemini_live_reply.wav`, `cover.rgb565`

Se algum aparecer, não commitar — diz-me e corrijo o `.gitignore` primeiro.
Depois de entrarem no histórico, tirá-los de lá é bem mais trabalhoso.

Se a lista estiver limpa:

```powershell
git commit -m "Estado funcional: voz Gemini Live por WebSocket + controlo Spotify"
git tag -a v0-funcional -m "Baseline antes da Fase 1"
```

---

## 3 · Repositório do firmware

### 3.1 Guardar o `.gitignore`

Não consigo escrever nesta pasta — está dentro de `.vscode`, e as ferramentas
remotas recusam esse caminho. Guarda o ficheiro que te envio no chat como:

```
C:\Users\dgoch\Desktop\ProjetoAss Istant\projetos\.vscode\hello_world\.gitignore
```

(substitui o que lá está)

### 3.2 Commit no sítio onde está

Ainda **não** mexer na pasta. Primeiro garantir o ponto de retorno.

```powershell
cd "C:\Users\dgoch\Desktop\ProjetoAss Istant\projetos\.vscode\hello_world"

git init
git add .
git status
```

**CONFERIR:** não pode aparecer `build/` nem `managed_components/`.
Devem aparecer ~40 ficheiros, incluindo `sdkconfig` — esse é de propósito
(é onde vive a seleção do modelo da wake word).

```powershell
git commit -m "Estado funcional: WakeNet Jarvis + streaming WebSocket + UI Spotify"
git tag -a v0-funcional -m "Baseline antes da Fase 1"
```

---

## 4 · Tirar o firmware de dentro do `.vscode`

Só depois do commit acima. Com o baseline guardado, isto passa a ser reversível.

Porquê: enquanto o projeto estiver dentro de `.vscode`, eu não consigo escrever
lá nada — nem `.gitignore`, nem correções de código. A Fase 1 mexe no
`voice.c`. Sem isto, tudo o que eu fizer no firmware tem de passar por ti a
copiar ficheiros à mão.

```powershell
cd "C:\Users\dgoch\Desktop\ProjetoAss Istant\projetos"
Move-Item ".vscode\hello_world" "hello_world"
```

O `.git` vai junto — o histórico e a tag não se perdem.

**A seguir, obrigatoriamente:** a cache do CMake guarda caminhos absolutos, por
isso o build antigo fica inválido.

```powershell
cd hello_world
idf.py fullclean
idf.py build
```

Demora (esp-sr e lvgl recompilam do zero). Se o build passar, está tudo bem.

Por fim, no Claude: **Add folder** →
`C:\Users\dgoch\Desktop\ProjetoAss Istant\projetos\hello_world`
(e podes remover a ligação antiga, que deixou de existir)

---

## 5 · Ambiente Python limpo

O `.venv` que está na pasta está obsoleto — tem Flask e requests, mas não tem
`google-genai`, `websockets`, `pillow`, `zeroconf` nem `pydantic`. O servidor
está a correr do Python global. É isso que vai partir quando migrares para o
servidor definitivo.

```powershell
cd C:\Users\dgoch\Scripts\spotify-service

Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Arrancar o servidor a partir deste ambiente e correr o `TESTES.md` até ao T08.
Se passar, fixar o lock:

```powershell
pip freeze > requirements-lock.txt
git add requirements-lock.txt
git commit -m "Lock de dependencias a partir de ambiente limpo"
```

---

## 6 · Rotação de chaves

Só tu consegues fazer isto. O `.env` e o `.spotify_token.json` estiveram
carregados como documentos do Projeto (já os apaguei de lá).

- **Spotify** — Developer Dashboard → a tua app → Settings → *Rotate client secret*.
  Atualizar o `SPOTIFY_CLIENT_SECRET` no `.env`.
- **Gemini** — Google AI Studio → API keys → criar nova, apagar a antiga.
  Atualizar o `GEMINI_API_KEY` no `.env`.

Depois de rodar, reiniciar o servidor. Se o refresh token do Spotify deixar de
servir, basta ir a `/login` uma vez.

---

## 7 · Baseline

Correr o `TESTES.md` de ponta a ponta e preencher a primeira linha da tabela.
A partir daqui, qualquer alteração é comparável.

Esperado hoje: **T09 falha** (é o bloqueador B1, e é o alvo da Fase 1.1) ·
**T14 e T15 falham** por ainda não estarem implementados · tudo o resto passa.

---

## Depois disto (opcional, agora seguro)

Com o commit feito, estes ficheiros deixaram de ser precisos — estão no
histórico e recuperam-se com `git show`:

**Servidor:** `app_WORKING_BACKUP.py` · `gemini_live_service_backup.py` ·
`live_voice_ws_server_backup.py` · `live_voice_ws_server_backup_2.0.py` ·
`live_voice_ws_server_nworking_backup.py`

**Firmware:** `voice_backup.txt` · `voice_backup_1.2.c` · `voice_backup_1.2.2.c` ·
`voice_backup_1.3.c` · `voice_backup_1.4.c` · `voice_backup_1.5.c` ·
`display_LCD_backup.c` · `main.c.c` · `hello_world_main.c`

Nenhum destes é compilado (o `main/CMakeLists.txt` só regista `display_LCD.c`,
`wifi.c` e `voice.c`), por isso apagá-los não afeta o build.
