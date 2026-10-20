"""
T37 — visual_service (Fase 8.d).

Corre sem a BOX e sem rede externa: o Spotify, a paleta e o LRCLIB são
simulados; o WebSocket é real, numa porta livre em 127.0.0.1.

Prova:

  1. o relógio: âncora a meio do pedido; leitura lenta ignorada (a não ser
     que a faixa mude); parado não anda; não passa da duração;
  2. as mensagens têm os campos do PDF de 12-10;
  3. sem letra (L6): uma entrada com o título e o artista, já em filas e só
     com caracteres da fonte;
  4. pela ligação: quem liga recebe o estado inteiro; a faixa nova chega com
     a paleta e depois a letra; um caminho errado é recusado;
  5. porta ocupada: o start() falha (B5);
  6. o get_status passa a trazer `track_id` e `pedido_ms`.

Correr com:  .\\.venv\\Scripts\\python.exe teste_visual.py
"""

import json
import socket
import sys
import time

from websockets.sync.client import connect

import visual_service as V
from lyrics_service import CONJUNTO


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


falhas = []


def verificar(condicao, descricao):
    print(f"  {'OK   ' if condicao else 'FALHA'} {descricao}")
    if not condicao:
        falhas.append(descricao)


def status(track_id="spotify:track:A", progresso=5000, servidor=10_000, pedido=800, a_tocar=True, **extra):
    return {
        "active": track_id is not None, "playing": a_tocar, "track_id": track_id,
        "track": "Faixa “A”", "artist": "Artistа", "album": "Álbum",
        "progress_ms": progresso, "duration_ms": 180_000, "cover": "https://i.scdn.co/image/A",
        "server_time_ms": servidor, "pedido_ms": pedido, **extra,
    }


print()
print("T37 · visual_service")

print()
print("1. O relógio")
r = V.Relogio()
r.actualizar(status())
verificar(r.progresso(10_600) == 6000, f"âncora a meio do pedido: {r.progresso(10_600)} (esperado 6000)")
verificar(not r.actualizar(status(progresso=9000, servidor=14_000, pedido=3000)), "leitura lenta da mesma faixa: ignorada")
verificar(r.progresso(10_600) == 6000, "e o relógio não mexeu")
verificar(r.actualizar(status(track_id="spotify:track:B", progresso=0, servidor=20_000, pedido=3000)),
          "leitura lenta com faixa nova: aceite")
r.actualizar(status(track_id="spotify:track:B", progresso=7000, servidor=30_000, a_tocar=False))
verificar(r.progresso(99_999) == 7000, "parada, a posição não anda")
r.actualizar(status(track_id="spotify:track:B", progresso=179_000, servidor=40_000, pedido=0))
verificar(r.progresso(60_000) == 180_000, "a tocar, não passa da duração")
verificar(not r.actualizar(status(track_id="spotify:track:B", progresso=179_000, servidor=40_000)),
          "a mesma leitura (cache) não conta duas vezes")

print()
print("2. As mensagens")
r = V.Relogio()
r.actualizar(status())
paleta = {"dominante": {"hex": "#112233"}, "realce": {"hex": "#445566"}, "mais_viva": {"hex": "#778899"}}
t = V.mensagem_track(status(), paleta, r, agora_ms=10_600)
verificar(
    set(t) == {"t", "id", "titulo", "artista", "duration_ms", "progress_ms", "server_time_ms", "paleta"},
    f"track: {sorted(t)}",
)
verificar(t["paleta"] == {"dom": "#112233", "a1": "#445566", "a2": "#778899"} and t["progress_ms"] == 6000,
          "paleta dom/a1/a2 e progresso levado ao instante de envio")
verificar(t["titulo"] == 'Faixa "A"' and t["artista"] == "Artista",
          f"título e artista só com caracteres da fonte: {t['titulo']!r}, {t['artista']!r}")
