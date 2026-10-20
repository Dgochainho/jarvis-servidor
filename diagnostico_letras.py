"""
Diagnóstico — cobertura do LRCLIB nas faixas reais (Fase 8.d, passo 0).

Antes de escrever o lyrics_service: das faixas que de facto se ouvem aqui,
quantas têm letra SINCRONIZADA no LRCLIB? Se forem poucas, a funcionalidade
quase nunca aparece, e isso muda as prioridades. As capas do capas.jsonl são
uma amostra do uso real, com faixa, artista e álbum.

Mede também o que o desenho precisa de saber:

  - o comprimento das linhas, para ver quantas cabem numa fila de 21
    caracteres, em duas, em três (o painel tem 21 × 3);
  - quantas letras têm caracteres fora do Latin-1, que a fonte de 5×8 do nó
    não desenha — é a decisão que o PDF de 12-10 manda tomar antes do código.

PRIVACIDADE: manda ao lrclib.net o nome da faixa e do artista de cada capa.
Autorizado a 2026-10-20. NÃO imprime nem guarda o texto das letras — só
contagens e comprimentos. O resultado por faixa vai para letras_medicao.jsonl,
fora do git (*.jsonl).

Correr com:  .\\.venv\\Scripts\\python.exe diagnostico_letras.py
"""

import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

import capas_log


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


API = "https://lrclib.net/api/search"

# O LRCLIB pede um User-Agent que identifique a aplicação.
CABECALHOS = {"User-Agent": "Jarvis/8.d (diagnostico pessoal, BOX-3)"}

# Uma pausa entre pedidos: é um serviço gratuito, e 77 pedidos seguidos não
# têm pressa nenhuma.
PAUSA_S = 0.5

# Esperas depois de um 503, em segundos; None = última tentativa.
ESPERAS_503 = (1, 2, 4, None)

SAIDA = Path(__file__).with_name("letras_medicao.jsonl")

COLS = 21

LINHA_LRC = re.compile(r"^\s*\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)$")


