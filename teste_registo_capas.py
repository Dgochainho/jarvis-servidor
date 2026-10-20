"""
T32 — registo de capas (Fase 8.b, passo 1).

Corre sem a BOX e sem rede: o estado do Spotify e a conversão da capa são
simulados, e o registo vai para um ficheiro temporário em vez do
`capas.jsonl` verdadeiro.

Prova quatro coisas:

  1. uma capa nova pedida pela BOX fica registada, com a paleta e os nomes;
  2. a mesma capa pedida outra vez não se repete — nem depois de um
     "arranque" novo, que volta a ler os URLs do ficheiro;
  3. a paleta que se regista é a da capa pedida, nunca a da anterior;
  4. um registo que falha não custa a capa à BOX.

Correr com:  .\\.venv\\Scripts\\python.exe teste_registo_capas.py
"""

import io
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from spotify_session import spotify
import capas_log
import app as servidor


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


falhas = []


def verificar(condicao, descricao):
    print(f"  {'OK   ' if condicao else 'FALHA'} {descricao}")

    if not condicao:
        falhas.append(descricao)


def paleta_falsa(hex_dominante):
    cor = {
        "hex": hex_dominante,
        "rgb": [int(hex_dominante[i:i + 2], 16) for i in (1, 3, 5)],
        "peso": 0.5,
        "vivacidade": 0.5,
    }

    return {
        "dominante": cor,
        "realce": cor,
        "mais_viva": cor,
        "paleta": [cor],
    }


def a_tocar(url, album, calcula_paleta=True):
    """Simula o Spotify a tocar `url` e a conversão dessa capa."""

    def estado(max_age_seconds=None):
        return {
            "active": True,
            "track": f"faixa de {album}",
            "artist": "Artista",
            "album": album,
            "cover": url,
        }, 200

    def converter(image_url, width=120, height=120):
        if calcula_paleta:
            servidor.cover_service.cached_paleta = paleta_falsa("#112233")
            servidor.cover_service.cached_paleta_url = image_url

        return b"\x00\x00" * (width * height)

    spotify.get_status = estado
    servidor.cover_service.get_rgb565 = converter


def pedir_capa():
    log = io.StringIO()

    with redirect_stdout(log):
        resposta = servidor.app.test_client().get("/api/cover.rgb565")

    return resposta, log.getvalue()


def novo_arranque(caminho):
    capas_log.CAMINHO = caminho
    capas_log._ja_escritas = None


pasta = Path(tempfile.mkdtemp(prefix="t32-"))
ficheiro = pasta / "capas.jsonl"

print()
print("T32 · registo de capas")
print()

print("1. Uma capa nova fica registada")
novo_arranque(ficheiro)
a_tocar("https://i.scdn.co/image/A", "Álbum A")
resposta, _log = pedir_capa()
capas = capas_log.ler_capas(ficheiro)
verificar(resposta.status_code == 200, f"a BOX recebe a capa (HTTP {resposta.status_code})")
verificar(len(capas) == 1, f"{len(capas)} linha(s) no registo")
if capas:
    verificar(
        capas[0]["capa"] == "https://i.scdn.co/image/A"
        and capas[0]["album"] == "Álbum A"
        and capas[0]["dominante"]["hex"] == "#112233"
        and len(capas[0]["paleta"]) == 1,
        "a linha tem o URL, o álbum e a paleta",
    )

print()
print("2. A mesma capa não se repete")
pedir_capa()
verificar(len(capas_log.ler_capas(ficheiro)) == 1, "pedida outra vez: continua 1 linha")
novo_arranque(ficheiro)
pedir_capa()
verificar(len(capas_log.ler_capas(ficheiro)) == 1, "depois de um arranque novo: continua 1 linha")
a_tocar("https://i.scdn.co/image/B", "Álbum B")
pedir_capa()
verificar(len(capas_log.ler_capas(ficheiro)) == 2, "uma capa diferente: passa a 2 linhas")

print()
print("3. Nunca a paleta da capa anterior")
a_tocar("https://i.scdn.co/image/C", "Álbum C", calcula_paleta=False)
servidor.cover_service.cached_paleta_url = "https://i.scdn.co/image/B"
pedir_capa()
urls = [c["capa"] for c in capas_log.ler_capas(ficheiro)]
verificar("https://i.scdn.co/image/C" not in urls, f"sem paleta própria, C não foi registada ({len(urls)} linhas)")

print()
print("4. Um registo que falha não custa a capa")
novo_arranque(pasta)  # uma pasta não se abre para escrita
a_tocar("https://i.scdn.co/image/D", "Álbum D")
resposta, log = pedir_capa()
verificar(resposta.status_code == 200, f"a BOX recebe a capa (HTTP {resposta.status_code})")
verificar("[CAPAS] Falhou o registo" in log, "a falha fica no log")

print()
if falhas:
    print(f"T32 FALHOU — {len(falhas)} verificação(ões):")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)

print("T32 PASSA")
