"""
Registo de turnos — uma linha JSON por interacção de voz.

Porque existe:

Os logs `[PERF]` no stdout respondem à pergunta "quanto demorou este turno?"
enquanto a janela estiver aberta. Não respondem a nenhuma das perguntas que
interessam a seguir:

    - O fallback HTTP alguma vez é usado em campo? (decisão D1)
    - Quantas vezes a BOX se auto-activa com a própria voz? (Fase 3.1)
    - O tempo de recepção do áudio afasta-se da duração da fala? (bug B4)
    - A latência piorou desde a semana passada?

Todas elas são contagens sobre muitos turnos, e não se fazem a olhar para uma
consola. Daí um ficheiro.

Formato: JSONL — uma linha JSON completa por turno, em append. Escolhido em vez
de CSV porque os campos variam (um turno com erro não tem `t_primeiro_audio`) e
em vez de SQLite porque isto tem de poder ser lido com um editor de texto às
duas da manhã.

O ficheiro está no `.gitignore` (`*.jsonl`).

PRIVACIDADE: com a decisão D6, os campos `ouvido` e `dito` guardam as
transcrições em texto. É um registo de tudo o que for dito à BOX, em claro, no
disco deste PC. Fica no `.gitignore`, mas não está cifrado nem expira.
Para desligar só o texto, pôr GUARDAR_TRANSCRICOES = False aqui em baixo: o
resto dos campos continua a ser registado.
"""

import json
from datetime import datetime
from pathlib import Path


CAMINHO = Path(__file__).with_name("turnos.jsonl")

# Ver a nota de PRIVACIDADE acima. False substitui o texto pelo seu
# comprimento em caracteres (`ouvido_n`, `dito_n`).
GUARDAR_TRANSCRICOES = True


def segundos(valor):
    """Arredonda para 2 casas, tolerando None."""
    if valor is None:
        return None

    return round(valor, 2)


def registar_turno(campos):
    """
    Acrescenta uma linha ao registo.

    NUNCA levanta excepção. Um turno de voz não pode falhar porque o disco
    está cheio ou o ficheiro está aberto noutro programa — o registo é para
    observar o sistema, não para fazer parte dele.
    """
    try:
        linha = {
            "ts": datetime.now().astimezone().isoformat(
                timespec="seconds"
            )
        }

        for chave, valor in campos.items():
            if chave in ("ouvido", "dito") and not GUARDAR_TRANSCRICOES:
                linha[f"{chave}_n"] = len(valor or "")
                continue

            linha[chave] = valor

        with open(CAMINHO, "a", encoding="utf-8") as ficheiro:
            ficheiro.write(
                json.dumps(linha, ensure_ascii=False) + "\n"
            )

    except Exception as erro:
        # Um aviso, e seguimos. Se isto se repetir, aparece no stdout.
        print(f"[TURNOS] Falhou o registo do turno: {erro}")


def ler_turnos(caminho=None):
    """
    Lê o registo, ignorando linhas corrompidas.

    Uma linha truncada (servidor morto a meio de uma escrita) não deve
    impedir a leitura das outras 900.
    """
    caminho = Path(caminho) if caminho else CAMINHO

    if not caminho.exists():
        return []

    turnos = []

    with open(caminho, encoding="utf-8") as ficheiro:
        for numero, linha in enumerate(ficheiro, start=1):
            linha = linha.strip()

            if not linha:
                continue

            try:
                turnos.append(json.loads(linha))

            except json.JSONDecodeError:
                print(
                    f"[TURNOS] Linha {numero} ilegível, ignorada."
                )

    return turnos