def normalizar(texto):
    """Minúsculas, sem acentos nem pontuação — só para comparar nomes."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def primeiro_artista(artistas):
    return (artistas or "").split(",")[0].strip()


def escolher(resultados, faixa, artista):
    """
    O resultado com o mesmo artista e o nome de faixa mais parecido.

    Sem a duração (o capas.jsonl não a tem) não se distinguem versões; para
    medir cobertura chega. Entre candidatos iguais, preferir o que tem letra
    sincronizada — é a pergunta que se está a fazer.
    """
    alvo_faixa = normalizar(faixa)
    alvo_artista = normalizar(artista)

    candidatos = [
        r for r in resultados
        if alvo_artista and alvo_artista in normalizar(r.get("artistName"))
    ]

    if not candidatos:
        return None

    def pontos(r):
        nome = normalizar(r.get("trackName"))
        return (
            nome == alvo_faixa,
            nome.startswith(alvo_faixa) or alvo_faixa.startswith(nome),
            bool(r.get("syncedLyrics")),
        )

    melhor = max(candidatos, key=pontos)
    return melhor if pontos(melhor)[:2] != (False, False) else None


def analisar_lrc(lrc):
    """Contagens sobre um LRC, sem guardar o texto."""
    linhas = []

    for linha in lrc.splitlines():
        m = LINHA_LRC.match(linha)
        if m and m.group(3).strip():
            linhas.append(m.group(3).strip())

    fora_latin1 = sum(
        1 for linha in linhas
        if any(ord(c) > 0xFF for c in linha)
    )

    # Quais, por nome Unicode e contagem: decide entre transliterar (aspas
    # tipográficas, travessões) e desistir (outra escrita). Só os caracteres,
    # nunca o texto à volta.
    caracteres = {}
    for linha in linhas:
        for c in linha:
            if ord(c) > 0xFF:
                nome = unicodedata.name(c, f"U+{ord(c):04X}")
                caracteres[nome] = caracteres.get(nome, 0) + 1

    comprimentos = [len(linha) for linha in linhas]

    return {
        "linhas": len(linhas),
        "fora_latin1": fora_latin1,
        "cabe_1": sum(1 for n in comprimentos if n <= COLS),
        "cabe_2": sum(1 for n in comprimentos if COLS < n <= 2 * COLS),
        "cabe_3": sum(1 for n in comprimentos if 2 * COLS < n <= 3 * COLS),
        "nao_cabe": sum(1 for n in comprimentos if n > 3 * COLS),
        "max": max(comprimentos, default=0),
        "caracteres_fora": caracteres,
    }


def medir(capa, sessao):
    faixa = capa.get("faixa") or ""
    artista = primeiro_artista(capa.get("artista"))

    # Primeira corrida (2026-10-20): 19 de 77 pedidos deram 503, espalhados.
    # É o serviço a recusar a espaços, não falta de letras. Repetir com espera
    # crescente, e registar quantas tentativas foram precisas — o
    # lyrics_service vai ter de fazer o mesmo.
    tentativas = 0
    erro = None

    for espera in ESPERAS_503:
        tentativas += 1
        inicio = time.perf_counter()

        try:
            resposta = sessao.get(
                API,
                params={"track_name": faixa, "artist_name": artista},
                headers=CABECALHOS,
                timeout=15,
            )
            segundos = time.perf_counter() - inicio

            if resposta.status_code == 503 and espera is not None:
                time.sleep(espera)
                continue

            resposta.raise_for_status()
            resultados = resposta.json()
            erro = None
            break

        except Exception as e:
            erro = e
            if espera is None:
                break
            time.sleep(espera)

    if erro is not None or resposta.status_code == 503:
        return {"faixa": faixa, "artista": artista, "categoria": "erro",
                "tentativas": tentativas,
                "erro": str(erro or "503 em todas as tentativas")[:200]}

    escolhido = escolher(resultados, faixa, artista)

    linha = {
        "faixa": faixa,
        "artista": artista,
        "resultados": len(resultados),
        "segundos": round(segundos, 2),
        "tentativas": tentativas,
    }

    if escolhido is None:
        linha["categoria"] = "nao_encontrada"
    elif escolhido.get("syncedLyrics"):
        linha["categoria"] = "sincronizada"
        linha.update(analisar_lrc(escolhido["syncedLyrics"]))
    elif escolhido.get("instrumental"):
        linha["categoria"] = "instrumental"
    elif escolhido.get("plainLyrics"):
        linha["categoria"] = "so_texto"
    else:
        linha["categoria"] = "vazia"

    return linha


def main():
    capas = [c for c in capas_log.ler_capas() if c.get("faixa")]

    print()
    print(f"Faixas a medir: {len(capas)}")
    print()

    sessao = requests.Session()
    linhas = []

    with open(SAIDA, "w", encoding="utf-8") as ficheiro:
        for i, capa in enumerate(capas, start=1):
            linha = medir(capa, sessao)
            linhas.append(linha)
            ficheiro.write(json.dumps(linha, ensure_ascii=False) + "\n")
            print(f"  {i:>3}/{len(capas)}  {linha['categoria']}")
            time.sleep(PAUSA_S)

    print()
    print("Cobertura:")
    contagem = {}
    for linha in linhas:
        contagem[linha["categoria"]] = contagem.get(linha["categoria"], 0) + 1
    for categoria in ("sincronizada", "so_texto", "instrumental", "vazia",
                      "nao_encontrada", "erro"):
        n = contagem.get(categoria, 0)
        print(f"  {categoria:<15} {n:>3}  ({100 * n / len(linhas):.0f}%)")

    sinc = [linha for linha in linhas if linha["categoria"] == "sincronizada"]
    if sinc:
        total = sum(linha["linhas"] for linha in sinc)
        print()
        print(f"Nas {len(sinc)} sincronizadas, {total} linhas de letra:")
        for chave, rotulo in (("cabe_1", "cabe numa fila de 21"),
                              ("cabe_2", "precisa de duas filas"),
                              ("cabe_3", "precisa de três filas"),
                              ("nao_cabe", "não cabe em três filas")):
            n = sum(linha[chave] for linha in sinc)
            print(f"  {rotulo:<24} {n:>5}  ({100 * n / total:.1f}%)")
        print(f"  linha mais comprida: {max(linha['max'] for linha in sinc)} caracteres")
        com_fora = sum(1 for linha in sinc if linha["fora_latin1"])
        print(f"  letras com caracteres fora do Latin-1: {com_fora} de {len(sinc)}")
        todos = {}
        for linha in sinc:
            for nome, n in linha.get("caracteres_fora", {}).items():
                todos[nome] = todos.get(nome, 0) + n
        for nome, n in sorted(todos.items(), key=lambda par: -par[1])[:10]:
            print(f"    {n:>4} × {nome}")

    repetidas = [linha for linha in linhas if linha.get("tentativas", 1) > 1]
    print()
    print(
        f"Pedidos que precisaram de repetir por 503: {len(repetidas)} de "
        f"{len(linhas)}; tentativas no pior caso: "
        f"{max((linha.get('tentativas', 1) for linha in linhas), default=0)}"
    )

    tempos = sorted(linha["segundos"] for linha in linhas if "segundos" in linha)
    if tempos:
        print()
        print(
            f"Tempo de resposta do LRCLIB: mediana {tempos[len(tempos) // 2]:.2f} s, "
            f"máximo {tempos[-1]:.2f} s"
        )

    print()
    print(f"Resultado por faixa em {SAIDA.name} (sem o texto das letras).")


if __name__ == "__main__":
    main()
