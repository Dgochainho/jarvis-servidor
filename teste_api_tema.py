"""
T34 — `/api/tema` (Fase 8.b, passo 3).

Corre sem a BOX e sem rede: o estado do Spotify e a paleta são simulados.

Prova:

  1. a tocar, devolve o tema da capa que está a tocar, com o URL dela;
  2. sem reprodução, ou sem capa, devolve o tema neutro e diz que é;
  3. com o estado do Spotify indisponível, ou a paleta a falhar, devolve um
     erro e nenhuma cor — a BOX fica com o tema que tem;
  4. a resposta cabe com folga no `spotify_response[4096]` da BOX;
  5. o tema neutro do firmware (`TEMA_NEUTRO` no `display_LCD.c`) é igual ao
     do servidor. Duas cópias de uma coisa que tem de concordar — é por isso
     que este teste as compara (decisão F3).

Correr com:  .\\.venv\\Scripts\\python.exe teste_api_tema.py
"""

import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

from spotify_session import spotify
import tema_service
import app as servidor


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Onde o CLAUDE.md diz que o firmware vive.
FIRMWARE = Path(
    r"C:\Users\dgoch\Desktop\ProjetoAss Istant\projetos\hello_world"
    r"\main\display_LCD.c"
)

CAPA = "https://i.scdn.co/image/T34"

PALETA = {
    "dominante": {"hex": "#dfc7bc", "rgb": [223, 199, 188], "peso": 0.5, "vivacidade": 0.15},
    "realce": {"hex": "#573367", "rgb": [87, 51, 103], "peso": 0.1, "vivacidade": 0.4},
    "mais_viva": {"hex": "#573367", "rgb": [87, 51, 103], "peso": 0.1, "vivacidade": 0.4},
    "paleta": [],
}


falhas = []


def verificar(condicao, descricao):
    print(f"  {'OK   ' if condicao else 'FALHA'} {descricao}")

    if not condicao:
        falhas.append(descricao)


def simular(estado, codigo=200, paleta=PALETA, paleta_falha=False):
    spotify.get_status = lambda max_age_seconds=None: (estado, codigo)

    def get_paleta(url):
        if paleta_falha:
            raise RuntimeError("simulado")
        return paleta

    servidor.cover_service.get_paleta = get_paleta


def pedir():
    with redirect_stdout(io.StringIO()):
        resposta = servidor.app.test_client().get("/api/tema")

    return resposta, resposta.get_json(silent=True) or {}


def cores(tema):
    return {cor: tema[cor] for cor in tema_service.CORES}


neutro = cores(tema_service.tema_neutro())

print()
print("T34 · /api/tema")
print()

print("1. A tocar: o tema da capa")
simular({"active": True, "cover": CAPA, "track": "t", "artist": "a"})
resposta, corpo = pedir()
verificar(resposta.status_code == 200, f"HTTP {resposta.status_code}")
verificar(corpo.get("origem") == "capa" and corpo.get("activo") is True, f"origem {corpo.get('origem')}")
verificar(corpo.get("capa") == CAPA, "traz o URL da capa")
verificar(cores(corpo) == cores(tema_service.calcular_tema(PALETA)), "as cores são as do tema_service")
verificar(len(resposta.data) < 1024, f"cabe no buffer da BOX ({len(resposta.data)} bytes)")

print()
print("2. Sem reprodução, ou sem capa: o neutro")
simular({"active": False})
resposta, corpo = pedir()
verificar(
    resposta.status_code == 200 and corpo.get("origem") == "neutro"
    and corpo.get("activo") is False and corpo.get("capa") is None
    and cores(corpo) == neutro,
    f"sem reprodução -> {corpo.get('origem')}, activo={corpo.get('activo')}",
)
simular({"active": True, "cover": None})
resposta, corpo = pedir()
verificar(
    corpo.get("origem") == "neutro" and corpo.get("activo") is True and cores(corpo) == neutro,
    f"a tocar sem capa -> {corpo.get('origem')}",
)

print()
print("3. Falhas: erro, e nenhuma cor")
simular({}, codigo=401)
resposta, corpo = pedir()
verificar(
    resposta.status_code == 401 and "fundo" not in corpo,
    f"estado indisponível -> HTTP {resposta.status_code}",
)
simular({"active": True, "cover": CAPA}, paleta_falha=True)
resposta, corpo = pedir()
verificar(
    resposta.status_code == 500 and "fundo" not in corpo,
    f"paleta a falhar -> HTTP {resposta.status_code}",
)

print()
print("4. O neutro do firmware é o do servidor")
if not FIRMWARE.exists():
    print(f"  NÃO VERIFICADO — firmware não encontrado em {FIRMWARE}")
else:
    fonte = FIRMWARE.read_text(encoding="utf-8")
    bloco = re.search(r"TEMA_NEUTRO\s*=\s*\{(.*?)\};", fonte, re.S)
    verificar(bloco is not None, "TEMA_NEUTRO encontrado no display_LCD.c")

    if bloco:
        firmware = {
            nome: "#" + valor.lower()
            for nome, valor in re.findall(r"\.(\w+)\s*=\s*0x([0-9a-fA-F]{6})", bloco.group(1))
        }

        for cor in tema_service.CORES:
            verificar(
                firmware.get(cor) == neutro[cor],
                f"{cor}: firmware {firmware.get(cor)} · servidor {neutro[cor]}",
            )

print()
if falhas:
    print(f"T34 FALHOU — {len(falhas)} verificação(ões)")
    sys.exit(1)

print("T34 PASSA")
