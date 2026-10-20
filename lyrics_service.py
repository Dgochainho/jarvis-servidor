"""
Letras sincronizadas para a matriz (Fase 8.d).

Vai buscar a letra ao LRCLIB, guarda-a em cache no disco, e devolve-a já
partida em filas de 21 caracteres, só com caracteres que a fonte do nó tem.
O nó não parte nem translitera nada (PDF de 12-10).

Ver `docs/FASE-8.d-letras.md`. As decisões L1, L2 e L3 estão aqui:

  L1  /api/get com a duração; senão /api/search; 503 repete a 1, 2 e 4 s;
      cache por faixa, incluindo o "não há", que expira ao fim de 30 dias.
  L2  ≤ 3 filas: uma entrada. Mais do que isso: divide no tempo.
  L3  transliterar o que tem equivalente; senão tirar o acento; senão a
      LINHA fica vazia, não a letra.

A cache guarda o LRC em bruto, não as filas: mudar a regra de quebra aplica-se
às letras já guardadas sem voltar a perguntar nada. Fica fora do git
(`letras_cache/`) — é texto de terceiros, para uso pessoal.
"""

import json
import math
import re
import time
import unicodedata
from pathlib import Path

import requests


COLS = 21
FILAS = 3

API = "https://lrclib.net/api"
CABECALHOS = {"User-Agent": "Jarvis/8.d (uso pessoal, ESP32-S3-BOX-3)"}

# Medido a 2026-10-20 (diagnostico_letras.py): entre 6 e 26 pedidos em 77
# precisaram de repetir por 503, alguns até à 4.ª tentativa.
ESPERAS_503 = (1, 2, 4)

PASTA_CACHE = Path(__file__).with_name("letras_cache")

# O LRCLIB é contribuído e vai crescendo: o "não há" de hoje pode ser o
# "há" do mês que vem.
NAO_HA_EXPIRA_S = 30 * 24 * 3600

# A última linha não tem "seguinte" que lhe dê duração; para a dividir no
# tempo (L2) usa-se isto.
DURACAO_ULTIMA_MS = 4000

FONTE = Path(__file__).with_name("fontes") / "fonte_5x8.json"


def _conjunto_da_fonte():
    tabela = json.loads(FONTE.read_text(encoding="utf-8"))
    return frozenset(chr(int(codigo)) for codigo in tabela["glifos"])


CONJUNTO = _conjunto_da_fonte()


# ---------------------------------------------------------
# L3 — caracteres
# ---------------------------------------------------------

# Os que a medição encontrou (’ e o е cirílico) e os da mesma família: a
# tipografia e as letras de outras escritas que são iguais às latinas à
# vista, e que aparecem em letras escritas à mão por utilizadores.
TRANSLITERACAO = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "―": "-", "−": "-",
    "…": "...", "•": "·", " ": " ", " ": " ", "​": "",
    # Cirílico
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ј": "j", "ѕ": "s", "А": "A", "В": "B", "Е": "E", "К": "K",
    "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X",
    # Grego
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "ο": "o",
})


def transliterar(texto, conjunto=CONJUNTO):
    """
    O texto só com caracteres de `conjunto`, ou None se não der.

    Primeiro a tabela; depois, para o que sobrar, a decomposição Unicode (um
    `ŝ` dá `s`); se ainda assim ficar alguma coisa fora, desiste — e quem
    chama deixa a LINHA vazia, não a letra inteira.
    """
    texto = texto.translate(TRANSLITERACAO)
    saida = []

    for c in texto:
        if c in conjunto:
            saida.append(c)
            continue

        base = "".join(
            d for d in unicodedata.normalize("NFKD", c)
            if not unicodedata.combining(d)
        )

        if base and all(d in conjunto for d in base):
            saida.append(base)
        else:
            return None

    return "".join(saida)


# ---------------------------------------------------------
# L2 — filas
# ---------------------------------------------------------

def partir_filas(texto, cols=COLS):
    """Parte por palavras em filas de até `cols`. Uma palavra maior corta-se."""
    filas = []
    actual = ""

    for palavra in texto.split():
        while len(palavra) > cols:
            if actual:
                filas.append(actual)
                actual = ""
            filas.append(palavra[:cols])
            palavra = palavra[cols:]

        if not actual:
            actual = palavra
        elif len(actual) + 1 + len(palavra) <= cols:
            actual += " " + palavra
        else:
            filas.append(actual)
            actual = palavra

    if actual:
        filas.append(actual)

    return filas


