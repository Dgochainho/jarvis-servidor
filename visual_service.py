"""
O servidor da camada visual (Fase 8.d): WebSocket em :8766/visual, só push.

O nó (o Matrix Portal, ou por agora a matriz virtual em /matriz) nunca fala
com o Spotify nem com o LRCLIB. Liga-se aqui, recebe o estado inteiro de uma
vez, e depois só o que muda. Mensagens do PDF de 12-10:

    {"t": "track",  "id", "titulo", "artista", "duration_ms",
                    "progress_ms", "server_time_ms", "paleta": {dom, a1, a2}}
    {"t": "letras", "id", "estado", "motivo", "cols", "filas",
                    "linhas": [[t_ms, [fila, …]], …]}
    {"t": "estado", "id", "a_tocar", "progress_ms", "server_time_ms"}

O relógio (L4 do docs/FASE-8.d-letras.md):

  - a âncora é o MEIO da ida ao Spotify, não o fim — medido nos logs, isso
    vale ~0,45 s;
  - uma leitura que tenha demorado mais de 2 s não corrige o relógio;
  - o `progress_ms` de cada mensagem já vem levado até ao instante em que a
    mensagem sai. O nó soma-lhe o tempo que passou desde que a recebeu, no
    relógio dele. Assim não precisa de ter o relógio acertado com o do
    servidor — o que o PDF fazia com `server_time_ms - progress_ms`, e que só
    funciona se os dois relógios concordarem.

De onde vem o estado (L5): `spotify.get_status(max_age_seconds=5)` uma vez
por segundo. Com a BOX ligada reaproveita o polling dela; sem a BOX, uma ida
ao Spotify a cada 5 s no máximo. O /api/status não é tocado.

Como o servidor de voz, e pela mesma razão (B5): se a porta não abrir, o
arranque inteiro falha.
"""

import asyncio
import json
import threading
import time
from typing import Optional

from websockets.asyncio.server import ServerConnection, broadcast, serve

from lyrics_service import partir_filas, transliterar


VISUAL_WS_PATH = "/visual"

INTERVALO_S = 1.0
MAX_IDADE_ESTADO_S = 5.0

# Medido a 2026-10-20: p90 1,33 s, p99 10 s. Acima disto a leitura não diz
# com precisão a que instante se refere o progress_ms.
PEDIDO_LENTO_MS = 2000


def _agora_ms():
    return int(time.time() * 1000)


class Relogio:
    """
    Onde vai a música, a partir das leituras do Spotify.

    Guarda uma âncora — (progress_ms, instante a que se refere, a tocar) — e
    extrapola dela. Só a troca por uma leitura nova que seja de confiança, ou
    quando a faixa ou o estado de reprodução mudaram (aí, uma leitura lenta é
    melhor do que nenhuma).
    """

    def __init__(self):
        self.track_id = None
        self.a_tocar = False
        self.duracao_ms = 0
        self._progresso_ms = 0
        self._instante_ms = 0
        self._ultima_leitura = None

    def actualizar(self, status):
        """Devolve True se a âncora mudou."""
        leitura = status.get("server_time_ms")

        if leitura is None or leitura == self._ultima_leitura:
            return False

        self._ultima_leitura = leitura

        activo = bool(status.get("active"))
        track_id = status.get("track_id") if activo else None
        a_tocar = activo and bool(status.get("playing"))
        pedido_ms = status.get("pedido_ms") or 0

        mudou_algo = track_id != self.track_id or a_tocar != self.a_tocar

        if pedido_ms > PEDIDO_LENTO_MS and not mudou_algo:
            return False

        self.track_id = track_id
        self.a_tocar = a_tocar
        self.duracao_ms = status.get("duration_ms") or 0
        self._progresso_ms = status.get("progress_ms") or 0
        self._instante_ms = leitura - pedido_ms // 2

        return True

    def progresso(self, agora_ms=None):
        agora_ms = _agora_ms() if agora_ms is None else agora_ms

        if not self.a_tocar:
            return self._progresso_ms

        valor = self._progresso_ms + (agora_ms - self._instante_ms)

        if self.duracao_ms:
            valor = min(valor, self.duracao_ms)

        return max(0, int(valor))


