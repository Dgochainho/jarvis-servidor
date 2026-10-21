# Instalar o servidor na torre

Fase 9 · guia passo a passo. O porquê de cada passo está no
`docs/FASE-9-servidor.md` (decisões M1 a M6); aqui só o que se faz.

Assume Ubuntu Server 24.04 LTS ou Debian 13 já instalado, com acesso por SSH
ou teclado, e um utilizador com `sudo`. Os comandos são para correr na torre,
excepto onde diz **no portátil**.

---

## 0. Antes de começar

- [ ] A torre tem **outro nome** na rede que não `spotify-service` (M4). Ver
      com `hostname`; mudar com `sudo hostnamectl set-hostname torre-jarvis`.
- [ ] Ligada **por cabo**, se der (M2).
- [ ] Na **BIOS**: ligar sozinha quando volta a corrente — costuma chamar-se
      *After Power Loss* ou *AC Power Recovery*, em *Power On* (M5).

## 1. Pacotes e utilizador

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
python3 --version          # 3.12 ou mais recente
sudo adduser --disabled-password --gecos "" jarvis
```

## 2. O código

```bash
sudo -iu jarvis
git clone https://github.com/Dgochainho/jarvis-servidor.git
cd jarvis-servidor
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

O repositório é privado: o `git clone` pede autenticação. A forma mais simples
é um token pessoal do GitHub só de leitura, para este repositório.

## 3. Os segredos e os dados (M3)

**No portátil**, numa PowerShell na pasta do servidor, depois de saber o IP da
torre (`hostname -I` na torre):

```powershell
scp .env .spotify_token.json capas.jsonl jarvis@IP-DA-TORRE:~/jarvis-servidor/
scp -r letras_cache jarvis@IP-DA-TORRE:~/jarvis-servidor/
```

**Não** vão: o `turnos.jsonl` (decidido — a torre começa um registo novo) nem
os `log-servidor*.txt`. O `.env` e o token **nunca passam pelo git**.

Na torre, só o utilizador `jarvis` os lê:

```bash
chmod 600 ~/jarvis-servidor/.env ~/jarvis-servidor/.spotify_token.json
```

## 4. Os testes sem rede, antes de mais nada

```bash
cd ~/jarvis-servidor
for t in teste_accoes_unicas.py teste_registo_capas.py teste_tema.py \
         teste_api_tema.py teste_letras.py teste_visual.py; do
    .venv/bin/python "$t" | tail -1
done
```

**Esperado:** T31, T32, T33, T34, T36 e T37 a dizer `PASSA`. No T34, o ponto 4
diz `NÃO VERIFICADO` — o caminho do firmware é de Windows; é o previsto.

Se algum falhar, parar aqui: é quase de certeza a versão do Python, e é mais
fácil de ver agora do que com a BOX a falhar.

## 5. A torre não adormece (M5)

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

## 6. A firewall: só a rede de casa (M6)

Se o `ufw` estiver activo (`sudo ufw status`), trocar `192.168.68.0/24` pela
rede de casa — a do IP da torre, com o último número a 0:

```bash
sudo ufw allow from 192.168.68.0/24 to any port 8888,8765,8766 proto tcp
sudo ufw allow from 192.168.68.0/24 to any port 5353 proto udp
```

Nada se abre no router.

## 7. O portátil deixa de ser servidor (M4)

**No portátil**: fechar o servidor (a janela do `iniciar-servidor.ps1`, com
`Ctrl+C`) e não o voltar a arrancar. Dois servidores a anunciar
`spotify-service.local` na mesma rede, e a BOX pode ir ter com o errado sem
que nada o diga.

## 8. O serviço (M1)

```bash
exit                                   # volta ao utilizador com sudo
sudo cp /home/jarvis/jarvis-servidor/deploy/jarvis.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis
systemctl status jarvis                # "active (running)"
sudo -u jarvis tail -f /home/jarvis/jarvis-servidor/log-servidor.txt
```

No log, por esta ordem: a sessão do Spotify restaurada, o `[VOICE-WS]`, o
`[VISUAL] Push em ws://0.0.0.0:8766/visual`, e o Flask a ouvir na 8888.
`Ctrl+C` sai do `tail` sem parar o servidor.

## 9. Os testes com a BOX

Reiniciar a BOX (para ela redescobrir o servidor por mDNS), e depois, do
`TESTES.md`:

1. **T01** arranque limpo e **T02** a BOX encontra o serviço.
2. **T03** botões, **T07** voz, **T38** a matriz em `http://torre-jarvis.local:8888/matriz`.
3. **T39** — o servidor volta sozinho.

## Depois: actualizar

Com o utilizador de administração (não o `jarvis`, que não tem `sudo`):

```bash
sudo /home/jarvis/jarvis-servidor/deploy/actualizar.sh
```

Faz `git pull`, instala dependências, corre os testes sem rede, e **só reinicia
o servidor se passarem todos**.