def montar_entradas(linhas, cols=COLS, filas=FILAS):
    """
    [(t_ms, texto)] → [[t_ms, [fila, …]]], cada entrada com ≤ `filas` filas.

    Uma linha que precise de mais filas divide-se em partes iguais no tempo
    até à linha seguinte (L2): no corpus de 2026-10-20 foi 1,6% das linhas, e
    a mais comprida dava cinco filas.
    """
    entradas = []

    for i, (t, texto) in enumerate(linhas):
        limpo = transliterar(texto)
        todas = partir_filas(limpo, cols) if limpo else []

        if len(todas) <= filas:
            entradas.append([t, todas])
            continue

        seguinte = linhas[i + 1][0] if i + 1 < len(linhas) else t + DURACAO_ULTIMA_MS
        partes = math.ceil(len(todas) / filas)
        passo = (seguinte - t) / partes

        for parte in range(partes):
            entradas.append([
                int(t + parte * passo),
                todas[parte * filas:(parte + 1) * filas],
            ])

    return entradas


# ---------------------------------------------------------
# LRC
# ---------------------------------------------------------

_TEMPO = re.compile(r"\[(\d+):(\d{1,2}(?:\.\d{1,3})?)\]")
_OFFSET = re.compile(r"^\s*\[offset:\s*([+-]?\d+)\s*\]", re.I | re.M)


def ler_lrc(lrc):
    """
    LRC → [(t_ms, texto)], por ordem de tempo.

    Aceita vários tempos à cabeça da mesma linha (refrões repetidos), ignora as
    etiquetas de metadados ([ar:], [ti:]…) e aplica o [offset:] — que, na
    convenção do LRC, positivo quer dizer "mais cedo".
    """
    m = _OFFSET.search(lrc)
    offset = int(m.group(1)) if m else 0

    linhas = []

    for bruta in lrc.splitlines():
        tempos = []
        resto = bruta.strip()

        while True:
            m = _TEMPO.match(resto)
            if not m:
                break
            tempos.append(int(m.group(1)) * 60000 + round(float(m.group(2)) * 1000))
            resto = resto[m.end():]

        for t in tempos:
            linhas.append((max(0, t - offset), resto.strip()))

    linhas.sort(key=lambda par: par[0])
    return linhas


# ---------------------------------------------------------
# L1 — o LRCLIB e a cache
# ---------------------------------------------------------

def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


_SUFIXO = re.compile(r"\s*(\(feat\.?[^)]*\)|\[feat\.?[^]]*\]|\s-\s.*)$", re.I)


def sem_sufixo(faixa):
    """`Istanbul (feat. X) - Live From Malibu` → `Istanbul`."""
    anterior = None
    while anterior != faixa:
        anterior = faixa
        faixa = _SUFIXO.sub("", faixa).strip()
    return faixa


def _escolher(resultados, faixa, artista):
    """O critério do diagnostico_letras.py: mesmo artista, nome mais parecido."""
    alvo_faixa = _normalizar(faixa)
    alvo_artista = _normalizar(artista)

    candidatos = [
        r for r in resultados
        if alvo_artista and alvo_artista in _normalizar(r.get("artistName"))
    ]

    def pontos(r):
        nome = _normalizar(r.get("trackName"))
        return (
            nome == alvo_faixa,
            nome.startswith(alvo_faixa) or alvo_faixa.startswith(nome),
            bool(r.get("syncedLyrics")),
        )

    if not candidatos:
        return None

    melhor = max(candidatos, key=pontos)
    return melhor if pontos(melhor)[:2] != (False, False) else None


class LetraIndisponivel(Exception):
    """O LRCLIB não respondeu. Não se guarda em cache: tenta-se outra vez."""