e = V.mensagem_estado(r, agora_ms=10_600)
verificar(set(e) == {"t", "id", "a_tocar", "progress_ms", "server_time_ms"}, f"estado: {sorted(e)}")

print()
print("3. Sem letra: título e artista")
sem = V.mensagem_letras("spotify:track:A", {"estado": "sem_letra", "motivo": "nao_existe", "cols": 21, "filas": 3, "linhas": []},
                        "Um título bastante comprido para ver a quebra em filas", "Artistа")
verificar(len(sem["linhas"]) == 1 and sem["linhas"][0][0] == 0, f"uma entrada no instante 0: {sem['linhas']}")
filas = sem["linhas"][0][1]
verificar(len(filas) == 3 and filas[-1] == "Artista", "duas filas de título e o artista (com o а cirílico transliterado)")
verificar(all(len(f) <= 21 and all(c in CONJUNTO for c in f) for f in filas), "tudo cabe na fonte")


class SpotifyFalso:
    def __init__(self):
        self.status = status()
        self.leituras = 0

    def get_status(self, max_age_seconds=0.0):
        self.leituras += 1
        self.status = {**self.status, "server_time_ms": int(time.time() * 1000), "pedido_ms": 100}
        return self.status, 200


class CoverFalso:
    def get_paleta(self, url):
        return paleta


class LetrasFalsas:
    def obter(self, track_id, faixa, artista, album=None, duracao_ms=None):
        return {"estado": "sincronizada", "motivo": "lrclib", "cols": 21, "filas": 3,
                "linhas": [[1000, ["linha de teste"]]]}


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def receber_ate(ws, tipo, segundos=5):
    fim = time.time() + segundos
    while time.time() < fim:
        m = json.loads(ws.recv(timeout=fim - time.time()))
        if m["t"] == tipo:
            return m
    return None


print()
print("4. Pela ligação")
V.INTERVALO_S = 0.05
spotify = SpotifyFalso()
porta = porta_livre()
servico = V.VisualService(spotify, CoverFalso(), LetrasFalsas(), host="127.0.0.1", port=porta)
servico.start()

try:
    with connect(f"ws://127.0.0.1:{porta}/visual") as ws:
        primeira = receber_ate(ws, "track")
        verificar(primeira and primeira["id"] == "spotify:track:A", "quem liga recebe logo a faixa")
        letras = receber_ate(ws, "letras")
        verificar(letras and letras["linhas"] == [[1000, ["linha de teste"]]], "e a letra")
        verificar(receber_ate(ws, "estado") is not None, "e o estado")

        spotify.status = status(track_id="spotify:track:B")
        nova = receber_ate(ws, "track")
        verificar(nova and nova["id"] == "spotify:track:B" and nova["paleta"]["a1"] == "#445566",
                  "faixa nova chega com a paleta")
        letras_b = receber_ate(ws, "letras")
        verificar(letras_b and letras_b["id"] == "spotify:track:B", "e depois a letra dela")

    try:
        with connect(f"ws://127.0.0.1:{porta}/outra") as ws:
            ws.recv(timeout=2)
        recusado = False
    except Exception:
        recusado = True
    verificar(recusado, "caminho errado: recusado")

    print()
    print("5. Porta ocupada: o arranque falha (B5)")
    segundo = V.VisualService(spotify, CoverFalso(), LetrasFalsas(), host="127.0.0.1", port=porta)
    try:
        segundo.start()
        falhou = False
    except RuntimeError:
        falhou = True
    finally:
        segundo.stop()
    verificar(falhou, "start() levanta RuntimeError")

finally:
    servico.stop()

print()
print("6. O get_status traz o que o relógio precisa")
fonte = open("spotify_client.py", encoding="utf-8").read()
verificar('"pedido_ms":' in fonte and '"track_id":' in fonte, "track_id e pedido_ms no resultado do _fetch_status")

print()
if falhas:
    print(f"T37 FALHOU — {len(falhas)} verificação(ões)")
    sys.exit(1)

print("T37 PASSA")
