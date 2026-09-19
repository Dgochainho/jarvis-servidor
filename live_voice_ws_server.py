import asyncio
import os
import struct
import threading
import time
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from action_service import execute_spotify_action


load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY não encontrada no .env"
    )


MODEL = "gemini-3.1-flash-live-preview"

VOICE_WS_PATH = "/voice"

# A BOX cancela sozinha se não encontrar fala poucos segundos após WAKE.
TURN_START_TIMEOUT_SECONDS = 10


# O firmware limita o comando a 12 s; estes timeouts são defensivos.
TURN_INPUT_TIMEOUT_SECONDS = 20
TURN_RESPONSE_TIMEOUT_SECONDS = 80
GEMINI_TURN_TOTAL_TIMEOUT_SECONDS = 120
CONVERSATION_IDLE_SECONDS = 30

# A BOX só processa mensagens de controlo com menos de 96 bytes.
FIRMWARE_CONTROL_MAX_BYTES = 95

# PCM16 mono a 16 kHz = 32 000 bytes/s.
INPUT_BYTES_PER_SECOND = 32_000

# Fragmentamos a resposta para não entregar mensagens WebSocket grandes
# ao cliente ESP32. 1024 bytes correspondem a 32 ms de áudio a 16 kHz.
# Isto reduz o tempo bloqueado dentro do callback de reprodução da BOX.
OUTPUT_WS_CHUNK_BYTES = 1024

_QUEUE_START = object()
_QUEUE_END = object()
_QUEUE_CANCEL = object()


@dataclass
class TurnStats:
    """Métricas medidas no instante em que o PC recebe áudio da BOX."""

    wake_received_at: float
    start_received_at: Optional[float] = None
    first_pcm_received_at: Optional[float] = None
    end_received_at: Optional[float] = None
    bytes_received: int = 0

    @property
    def pcm_duration_seconds(self) -> float:
        return self.bytes_received / INPUT_BYTES_PER_SECOND

    @property
    def receive_wall_seconds(self) -> float:
        if (
            self.first_pcm_received_at is None
            or self.end_received_at is None
        ):
            return 0.0

        return self.end_received_at - self.first_pcm_received_at