def mensagem_track(status, paleta, relogio, agora_ms=None):
    agora_ms = _agora_ms() if agora_ms is None else agora_ms

    if not relogio.track_id:
        return {"t": "track", "id": None, "server_time_ms": agora_ms}

    paleta = paleta or {}

    def cor(chave):
        return (paleta.get(chave) or {}).get("hex")

    return {
        "t": "track",
        "id": relogio.track_id,
        # Só caracteres da fonte chegam ao nó (L3), também aqui.
        "titulo": transliterar(status.get("track") or "") or "",
        "artista": transliterar(status.get("artist") or "") or "",
        "duration_ms": relogio.duracao_ms,
        "progress_ms": relogio.progresso(agora_ms),
        "server_time_ms": agora_ms,
        # dom: a dominante; a1: o realce; a2: a mais viva — os nomes da 8.a.
        "paleta": {"dom": cor("dominante"), "a1": cor("realce"), "a2": cor("mais_viva")},
    }


def mensagem_estado(relogio, agora_ms=None):
    agora_ms = _agora_ms() if agora_ms is None else agora_ms

    return {
        "t": "estado",
        "id": relogio.track_id,
        "a_tocar": relogio.a_tocar,
        "progress_ms": relogio.progresso(agora_ms),
        "server_time_ms": agora_ms,
    }


def mensagem_letras(track_id, letra, titulo="", artista=""):
    """
    A mensagem `letras`. Sem letra (L6), uma única entrada no instante 0 com
    o título e o artista: o nó desenha-a como qualquer outra e não precisa de
    saber que o caso existe. Um terço das faixas medidas não tem letra.
    """
    mensagem = {"t": "letras", "id": track_id, **letra}

    if letra.get("estado") != "sincronizada":
        filas_titulo = partir_filas(transliterar(titulo) or "", letra["cols"])
        filas_artista = partir_filas(transliterar(artista) or "", letra["cols"])
        filas = (filas_titulo[:2] + filas_artista[:1])[: letra["filas"]]
        mensagem["linhas"] = [[0, filas]] if filas else []

    return mensagem


