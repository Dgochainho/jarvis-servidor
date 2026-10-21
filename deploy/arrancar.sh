#!/bin/sh
# Arranca o servidor na torre (Fase 9). Chamado pelo serviço jarvis.service.
#
# Faz o que o iniciar-servidor.ps1 faz no portátil:
#
#   - guarda o log anterior como log-servidor-<data>.txt, em vez de o deitar
#     fora — uma sessão de testes perdida por cima de outra já custou caro;
#   - corre o Python sem buffer e em UTF-8, com a saída toda para o ficheiro.
#
# O `exec` no fim troca este script pelo Python: o systemd fica a vigiar o
# processo do servidor, não o do shell, e um crash do servidor é um crash do
# serviço — que é o que faz o Restart=on-failure funcionar.
#
# Ao contrário do portátil, aqui não há consola: o aviso do CLAUDE.md sobre a
# saída no terminal deixa de se aplicar.

set -eu

PASTA="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PASTA"

LOG="log-servidor.txt"

if [ -f "$LOG" ]; then
    CARIMBO="$(date -r "$LOG" +%Y%m%d-%H%M%S)"
    mv "$LOG" "log-servidor-$CARIMBO.txt"
fi

export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1

exec "$PASTA/.venv/bin/python" -u app.py >> "$LOG" 2>&1