class Pcm24kTo16k:
    """Conversor stateful PCM16 mono, 24 kHz -> 16 kHz."""

    def __init__(self) -> None:
        self.carry = b""

    def convert(self, pcm24: bytes) -> bytes:
        data = self.carry + pcm24

        # 3 amostras PCM16 = 6 bytes e produzem 2 amostras.
        usable = (len(data) // 6) * 6

        if usable == 0:
            self.carry = data
            return b""

        output = bytearray()

        for offset in range(0, usable, 6):
            a, b, c = struct.unpack_from(
                "<hhh",
                data,
                offset,
            )

            # Razão exata 3:2. A segunda amostra fica a meio de b e c.
            out1 = a
            out2 = int((int(b) + int(c)) / 2)

            output.extend(
                struct.pack(
                    "<hh",
                    out1,
                    out2,
                )
            )

        self.carry = data[usable:]
        return bytes(output)


class LiveVoiceWebSocketServer:
    """
    Servidor WebSocket persistente BOX <-> PC.

    Protocolo:
        servidor -> READY

        BOX -> WAKE
        BOX -> START
        BOX -> frames binários PCM16 / 16 kHz / mono
        BOX -> END

        servidor -> frames binários PCM16 / 16 kHz / mono
        servidor -> DONE

    Depois de DONE, a mesma ligação fica aberta para o próximo WAKE.
    CANCEL abandona o turno atual sem desligar a BOX.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
    ) -> None:
        self.host = host
        self.port = port

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._started = threading.Event()
        self._startup_error: Optional[BaseException] = None
        self._connection_lock: Optional[asyncio.Lock] = None

    def start(
        self,
        timeout: float = 10.0,
    ) -> None:
        if (
            self._thread is not None
            and self._thread.is_alive()
        ):
            return

        self._started.clear()
        self._startup_error = None

        self._thread = threading.Thread(
            target=self._thread_main,
            name="jarvis-voice-ws",
            daemon=True,
        )
        self._thread.start()

        if not self._started.wait(timeout):
            raise RuntimeError(
                "Timeout ao iniciar o servidor WebSocket de voz"
            )

        if self._startup_error is not None:
            raise RuntimeError(
                "Falha ao iniciar servidor WebSocket de voz"
            ) from self._startup_error

    def stop(
        self,
        timeout: float = 5.0,
    ) -> None:
        loop = self._loop
        stop_event = self._stop_event

        if (
            loop is not None
            and stop_event is not None
        ):
            loop.call_soon_threadsafe(
                stop_event.set
            )

        thread = self._thread

        if thread is not None:
            thread.join(timeout=timeout)

            if thread.is_alive():
                print(
                    "[VOICE-WS] Aviso: thread do servidor "
                    "ainda não terminou"
                )
                return

        self._thread = None
        self._loop = None
        self._stop_event = None

    def _thread_main(self) -> None:
        try:
            asyncio.run(
                self._run_server()
            )

        except BaseException as exc:
            self._startup_error = exc
            self._started.set()

            print(
                "[VOICE-WS] ERRO fatal: "
                f"{self._format_exception(exc)}"
            )

    async def _run_server(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._connection_lock = asyncio.Lock()

        try:
            async with serve(
                self._handle_connection,
                self.host,
                self.port,
                compression=None,
                max_size=64 * 1024,

                # A BOX envia frames de 512 bytes a ~62,5 frames/s.
                # 1024 posições cobrem mais do que o máximo de 12 s.
                max_queue=1024,

                write_limit=64 * 1024,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            ):
                print()
                print(
                    "[VOICE-WS] ====================================="
                )
                print(
                    f"[VOICE-WS] Persistente em "
                    f"ws://{self.host}:{self.port}{VOICE_WS_PATH}"
                )
                print(
                    "[VOICE-WS] ====================================="
                )
                print()

                self._started.set()
                await self._stop_event.wait()

        except BaseException:
            self._started.set()
            raise

    async def _handle_connection(
        self,
        websocket: ServerConnection,
    ) -> None:
        path = getattr(
            getattr(websocket, "request", None),
            "path",
            "",
        )

        if path != VOICE_WS_PATH:
            await websocket.close(
                code=1008,
                reason="Caminho WebSocket inválido",
            )
            return

        assert self._connection_lock is not None

        # Só existe uma BOX. Não deixamos uma segunda ligação pendurada.
        if self._connection_lock.locked():
            await websocket.close(
                code=1013,
                reason="Já existe uma BOX ligada",
            )
            return

        async with self._connection_lock:
            peer = websocket.remote_address
            print(
                f"[VOICE-WS] BOX persistente ligada: {peer}"
            )

            try:
                # READY significa que o WebSocket PC está operacional.
                # A sessão Gemini abre apenas quando chega WAKE.
                await asyncio.sleep(0.2)

                await websocket.send("READY")

                print(
                    "[VOICE-WS] READY enviado; à espera de Jarvis"
                )

                while True:
                    message = await websocket.recv()

                    if message == "WAKE":
                        print()
                        print(
                            "[VOICE-WS] >>> WAKE recebido <<<"
                        )

                        try:
                            result = await self._run_conversation(
                                websocket
                            )

                            if result == "done":
                                print(
                                    "[VOICE-WS] Conversa encerrada; "
                                    "à espera de novo Jarvis"
                                )
                            else:
                                print(
                                    "[VOICE-WS] Conversa cancelada; "
                                    "à espera de novo Jarvis"
                                )

                        except ConnectionClosed:
                            raise

                        except Exception as exc:
                            detail = self._format_exception(exc)

                            print(
                                "[VOICE-WS] ERRO na conversa: "
                                f"{detail}"
                            )

                            await self._send_error_control(
                                websocket,
                                exc,
                            )

                        continue

                    if message == "CANCEL":
                        # CANCEL fora de turno é inofensivo.
                        print(
                            "[VOICE-WS] CANCEL recebido fora de turno"
                        )
                        await websocket.send("DONE")
                        continue

                    if isinstance(message, bytes):
                        # Isto só deve ocorrer após uma falha no turno.
                        # Ignoramos silenciosamente para recuperar o
                        # alinhamento sem inundar o terminal de logs.
                        continue

                    if message in {"START", "END"}:
                        # Mensagem residual de uma interação falhada.
                        continue

                    print(
                        "[VOICE-WS] Mensagem inesperada em idle: "
                        f"{message!r}"
                    )

            except ConnectionClosed as exc:
                print(
                    f"[VOICE-WS] Ligação fechada: "
                    f"code={exc.code} reason={exc.reason}"
                )

            except Exception as exc:
                print(
                    "[VOICE-WS] ERRO da ligação: "
                    f"{self._format_exception(exc)}"
                )

            finally:
                print(
                    f"[VOICE-WS] BOX desligada: {peer}"
                )

    async def _run_conversation(
        self,
        websocket: ServerConnection,
    ) -> str:
        config = {
            "response_modalities": ["AUDIO"],

            "tools": [
                {
                    "function_declarations": [
                        {
                            "name": "spotify_control",
                            "description": (
                                "Controla a reprodução Spotify do utilizador. "
                                "Usa esta função para pausar, retomar, avançar "
                                "para a próxima música, voltar à música anterior "
                                "ou consultar a música atualmente selecionada."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "action": {
                                        "type": "string",
                                        "enum": [
                                            "pause",
                                            "resume",
                                            "next",
                                            "previous",
                                            "current_track",
                                        ],
                                        "description": (
                                            "A ação Spotify que deve ser executada."
                                        ),
                                    }
                                },
                                "required": ["action"],
                            },
                        }
                    ]
                }
            ],

            "input_audio_transcription": {},
            "output_audio_transcription": {},

            "realtime_input_config": {
                "automatic_activity_detection": {
                    "disabled": True
                }
            },

            "system_instruction": {
                "parts": [
                    {
                        "text": (
                            "És Jarvis, um assistente pessoal de "
                            "inteligência artificial. "
                            "Fala em português de Portugal, salvo se "
                            "o utilizador pedir outra língua. "
                            "Responde de forma natural, útil e "
                            "relativamente concisa. "

                            "Quando o utilizador pedir uma ação sobre o "
                            "Spotify, usa obrigatoriamente a ferramenta "
                            "spotify_control. "

                            "Usa-a também quando o utilizador perguntar "
                            "qual música está atualmente selecionada. "

                            "Para comandos Spotify, chama primeiro a "
                            "ferramenta e só depois responde verbalmente. "

                            "Nunca digas que uma ação Spotify foi executada "
                            "sem teres recebido sucesso da ferramenta."
                        )
                    }
                ]
            },
        }

        open_start = time.perf_counter()

        print(
            f"[VOICE-WS] A abrir Gemini {MODEL} "
            "para nova conversa..."
        )

        client = genai.Client(
            api_key=API_KEY
        )

        try:
            async with client.aio as async_client:
                async with async_client.live.connect(
                    model=MODEL,
                    config=config,
                ) as session:
                    open_seconds = (
                        time.perf_counter()
                        - open_start
                    )

                    print(
                        f"[VOICE-WS] Gemini pronto em "
                        f"{open_seconds:.2f} s"
                    )

                    print(
                        "[VOICE-WS] Nova conversa Gemini iniciada"
                    )

                    turn_number = 1

                    while True:
                        print(
                            f"[VOICE-WS] Conversa Gemini | "
                            f"turno {turn_number}"
                        )

                        result = await self._run_turn(
                            websocket,
                            session,
                        )

                        if result != "done":
                            return result

                        print(
                            "[VOICE-WS] Sessão Gemini mantida "
                            f"aberta por {CONVERSATION_IDLE_SECONDS} s"
                        )

                        idle_deadline = (
                            time.perf_counter()
                            + CONVERSATION_IDLE_SECONDS
                        )

                        while True:
                            remaining = (
                                idle_deadline
                                - time.perf_counter()
                            )

                            if remaining <= 0:
                                print(
                                    "[VOICE-WS] Tempo de conversa "
                                    "expirou; a fechar sessão Gemini"
                                )

                                await websocket.send("SLEEP")

                                print(
                                    "[VOICE-WS] SLEEP enviado à BOX"
                                )

                                return "done"

                            try:
                                message = await asyncio.wait_for(
                                    websocket.recv(),
                                    timeout=remaining,
                                )

                            except TimeoutError:
                                print(
                                    "[VOICE-WS] Tempo de conversa "
                                    "expirou; a fechar sessão Gemini"
                                )

                                await websocket.send("SLEEP")

                                print(
                                    "[VOICE-WS] SLEEP enviado à BOX"
                                )

                                return "done"

                            if message == "WAKE":
                                print()
                                print(
                                    "[VOICE-WS] >>> WAKE recebido "
                                    "na mesma conversa <<<"
                                )

                                turn_number += 1
                                break

                            if message == "CANCEL":
                                print(
                                    "[VOICE-WS] CANCEL recebido "
                                    "entre turnos"
                                )

                                await websocket.send("DONE")
                                continue

                            if isinstance(message, bytes):
                                # Frame residual de um turno anterior.
                                continue

                            if message in {"START", "END"}:
                                # Controlo residual de um turno anterior.
                                continue

                            print(
                                "[VOICE-WS] Mensagem inesperada "
                                "durante espera de conversa: "
                                f"{message!r}"
                            )

        finally:
            client.close()


    async def _run_turn(
        self,
        websocket: ServerConnection,
        session,
    ) -> str:
        # 12 s / 16 ms por frame = 750 frames, mais os controlos.
        input_queue: asyncio.Queue = asyncio.Queue(
            maxsize=1024
        )

        stats = TurnStats(
            wake_received_at=time.perf_counter()
        )

        receiver_task = asyncio.create_task(
            self._receive_turn_input(
                websocket,
                input_queue,
                stats,
            ),
            name="box-audio-receiver",
        )

        gemini_task = asyncio.create_task(
            asyncio.wait_for(
                self._gemini_turn(
                    session,
                    websocket,
                    input_queue,
                    stats,
                ),
                timeout=GEMINI_TURN_TOTAL_TIMEOUT_SECONDS,
            ),
            name="gemini-live-turn",
        )

        try:
            # Primeiro escoamos o protocolo da BOX até END/CANCEL.
            # Assim, mesmo se o Gemini falhar cedo, não deixamos PCM
            # residual a contaminar o próximo WAKE.
            receiver_result = await receiver_task

            if receiver_result == "cancelled":
                if not gemini_task.done():
                    gemini_task.cancel()

                await asyncio.gather(
                    gemini_task,
                    return_exceptions=True,
                )

                await websocket.send("DONE")
                return "cancelled"

            if receiver_result != "ended":
                raise RuntimeError(
                    "Estado de receção inesperado: "
                    f"{receiver_result!r}"
                )

            gemini_result = await gemini_task

            if gemini_result != "done":
                raise RuntimeError(
                    "Estado Gemini inesperado: "
                    f"{gemini_result!r}"
                )

            await websocket.send("DONE")
            return "done"

        finally:
            for task in (
                receiver_task,
                gemini_task,
            ):
                if not task.done():
                    task.cancel()

            await asyncio.gather(
                receiver_task,
                gemini_task,
                return_exceptions=True,
            )


    async def _receive_turn_input(
        self,
        websocket: ServerConnection,
        input_queue: asyncio.Queue,
        stats: TurnStats,
    ) -> str:
        first_message = await asyncio.wait_for(
            websocket.recv(),
            timeout=TURN_START_TIMEOUT_SECONDS,
        )

        if first_message == "CANCEL":
            await input_queue.put(_QUEUE_CANCEL)
            return "cancelled"

        if first_message != "START":
            raise RuntimeError(
                "Esperado START depois de WAKE; "
                f"recebido {first_message!r}"
            )

        stats.start_received_at = time.perf_counter()

        await input_queue.put(_QUEUE_START)

        print(
            "[VOICE-WS] START recebido; áudio BOX já pode entrar"
        )

        while True:
            message = await asyncio.wait_for(
                websocket.recv(),
                timeout=TURN_INPUT_TIMEOUT_SECONDS,
            )

            if isinstance(message, bytes):
                if not message:
                    continue

                if len(message) % 2 != 0:
                    raise RuntimeError(
                        "Frame PCM16 com número ímpar de bytes"
                    )

                now = time.perf_counter()

                if stats.first_pcm_received_at is None:
                    stats.first_pcm_received_at = now

                stats.bytes_received += len(message)

                await input_queue.put(message)
                continue

            if message == "END":
                stats.end_received_at = time.perf_counter()
                await input_queue.put(_QUEUE_END)
                return "ended"

            if message == "CANCEL":
                await input_queue.put(_QUEUE_CANCEL)
                return "cancelled"

            raise RuntimeError(
                "Mensagem de controlo desconhecida: "
                f"{message!r}"
            )


    async def _gemini_turn(
        self,
        session,
        websocket: ServerConnection,
        input_queue: asyncio.Queue,
        stats: TurnStats,
    ) -> str:
        first_item = await input_queue.get()

        if first_item is _QUEUE_CANCEL:
            return "cancelled"

        if first_item is not _QUEUE_START:
            raise RuntimeError(
                "Fila Live não começou com START"
            )

        await session.send_realtime_input(
            activity_start=types.ActivityStart()
        )

        print(
            "[VOICE-WS] START entregue ao Gemini"
        )

        bytes_forwarded = 0
        pacing_started_at = time.perf_counter()
        audio_seconds_forwarded = 0.0

        while True:
            item = await input_queue.get()

            if item is _QUEUE_CANCEL:
                return "cancelled"

            if item is _QUEUE_END:
                break

            if not isinstance(item, bytes):
                raise RuntimeError(
                    f"Item inesperado na fila: {item!r}"
                )

            target_send_at = (
                pacing_started_at
                + audio_seconds_forwarded
            )

            delay = (
                target_send_at
                - time.perf_counter()
            )

            if delay > 0:
                await asyncio.sleep(delay)

            await session.send_realtime_input(
                audio=types.Blob(
                    data=item,
                    mime_type="audio/pcm;rate=16000",
                )
            )

            bytes_forwarded += len(item)

            audio_seconds_forwarded += (
                len(item) / INPUT_BYTES_PER_SECOND
            )

        await session.send_realtime_input(
            activity_end=types.ActivityEnd()
        )

        print(
            f"[VOICE-WS] END entregue ao Gemini | "
            f"{bytes_forwarded} bytes encaminhados | "
            f"{stats.pcm_duration_seconds:.2f} s PCM | "
            f"{stats.receive_wall_seconds:.2f} s reais "
            f"entre primeiro PCM e END"
        )

        converter = Pcm24kTo16k()
        first_audio = True
        response_start = time.perf_counter()
        total_output = 0

        async with asyncio.timeout(
            TURN_RESPONSE_TIMEOUT_SECONDS
        ):
            async for response in session.receive():

                # -------------------------------------------------
                # TOOL CALLS - SPOTIFY
                # -------------------------------------------------

                if response.tool_call:
                    function_responses = []

                    for fc in response.tool_call.function_calls:
                        print(
                            f"[VOICE-WS] TOOL chamada: "
                            f"{fc.name} | args={fc.args}"
                        )

                        if fc.name == "spotify_control":
                            args = dict(fc.args or {})
                            action = args.get("action")

                            print(
                                "[VOICE-WS] Spotify solicitado: "
                                f"{action}"
                            )

                            result = await asyncio.to_thread(
                                execute_spotify_action,
                                action,
                            )

                            print(
                                "[VOICE-WS] Spotify resultado: "
                                f"{result}"
                            )

                        else:
                            result = {
                                "ok": False,
                                "message": (
                                    "Ferramenta desconhecida: "
                                    f"{fc.name}"
                                ),
                            }

                        function_responses.append(
                            types.FunctionResponse(
                                id=fc.id,
                                name=fc.name,
                                response={
                                    "result": result
                                },
                            )
                        )

                    await session.send_tool_response(
                        function_responses=
                            function_responses
                    )

                    print(
                        "[VOICE-WS] Resultado da TOOL "
                        "devolvido ao Gemini"
                    )

                    continue

                # -------------------------------------------------
                # RESPOSTA NORMAL DO GEMINI
                # -------------------------------------------------

                content = response.server_content

                if content is None:
                    continue

                if content.input_transcription:
                    value = (
                        content.input_transcription.text
                    )

                    if value:
                        print(
                            f"[VOICE-WS] Tu: {value}"
                        )

                if content.output_transcription:
                    value = (
                        content.output_transcription.text
                    )

                    if value:
                        print(
                            f"[VOICE-WS] Jarvis: {value}"
                        )

                if content.model_turn is None:
                    continue

                for part in content.model_turn.parts:
                    if (
                        part.inline_data is None
                        or part.inline_data.data is None
                    ):
                        continue

                    pcm16 = converter.convert(
                        part.inline_data.data
                    )

                    if not pcm16:
                        continue

                    if first_audio:
                        latency = (
                            time.perf_counter()
                            - response_start
                        )

                        print(
                            "[PERF] Primeiro áudio "
                            "Gemini Live WS: "
                            f"{latency:.2f} s"
                        )

                        first_audio = False

                    total_output += len(pcm16)

                    # 1024 B = 32 ms. Mantém as escritas no
                    # callback da BOX curtas e previsíveis.
                    for offset in range(
                        0,
                        len(pcm16),
                        OUTPUT_WS_CHUNK_BYTES,
                    ):
                        await websocket.send(
                            pcm16[
                                offset:
                                offset
                                + OUTPUT_WS_CHUNK_BYTES
                            ]
                        )

        if first_audio:
            raise RuntimeError(
                "Gemini Live terminou sem devolver áudio"
            )

        print(
            f"[VOICE-WS] Resposta concluída | "
            f"{total_output} bytes PCM16 / 16 kHz"
        )

        return "done"

    @staticmethod
    async def _send_error_control(
        websocket: ServerConnection,
        exc: BaseException,
    ) -> None:
        # O firmware só analisa texto com data_len < 96. Enviamos apenas
        # o tipo do erro; o detalhe completo já foi registado no PC.
        message = f"ERROR:{type(exc).__name__}"
        encoded = message.encode("ascii", errors="replace")
        encoded = encoded[:FIRMWARE_CONTROL_MAX_BYTES]

        try:
            await websocket.send(
                encoded.decode("ascii")
            )
        except ConnectionClosed:
            pass

    @staticmethod
    def _format_exception(
        exc: BaseException,
    ) -> str:
        text = str(exc).strip()

        if text:
            return f"{type(exc).__name__}: {text}"

        return f"{type(exc).__name__}: {exc!r}"
