"""
T36 — lyrics_service (Fase 8.d).

Corre sem rede: o LRCLIB é simulado. O LRC é INVENTADO para este teste —
letra real não entra no repositório.

Prova:

  1. o LRC lê-se bem: vários tempos na mesma linha, metadados, [offset:];
  2. as filas: por palavras, ≤ 21, palavra grande cortada;
  3. as regras do L2: ≤ 2 filas, 3 filas, mais de 3 divide no tempo;
  4. os caracteres do L3: aspa tipográfica e cirílico transliterados, til
     mantido, outra escrita deixa a LINHA vazia e não a letra;
  5. o LRCLIB: /api/get com a duração, /api/search sem sufixo, os 503
     repetidos a 1-2-4 s, o "indisponível" que não fica em cache;
  6. a cache: a segunda vez não pergunta; o "não há" expira aos 30 dias;
  7. tudo o que sai cabe na fonte do nó.

Correr com:  .\\.venv\\Scripts\\python.exe teste_letras.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

import lyrics_service as L


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


falhas = []


def verificar(condicao, descricao):
    print(f"  {'OK   ' if condicao else 'FALHA'} {descricao}")
    if not condicao:
        falhas.append(descricao)


# Inventado. Linhas de comprimentos escolhidos para as regras do L2.
LRC = """[ar:Ninguém]
[ti:Canção de teste]
[00:01.00]Linha curta
[00:05.50][01:05.50]Um refrão que se repete duas vezes na letra
[00:10.00]
[00:12.00]Uma linha escrita para ocupar três filas certas
[00:20.00]E esta é tão comprida que nem em três filas cabe inteira, por isso o servidor tem de a dividir no tempo
[00:30.00]Fim
"""


class Resposta:
    def __init__(self, codigo, corpo=None):
        self.status_code = codigo
        self._corpo = corpo

    def json(self):
        return self._corpo


class SessaoFalsa:
    """Responde com a lista dada, por ordem, e regista os pedidos."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.pedidos.append((url.rsplit("/", 1)[-1], dict(params or {})))
        return self.respostas.pop(0)


def servico(respostas, pasta, agora=1_000_000.0):
    esperas = []
    sessao = SessaoFalsa(respostas)
    s = L.LyricsService(sessao=sessao, pasta_cache=pasta, dormir=esperas.append, agora=lambda: agora)
    return s, sessao, esperas


print()
print("T36 · lyrics_service")

print()
print("1. Ler o LRC")
linhas = L.ler_lrc(LRC)
verificar(len(linhas) == 7, f"{len(linhas)} linhas (o refrão conta duas vezes; metadados de fora)")
verificar(linhas[0] == (1000, "Linha curta"), f"primeira: {linhas[0]}")
verificar(linhas[-1][0] == 65500, f"o refrão repetido vai para o fim: {linhas[-1][0]} ms")
verificar((10000, "") in linhas, "a linha vazia fica, para limpar o ecrã")
com_offset = L.ler_lrc("[offset:+500]\n[00:02.00]x")
verificar(com_offset == [(1500, "x")], f"[offset:+500] adianta: {com_offset}")

print()
print("2. Filas")
filas = L.partir_filas("Uma linha escrita para ocupar três filas certas")
verificar(filas == ["Uma linha escrita", "para ocupar três", "filas certas"], f"{filas}")
verificar(L.partir_filas("x" * 30) == ["x" * 21, "x" * 9], "palavra de 30 cortada aos 21")

print()
print("3. As regras do L2")
entradas = L.montar_entradas(linhas)
por_tempo = {t: f for t, f in entradas}
verificar(por_tempo[1000] == ["Linha curta"], "uma fila")
verificar(
    len(por_tempo[12000]) == 3 and not [t for t, _ in entradas if 12000 < t < 20000],
    "três filas, uma entrada só (sem divisão no tempo)",
)
divididas = [(t, f) for t, f in entradas if 20000 <= t < 30000]
verificar(
    len(divididas) == 2 and divididas[0][0] == 20000 and divididas[1][0] == 25000,
    f"mais de três: duas entradas, a 20 s e a meio do intervalo ({[t for t, _ in divididas]})",
)
verificar(all(len(f) <= 3 for _, f in entradas), "nenhuma entrada com mais de 3 filas")
verificar(por_tempo[10000] == [], "a linha vazia dá uma entrada vazia")