class VisualService:

    def __init__(self, spotify, cover_service, lyrics, host="0.0.0.0", port=8766):
        self.host = host
        self.port = port

        self._spotify = spotify
        self._cover = cover_service
        self._lyrics = lyrics

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._started = threading.Event()
        self._startup_error: Optional[BaseException] = None

        self._clientes: set = set()
        self._relogio = Relogio()
        self._track = {"t": "track", "id": None}
        self._letras = None

    # -- arranque e paragem, como o LiveVoiceWebSocketServer ----------

    def start(self, timeout=10.0):
        if self._thread is not None and self._thread.is_alive():
            return

        self._started.clear()
        self._startup_error = None

        self._thread = threading.Thread(target=self._thread_main, name="jarvis-visual-ws", daemon=True)
        self._thread.start()

        if not self._started.wait(timeout):
            raise RuntimeError("Timeout ao iniciar o servidor visual")

        if self._startup_error is not None:
            raise RuntimeError("Falha ao iniciar o servidor visual") from self._startup_error

    def stop(self, timeout=5.0):
        loop, stop_event = self._loop, self._stop_event

        if loop is not None and stop_event is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(stop_event.set)
            except RuntimeError:
                # O loop já fechou (arranque falhado). Ver o mesmo caso no
                # live_voice_ws_server: sem isto, o erro verdadeiro do
                # arranque era tapado por "Event loop is closed".
                pass

        if self._thread is not None:
            self._thread.join(timeout=timeout)

        self._thread = None
        self._loop = None
        self._stop_event = None

    def _thread_main(self):
        try:
            asyncio.run(self._run_server())
        except BaseException as exc:
            # Primeiro registar, depois libertar o start() — a ordem do B5.
            self._startup_error = exc
            print(f"[VISUAL] ERRO fatal: {type(exc).__name__}: {exc}")
        finally:
            self._started.set()

    async def _run_server(self):
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()

        async with serve(
            self._handle,
            self.host,
            self.port,
            compression=None,
            ping_interval=20,
            ping_timeout=20,
        ):
            print(f"[VISUAL] Push em ws://{self.host}:{self.port}{VISUAL_WS_PATH}")
            self._started.set()

            ciclo = asyncio.create_task(self._ciclo(), name="visual-ciclo")

            try:
                await self._stop_event.wait()
            finally:
                ciclo.cancel()

    # -- clientes -----------------------------------------------------

    async def _handle(self, ws: ServerConnection):
        if ws.request is None or ws.request.path != VISUAL_WS_PATH:
            await ws.close(1008, "caminho desconhecido")
            return

        print(f"[VISUAL] Cliente ligado: {ws.remote_address}")
        self._clientes.add(ws)

        try:
            # O estado inteiro de uma vez: quem chega a meio de uma música
            # tem logo a letra e o relógio.
            await ws.send(json.dumps(self._track, ensure_ascii=False))
            if self._letras is not None:
                await ws.send(json.dumps(self._letras, ensure_ascii=False))
            await ws.send(json.dumps(mensagem_estado(self._relogio), ensure_ascii=False))

            await ws.wait_closed()
        finally:
            self._clientes.discard(ws)
            print(f"[VISUAL] Cliente desligado: {ws.remote_address}")

    def _enviar(self, mensagem):
        if self._clientes:
            broadcast(self._clientes, json.dumps(mensagem, ensure_ascii=False))

    # -- o ciclo ------------------------------------------------------

    async def _ciclo(self):
        while True:
            try:
                await self._passo()
            except asyncio.CancelledError:
                raise
            except Exception as erro:
                # Uma falha num segundo não pode matar a camada visual.
                print(f"[VISUAL] Falha no ciclo: {type(erro).__name__}: {erro}")

            await asyncio.sleep(INTERVALO_S)

    async def _passo(self):
        status, codigo = await asyncio.to_thread(
            self._spotify.get_status, max_age_seconds=MAX_IDADE_ESTADO_S
        )

        if codigo != 200:
            return

        anterior = self._relogio.track_id
        self._relogio.actualizar(status)

        if self._relogio.track_id != anterior:
            await self._nova_faixa(status)

        self._enviar(mensagem_estado(self._relogio))

    async def _nova_faixa(self, status):
        track_id = self._relogio.track_id

        paleta = None
        if track_id and status.get("cover"):
            try:
                paleta = await asyncio.to_thread(self._cover.get_paleta, status["cover"])
            except Exception as erro:
                print(f"[VISUAL] Sem paleta: {erro}")

        self._track = mensagem_track(status, paleta, self._relogio)
        self._letras = None
        self._enviar(self._track)

        if not track_id:
            return

        print(f"[VISUAL] Faixa: {status.get('track')} — {status.get('artist')}")

        letra = await asyncio.to_thread(
            self._lyrics.obter,
            track_id,
            status.get("track") or "",
            status.get("artist") or "",
            status.get("album"),
            status.get("duration_ms"),
        )

        # A música pode ter mudado enquanto se esperava pelo LRCLIB.
        if self._relogio.track_id != track_id:
            return

        self._letras = mensagem_letras(
            track_id, letra, status.get("track") or "", status.get("artist") or ""
        )
        self._enviar(self._letras)

        print(
            f"[VISUAL] Letra: {letra['estado']} ({letra.get('motivo')}), "
            f"{len(letra['linhas'])} entradas"
        )
