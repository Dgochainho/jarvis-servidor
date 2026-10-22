# Instalar o servidor na torre

Fase 9 · guia passo a passo. O porquê de cada passo está no
`docs/FASE-9-servidor.md` (decisões M1 a M6); aqui só o que se faz.

Começa com a torre ainda em Windows. Os comandos são para correr na torre,
excepto onde diz **no portátil**.

---

## A. Instalar o Linux

**Ubuntu Server 24.04 LTS**, e não a versão mais recente: traz o Python 3.12,
que é aquele em que o servidor sempre correu, e tem suporte até 2029. "Server"
quer dizer sem ambiente gráfico — a torre fica ligada à rede e usa-se a partir
do portátil, por SSH.

⚠️ **Isto apaga o Windows e tudo o que estiver no disco da torre.** Copiar
antes o que lá houver para guardar.

### A1. No portátil: preparar uma pen de instalação

Precisa de uma pen de **8 GB ou mais, que vai ser apagada**. O disco externo
de 500 GB também serviria, mas ficava apagado por inteiro — não usar se tiver
alguma coisa.

1. Descarregar o Ubuntu Server 24.04 LTS (um ficheiro `.iso`, ~3 GB) de
   `ubuntu.com/download/server`.
2. Descarregar o **Rufus** de `rufus.ie` — corre sem instalar.
3. No Rufus: *Dispositivo* → a pen; *Seleccionar* → o `.iso`; o resto como
   vem; *Iniciar*. Se perguntar o modo, **ISO**.

### A2. Na torre: arrancar pela pen

1. Com a torre desligada, ligar a pen e um teclado, monitor e cabo de rede.
2. Ligar a torre e carregar várias vezes em **Esc** logo no arranque — nos HP
   abre o menu de arranque. Depois:
   - **F10** entra na BIOS. Aproveitar para pôr *After Power Loss* (ou *AC
     Power Recovery*) em **Power On** (M5). Guardar e sair.
   - **F9** escolhe o dispositivo de arranque: a pen (USB).
3. O *Secure Boot* pode ficar ligado — o Ubuntu arranca com ele.

### A3. O instalador

Escolhas, por ordem de ecrã (o resto fica como vem):

| Ecrã | Escolha |
|---|---|
| Idioma | o que preferir |
| Teclado | **Portuguese** |
| Tipo de instalação | **Ubuntu Server** (não a "minimized") |
| Rede | o cabo aparece com um IP: seguir |
| Disco | **Use an entire disk** — o disco da torre. Confirmar: apaga o Windows |
| Perfil | o seu nome; **nome do servidor: `torre-jarvis`** — nunca `spotify-service` (M4); um utilizador e uma password: este é o **utilizador de administração** dos passos seguintes |
| Ubuntu Pro | saltar |
| SSH | ✅ **Install OpenSSH server** |
| Snaps em destaque | nenhum |

No fim, *Reboot now*, e tirar a pen quando pedir.

### A4. Primeiro arranque

Entrar com o utilizador e a password do perfil, e:

```bash
sudo apt update && sudo apt upgrade -y
hostname -I          # o IP da torre — anotar
lscpu | grep -E "Model name|^CPU\(s\)"
free -h
```

O processador e a memória vão para o `docs/FASE-9-servidor.md`.

A partir daqui pode-se desligar o monitor e o teclado e continuar **do
portátil**, numa PowerShell:

```powershell
ssh UTILIZADOR@IP-DA-TORRE
```

---

## 0. Antes de começar

- [ ] A torre chama-se `torre-jarvis` (ou outro nome que não `spotify-service`)
      (M4). Ver com `hostname`; mudar com `sudo hostnamectl set-hostname torre-jarvis`.
