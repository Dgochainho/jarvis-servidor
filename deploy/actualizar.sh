#!/bin/sh
# Actualiza o servidor na torre a partir do GitHub e reinicia-o (Fase 9).
#
#   sudo /home/jarvis/jarvis-servidor/deploy/actualizar.sh
#
# Corre como administrador (é preciso para o restart), mas faz o git, o pip e
# os testes como o utilizador `jarvis`, que é o dono do repositório e o que o
# serviço usa. O `jarvis` não tem sudo, de propósito.
#
# Pára ANTES de reiniciar se o git pull não for limpo (alterações locais que
# não deviam existir) ou se os testes sem rede falharem: um servidor que não
# passa os seus próprios testes não substitui o que está a correr.

set -eu

PASTA="/home/jarvis/jarvis-servidor"
COMO_JARVIS="sudo -u jarvis -H"

cd "$PASTA"

echo "== git pull"
$COMO_JARVIS git pull --ff-only

echo "== dependências"
$COMO_JARVIS .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements-lock.txt

echo "== testes sem rede"
for teste in teste_accoes_unicas.py teste_registo_capas.py teste_tema.py \
             teste_api_tema.py teste_letras.py teste_visual.py; do
    $COMO_JARVIS .venv/bin/python "$teste" > /tmp/jarvis-teste.txt 2>&1 || {
        echo "FALHOU: $teste — o servidor NÃO foi reiniciado"
        tail -20 /tmp/jarvis-teste.txt
        exit 1
    }
    tail -1 /tmp/jarvis-teste.txt
done

echo "== reiniciar"
systemctl restart jarvis
sleep 3
systemctl --no-pager --lines=0 status jarvis
