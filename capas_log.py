"""
Registo de capas — uma linha JSON por cada capa nova que a BOX mostra.

Porque existe (Fase 8.b, passo 1):

O tema do LCD vai sair da paleta da capa, e o cálculo tem números por
escolher: quão escuro o fundo, que contraste mínimo, quando desistir e usar o
cinzento. Nenhum deles se escolhe com duas capas. Isto junta as capas reais,
do uso normal, para o passo 2 as poder pôr todas lado a lado.

Uma linha por capa, não por vez que toca: um álbum ouvido dez vezes não deve
pesar dez vezes. Os URLs já escritos lêem-se do ficheiro no primeiro uso, por
isso a regra vale entre arranques.

Mesmo formato e mesmas regras do `turn_log`: JSONL em append, nunca levanta
excepção, fora do git (`*.jsonl`). Não guarda transcrições, mas é histórico de
audição.

Ver `docs/FASE-8.b-tema.md`.

Resumo do que já há:  .\\.venv\\Scripts\\python.exe capas_log.py
"""

import colorsys
import json
import sys
import threading
from datetime import datetime
from pathlib import Path


CAMINHO = Path(__file__).with_name("capas.jsonl")


_trinco = threading.Lock()

# None até ao primeiro registo; depois, os URLs que já estão no ficheiro.
_ja_escritas = None


def _ler(caminho):
    """Lê o registo, ignorando linhas corrompidas — como o `ler_turnos`."""
    if not caminho.exists():
        return []

    capas = []

    with open(caminho, encoding="utf-8") as ficheiro:
        for numero, linha in enumerate(ficheiro, start=1):
            linha = linha.strip()

            if not linha:
                continue

            try:
                capas.append(json.loads(linha))

            except json.JSONDecodeError:
                print(f"[CAPAS] Linha {numero} ilegível, ignorada.")

    return capas


def ler_capas(caminho=None):
    return _ler(Path(caminho) if caminho else CAMINHO)


def registar_capa(capa, faixa, artista, album, paleta):
    """
    Acrescenta a capa ao registo, se ainda lá não estiver.

    NUNCA levanta excepção: um registo que falha não pode custar a capa à
    BOX.
    """
    global _ja_escritas

    try:
        if not capa or not paleta:
            return

        with _trinco:
            if _ja_escritas is None:
                _ja_escritas = {
                    linha.get("capa") for linha in _ler(CAMINHO)
                }

            if capa in _ja_escritas:
                return

            linha = {
                "ts": datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
                "capa": capa,
                "faixa": faixa,
                "artista": artista,
                "album": album,
                **paleta,
            }

            with open(CAMINHO, "a", encoding="utf-8") as ficheiro:
                ficheiro.write(
                    json.dumps(linha, ensure_ascii=False) + "\n"
                )

            _ja_escritas.add(capa)

        print(
            f"[CAPAS] Nova capa registada ({len(_ja_escritas)}): "
            f"{album or faixa}"
        )

    except Exception as erro:
        print(f"[CAPAS] Falhou o registo da capa: {erro}")


# ---------------------------------------------------------
# Resumo, para saber se o corpus já chega
# ---------------------------------------------------------
#
# As faixas abaixo são só para descrever o que há, não são limiares de nada:
# servem para ver se o corpus tem capas escuras, claras, garridas e apagadas
# em número que se veja. Os limiares escolhem-se no passo 2, a olhar para as
# capas.

def _luminosidade(rgb):
    """V de HSV, de 0 a 1. Chega para separar capas escuras de claras."""
    return colorsys.rgb_to_hsv(*[c / 255.0 for c in rgb])[2]


def _contar(valores, cortes, nomes):
    contagem = {nome: 0 for nome in nomes}

    for valor in valores:
        for corte, nome in zip(cortes, nomes):
            if valor < corte:
                contagem[nome] += 1
                break

    return contagem


def resumo(caminho=None):
    capas = ler_capas(caminho)

    print()
    print(f"Capas registadas: {len(capas)}")

    if not capas:
        print()
        return

    dominantes = [
        _luminosidade(capa["dominante"]["rgb"])
        for capa in capas
        if capa.get("dominante")
    ]

    vivacidades = [
        capa["mais_viva"]["vivacidade"]
        for capa in capas
        if capa.get("mais_viva")
    ]

    print()
    print("Cor dominante, por luminosidade:")
    for nome, n in _contar(
        dominantes,
        [0.25, 0.5, 0.75, 1.01],
        ["muito escura", "escura", "clara", "muito clara"],
    ).items():
        print(f"  {nome:<14} {n:>4}")

    print()
    print("Cor mais viva da capa:")
    for nome, n in _contar(
        vivacidades,
        [0.2, 0.5, 1.01],
        ["apagada", "média", "garrida"],
    ).items():
        print(f"  {nome:<14} {n:>4}")

    print()
    print("Últimas cinco:")
    for capa in capas[-5:]:
        print(
            f"  {capa.get('ts', '')[:16]}  "
            f"{capa['dominante']['hex']}  "
            f"{capa.get('artista') or ''} — "
            f"{capa.get('album') or capa.get('faixa') or ''}"
        )

    print()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    resumo(sys.argv[1] if len(sys.argv) > 1 else None)