class LyricsService:

    def __init__(self, sessao=None, pasta_cache=PASTA_CACHE, dormir=time.sleep, agora=time.time):
        self._sessao = sessao or requests.Session()
        self._pasta = Path(pasta_cache)
        self._dormir = dormir
        self._agora = agora

    # -- HTTP -------------------------------------------------

    def _pedir(self, caminho, params):
        """GET ao LRCLIB, com os 503 repetidos. Devolve o JSON, ou None no 404."""
        for espera in ESPERAS_503 + (None,):
            try:
                resposta = self._sessao.get(
                    f"{API}/{caminho}", params=params, headers=CABECALHOS, timeout=10,
                )
            except requests.RequestException as erro:
                if espera is None:
                    raise LetraIndisponivel(str(erro)) from erro
                self._dormir(espera)
                continue

            if resposta.status_code == 503 and espera is not None:
                self._dormir(espera)
                continue

            if resposta.status_code == 404:
                return None

            if resposta.status_code != 200:
                raise LetraIndisponivel(f"LRCLIB respondeu {resposta.status_code}")

            return resposta.json()

        raise LetraIndisponivel("503 em todas as tentativas")

    def _procurar(self, faixa, artista, album, duracao_ms):
        """O registo do LRCLIB para esta faixa, ou None se não houver."""
        artista = (artista or "").split(",")[0].strip()

        if duracao_ms:
            registo = self._pedir("get", {
                "track_name": faixa,
                "artist_name": artista,
                "album_name": album or "",
                "duration": round(duracao_ms / 1000),
            })
            if registo:
                return registo

        for nome in dict.fromkeys((faixa, sem_sufixo(faixa))):
            resultados = self._pedir("search", {"track_name": nome, "artist_name": artista}) or []
            registo = _escolher(resultados, nome, artista)
            if registo:
                return registo

        return None

    # -- cache ------------------------------------------------

    def _ficheiro(self, track_id):
        return self._pasta / (re.sub(r"[^A-Za-z0-9_-]", "_", track_id) + ".json")

    def _ler_cache(self, track_id):
        ficheiro = self._ficheiro(track_id)
        if not ficheiro.exists():
            return None

        try:
            guardado = json.loads(ficheiro.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if guardado.get("lrc") is None and (
            self._agora() - guardado.get("guardado", 0) > NAO_HA_EXPIRA_S
        ):
            return None

        return guardado

    def _escrever_cache(self, track_id, lrc, motivo):
        try:
            self._pasta.mkdir(exist_ok=True)
            self._ficheiro(track_id).write_text(
                json.dumps(
                    {"lrc": lrc, "motivo": motivo, "guardado": int(self._agora())},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError as erro:
            # A cache é para poupar pedidos, não para fazer parte do sistema.
            print(f"[LETRAS] Falhou a escrita da cache: {erro}")

    # -- o que o visual_service chama -------------------------

    def obter(self, track_id, faixa, artista, album=None, duracao_ms=None):
        """
        A letra desta faixa, pronta para o nó:

            {"estado": "sincronizada" | "sem_letra",
             "motivo": …, "cols": 21, "filas": 3,
             "linhas": [[t_ms, [fila, …]], …]}

        Nunca levanta excepção: sem letra, ou com o LRCLIB em baixo, devolve
        "sem_letra" — e o nó mostra o título e o artista (L6).
        """
        resposta = {"cols": COLS, "filas": FILAS, "linhas": []}

        guardado = self._ler_cache(track_id) if track_id else None

        if guardado is None:
            try:
                registo = self._procurar(faixa, artista, album, duracao_ms)
            except LetraIndisponivel as erro:
                print(f"[LETRAS] LRCLIB indisponível ({faixa!r}): {erro}")
                return {**resposta, "estado": "sem_letra", "motivo": "indisponivel"}
            except Exception as erro:
                print(f"[LETRAS] Falha inesperada ({faixa!r}): {erro}")
                return {**resposta, "estado": "sem_letra", "motivo": "erro"}

            if registo is None:
                lrc, motivo = None, "nao_existe"
            elif registo.get("syncedLyrics"):
                lrc, motivo = registo["syncedLyrics"], "lrclib"
            elif registo.get("instrumental"):
                lrc, motivo = None, "instrumental"
            else:
                lrc, motivo = None, "so_texto"

            if track_id:
                self._escrever_cache(track_id, lrc, motivo)

            guardado = {"lrc": lrc, "motivo": motivo}

        if not guardado.get("lrc"):
            return {**resposta, "estado": "sem_letra", "motivo": guardado.get("motivo")}

        return {
            **resposta,
            "estado": "sincronizada",
            "motivo": guardado.get("motivo"),
            "linhas": montar_entradas(ler_lrc(guardado["lrc"])),
        }