- [ ] Ligada **por cabo**, se der (M2).
- [ ] Na **BIOS**: *After Power Loss* em **Power On** — feito no A2 (M5).

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
exit                                   # volta ao utilizador de administração
```

O repositório é privado: o `git clone` pede autenticação. A forma mais simples
é um token pessoal do GitHub só de leitura, para este repositório.

## 3. Os segredos e os dados (M3)

Vão: `.env`, `.spotify_token.json`, `capas.jsonl` e a pasta `letras_cache`.
**Não** vão: o `turnos.jsonl` (decidido — a torre começa um registo novo) nem
os `log-servidor*.txt`. O `.env` e o token **nunca passam pelo git**.

**Primeiro, parar o servidor do portátil** (a janela do `iniciar-servidor.ps1`,
com `Ctrl+C`) e não o voltar a arrancar. O servidor renova o token do Spotify
sozinho; se renovar depois da cópia, a cópia fica para trás. É também o passo 7
— aqui só se antecipa.

### Por um disco externo (o caminho previsto)

**No portátil**, com o disco ligado — trocar `E:` pela letra que o Windows lhe
der —, numa PowerShell na pasta do servidor:

```powershell
New-Item -ItemType Directory -Force E:\jarvis-transferencia
Copy-Item .env, .spotify_token.json, capas.jsonl E:\jarvis-transferencia
Copy-Item -Recurse letras_cache E:\jarvis-transferencia
```

**Na torre**, com o disco ligado. Num Ubuntu **Desktop** ele monta-se sozinho
em `/media/<utilizador>/<nome-do-disco>`; num **Server** monta-se à mão:

```bash
lsblk -f                                  # encontrar o disco: sdb1, ou parecido
sudo mkdir -p /mnt/disco
sudo mount /dev/sdb1 /mnt/disco           # NTFS e exFAT lêem-se sem instalar nada
```

Copiar para o repositório, e passar os ficheiros para o `jarvis` (trocar
`/mnt/disco` pelo `/media/…` no Desktop):

```bash
cd /mnt/disco/jarvis-transferencia
sudo cp .env .spotify_token.json capas.jsonl /home/jarvis/jarvis-servidor/
sudo cp -r letras_cache /home/jarvis/jarvis-servidor/
sudo chown -R jarvis:jarvis /home/jarvis/jarvis-servidor
sudo chmod 600 /home/jarvis/jarvis-servidor/.env /home/jarvis/jarvis-servidor/.spotify_token.json
cd / && sudo umount /mnt/disco            # só no Server
```

**Depois de o servidor arrancar bem na torre** (passo 8), apagar a pasta
`jarvis-transferencia` do disco: tem o `.env` e o token em claro.

### Pela rede, em alternativa

O `jarvis` não aceita login (não tem password, de propósito), por isso o `scp`
vai para o utilizador de administração e depois passa-se ao `jarvis`. **No
portátil**:

```powershell
scp .env .spotify_token.json capas.jsonl ADMIN@IP-DA-TORRE:~/
scp -r letras_cache ADMIN@IP-DA-TORRE:~/
```

e **na torre**, com o utilizador de administração:

```bash
sudo mv ~/.env ~/.spotify_token.json ~/capas.jsonl ~/letras_cache /home/jarvis/jarvis-servidor/
sudo chown -R jarvis:jarvis /home/jarvis/jarvis-servidor
sudo chmod 600 /home/jarvis/jarvis-servidor/.env /home/jarvis/jarvis-servidor/.spotify_token.json
```

## 4. Os testes sem rede, antes de mais nada

Como o utilizador `jarvis`, que é o que o serviço vai usar:

```bash
sudo -iu jarvis
cd ~/jarvis-servidor
for t in teste_accoes_unicas.py teste_registo_capas.py teste_tema.py \
         teste_api_tema.py teste_letras.py teste_visual.py; do
    .venv/bin/python "$t" | tail -1
done
exit
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

**Confirmar** que o servidor do portátil continua parado desde o passo 3, e
que ninguém o voltou a arrancar. Dois servidores a anunciar
`spotify-service.local` na mesma rede, e a BOX pode ir ter com o errado sem
que nada o diga.

## 8. O serviço (M1)

Com o utilizador de administração:

```bash
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