print()
print("4. Caracteres")
verificar(L.transliterar("It’s") == "It's", "aspa tipográfica")
verificar(L.transliterar("mе") == "me", "e cirílico")
verificar(L.transliterar("não, ação") == "não, ação", "til e cedilha ficam")
verificar(L.transliterar("ŝalom") == "salom", "ŝ perde o acento")
verificar(L.transliterar("東京") is None, "outra escrita: desiste")
mista = L.montar_entradas([(0, "東京"), (1000, "depois")])
verificar(mista == [[0, []], [1000, ["depois"]]], "só a linha fica vazia, a letra continua")

pasta = Path(tempfile.mkdtemp(prefix="t36-"))
try:
    print()
    print("5. O LRCLIB")
    s, sessao, esperas = servico([Resposta(200, {"syncedLyrics": LRC})], pasta)
    letra = s.obter("spotify:track:A", "Canção", "Ninguém, Outro", "Álbum", 183400)
    verificar(letra["estado"] == "sincronizada" and letra["linhas"], "/api/get encontra")
    verificar(
        sessao.pedidos[0] == ("get", {"track_name": "Canção", "artist_name": "Ninguém",
                                      "album_name": "Álbum", "duration": 183}),
        f"com a duração em segundos e o primeiro artista: {sessao.pedidos[0]}",
    )

    s, sessao, _ = servico([
        Resposta(404),
        Resposta(200, []),
        Resposta(200, [{"trackName": "Istanbul", "artistName": "Ninguém", "syncedLyrics": LRC}]),
    ], pasta)
    letra = s.obter("spotify:track:B", "Istanbul (feat. X) - Live From Malibu", "Ninguém", None, 200000)
    verificar(
        letra["estado"] == "sincronizada" and sessao.pedidos[2][1]["track_name"] == "Istanbul",
        f"sem resultado com o nome inteiro, tenta sem sufixo: {[p[1].get('track_name') for p in sessao.pedidos]}",
    )

    s, sessao, esperas = servico([Resposta(503), Resposta(503), Resposta(200, {"syncedLyrics": LRC})], pasta)
    letra = s.obter("spotify:track:C", "c", "a", None, 100000)
    verificar(letra["estado"] == "sincronizada" and esperas == [1, 2], f"503 repetido, esperas {esperas}")

    s, sessao, esperas = servico([Resposta(503)] * 4, pasta)
    letra = s.obter("spotify:track:D", "d", "a", None, 100000)
    verificar(
        letra == {"cols": 21, "filas": 3, "linhas": [], "estado": "sem_letra", "motivo": "indisponivel"}
        and esperas == [1, 2, 4],
        f"503 sempre: sem letra, indisponível, esperas {esperas}",
    )
    verificar(not (pasta / "spotify_track_D.json").exists(), "o indisponível NÃO fica em cache")

    s, _, _ = servico([Resposta(200, {"instrumental": True})], pasta)
    verificar(s.obter("spotify:track:E", "e", "a", None, 1000)["motivo"] == "instrumental", "instrumental")

    print()
    print("6. A cache")
    s, sessao, _ = servico([], pasta)
    letra = s.obter("spotify:track:A", "Canção", "Ninguém", "Álbum", 183400)
    verificar(letra["estado"] == "sincronizada" and not sessao.pedidos, "a segunda vez não pergunta")

    s, sessao, _ = servico([Resposta(404), Resposta(200, [])], pasta, agora=1_000_000.0)
    verificar(s.obter("spotify:track:F", "f", "a", None, 1000)["motivo"] == "nao_existe", "não existe")
    s, sessao, _ = servico([], pasta, agora=1_000_000.0 + 29 * 86400)
    s.obter("spotify:track:F", "f", "a", None, 1000)
    verificar(not sessao.pedidos, "o \"não há\" com 29 dias não pergunta")
    s, sessao, _ = servico([Resposta(404), Resposta(200, [])], pasta, agora=1_000_000.0 + 31 * 86400)
    s.obter("spotify:track:F", "f", "a", None, 1000)
    verificar(len(sessao.pedidos) == 2, "o \"não há\" com 31 dias volta a perguntar")

finally:
    shutil.rmtree(pasta, ignore_errors=True)

print()
print("7. Tudo cabe na fonte do nó")
saidas = [f for _, filas_ in L.montar_entradas(L.ler_lrc(LRC)) for f in filas_]
verificar(all(len(f) <= 21 for f in saidas), "nenhuma fila com mais de 21")
verificar(all(c in L.CONJUNTO for f in saidas for c in f), "nenhum carácter fora da fonte")

print()
if falhas:
    print(f"T36 FALHOU — {len(falhas)} verificação(ões)")
    sys.exit(1)

print("T36 PASSA")
