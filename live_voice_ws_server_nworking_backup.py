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


load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY não encontrada no .env")


MODEL = "gemini-3.1-flash-live-preview"
VOICE_WS_PATH = "/voice"

TURN_START_TIMEOUT_SECONDS = 10
TURN_INPUT_TIMEOUT_SECONDS = 20
TURN_RESPONSE_TIMEOUT_SECONDS = 80
CONVERSATION_IDLE_TIMEOUT_SECONDS = 30

FIRMWARE_CONTROL_MAX_BYTES = 95
INPUT_BYTES_PER_SECOND = 32_000
OUTPUT_WS_CHUNK_BYTES = 1024

_QUEUE_START = object()
_QUEUE_END = object()
_QUEUE_CANCEL = object()


@dataclass
class TurnStats:
    started_at: float
    first_pcm_received_at: Optional[float] = None
    end_received_at: Optional[float] = None
    bytes_received: int = 0

    @property
    def pcm_duration_seconds(self) -> float:
        return self.bytes_received / INPUT_BYTES_PER_SECOND

    @property
    def receive_wall_seconds(self) -> float:
        if self.first_pcm_received_at is None or self.end_received_at is None:
            return 0.0
        return self.end_received_at - self.first_pcm_received_at


class Pcm24kTo16k:
    """Conversor stateful PCM16 mono, 24 kHz -> 16 kHz."""

    def __init__(self) -> None:
        self.carry = b""

    def convert(self, pcm24: bytes) -> bytes:
        data = self.carry + pcm24
        usable = (len(data) // 6) * 6

        if usable == 0:
            self.carry = data
            return b""

        output = bytearray()

        for offset in range(0, usable, 6):
            a, b, c = struct.unpack_from("<hhh", data, offset)
            out1 = a
            out2 = int((int(b) + int(c)) / 2)
            output.extend(struct.pack("<hh", out1, out2))

        self.carry = data[usable:]
        return bytes(output)


class LiveVoiceWebSocketServer:
    """
    WebSocket persistente BOX <-> PC com sessão Gemini conversacional.

    Fase atual, compatível com o firmware existente:

        servidor -> READY

        BOX -> WAKE
        BOX -> START
        BOX -> PCM...
        BOX -> END
        servidor -> PCM resposta...
        servidor -> DONE

        BOX -> WAKE              # firmware atual ainda exige "Jarvis"
        BOX -> START
        ...

    A diferença é que o Gemini Live NÃO é fechado entre estes turnos.
    Assim, a segunda pergunta mantém o contexto da primeira.

    A sessão Gemini fecha após CONVERSATION_IDLE_TIMEOUT_SECONDS sem novo
    turno. O WebSocket BOX <-> PC continua aberto.

    A implementação já aceita START diretamente após DONE. Isso será usado
    na fase seguinte, quando o firmware puder ouvir uma continuação sem
    exigir novamente a palavra Jarvis.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        self.host = host
        self.port = port

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._started = threading.Event()
        self._startup_error: Optional[BaseException] = None
        self._connection_lock: Optional[asyncio.Lock] = None

    def start(self, timeout: float = 10.0) -> None:
        if self._thread is not None and self._thread.is_alive():
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
            raise RuntimeError("Timeout ao iniciar o servidor WebSocket de voz")

        if self._startup_error is not None:
            raise RuntimeError("Falha ao iniciar servidor WebSocket de voz") from self._startup_error

    def stop(self, timeout: float = 5.0) -> None:
        loop = self._loop
        stop_event = self._stop_event

        if loop is not None and stop_event is not None:
            loop.call_soon_threadsafe(stop_event.set)

        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

        self._thread = None
        self._loop = None
        self._stop_event = None

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run_server())
        except BaseException as exc:
            self._startup_error = exc
            self._started.set()
            print(f"[VOICE-WS] ERRO fatal: {self._format_exception(exc)}")

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
                max_queue=1024,
                write_limit=64 * 1024,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            ):
                print()
                print("[VOICE-WS] =========================================")
                print(
                    f"[VOICE-WS] Conversacional em "
                    f"ws://{self.host}:{self.port}{VOICE_WS_PATH}"
                )
                print(
                    f"[VOICE-WS] Contexto Gemini: até "
                    f"{CONVERSATION_IDLE_TIMEOUT_SECONDS} s sem novo turno"
                )
                print("[VOICE-WS] =========================================")
                print()

                self._started.set()
                await self._stop_event.wait()
        except BaseException:
            self._started.set()
            raise

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        path = getattr(getattr(websocket, "request", None), "path", "")

        if path != VOICE_WS_PATH:
            await websocket.close(code=1008, reason="Caminho WebSocket inválido")
            return

        assert self._connection_lock is not None

        if self._connection_lock.locked():
            await websocket.close(code=1013, reason="Já existe uma BOX ligada")
            return

        async with self._connection_lock:
            peer = websocket.remote_address
            print(f"[VOICE-WS] BOX persistente ligada: {peer}")

            try:
                await websocket.send("READY")
                print("[VOICE-WS] READY enviado; à espera de Jarvis")

                while True:
                    message = await websocket.recv()

                    if message == "WAKE":
                        print()
                        print("[VOICE-WS] >>> NOVA CONVERSA: WAKE recebido <<<")

                        try:
                            await self._run_conversation(
                                websocket,
                                first_turn_started_by="WAKE",
                            )
                        except ConnectionClosed:
                            raise
                        except Exception as exc:
                            print(
                                f"[VOICE-WS] ERRO na conversa: "
                                f"{self._format_exception(exc)}"
                            )
                            await self._send_error_control(websocket, exc)

                        print("[VOICE-WS] À espera de Jarvis para nova conversa")
                        continue

                    if message in {"CANCEL", "SESSION_END"}:
                        await websocket.send("DONE")
                        continue

                    if isinstance(message, bytes):
                        continue

                    if message in {"START", "END"}:
                        # Resíduo de um turno falhado; não fecha o WebSocket.
                        continue

                    print(f"[VOICE-WS] Mensagem inesperada em idle: {message!r}")

            except ConnectionClosed as exc:
                print(
                    f"[VOICE-WS] Ligação fechada: "
                    f"code={exc.code} reason={exc.reason}"
                )
            except Exception as exc:
                print(
                    f"[VOICE-WS] ERRO da ligação: "
                    f"{self._format_exception(exc)}"
                )
            finally:
                print(f"[VOICE-WS] BOX desligada: {peer}")

    async def _run_conversation(
        self,
        websocket: ServerConnection,
        first_turn_started_by: str,
    ) -> None:
        config = {
            "response_modalities": ["AUDIO"],
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
                            "És Jarvis, um assistente pessoal de inteligência artificial. "
                            "Fala em português de Portugal, salvo se o utilizador pedir "
                            "outra língua. Mantém o contexto da conversa entre perguntas. "
                            "Quando uma pergunta depende do que foi dito antes, usa esse "
                            "contexto naturalmente. Responde de forma natural, útil e "
                            "relativamente concisa."
                        )
                    }
                ]
            },
        }

        client = genai.Client(api_key=API_KEY)
        open_start = time.perf_counter()

        # Começamos a drenar START/PCM imediatamente, enquanto o Gemini abre.
        first_queue, first_stats, first_receiver = self._start_turn_receiver(
            websocket,
            start_already_received=(first_turn_started_by == "START"),
        )

        try:
            async with client.aio as async_client:
                print(f"[VOICE-WS] A abrir conversa Gemini {MODEL}...")

                async with async_client.live.connect(
                    model=MODEL,
                    config=config,
                ) as session:
                    print(
                        f"[VOICE-WS] Conversa Gemini pronta em "
                        f"{time.perf_counter() - open_start:.2f} s"
                    )

                    result = await self._complete_turn(
                        websocket,
                        session,
                        first_queue,
                        first_stats,
                        first_receiver,
                        turn_number=1,
                    )

                    if result != "done":
                        return

                    turn_number = 1

                    while True:
                        print(
                            f"[VOICE-WS] Contexto mantido; à espera do próximo turno "
                            f"({CONVERSATION_IDLE_TIMEOUT_SECONDS} s)"
                        )

                        try:
                            message = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=CONVERSATION_IDLE_TIMEOUT_SECONDS,
                            )
                        except asyncio.TimeoutError:
                            print(
                                "[VOICE-WS] Conversa encerrada por inatividade; "
                                "o próximo Jarvis abrirá novo contexto"
                            )
                            return

                        if message == "SESSION_END":
                            print("[VOICE-WS] SESSION_END recebido; conversa encerrada")
                            return

                        if message == "CANCEL":
                            await websocket.send("DONE")
                            continue

                        if message == "WAKE":
                            # Compatibilidade com o firmware atual: ainda se diz Jarvis,
                            # mas a sessão Gemini permanece a mesma.
                            start_already_received = False
                            print("[VOICE-WS] WAKE recebido dentro da mesma conversa")
                        elif message == "START":
                            # Preparado para a fase 2: follow-up sem repetir Jarvis.
                            start_already_received = True
                            print("[VOICE-WS] Follow-up direto START; mesmo contexto")
                        elif isinstance(message, bytes):
                            # Não aceitamos PCM sem START explícito.
                            continue
                        else:
                            print(
                                f"[VOICE-WS] Controlo inesperado durante conversa: "
                                f"{message!r}"
                            )
                            continue

                        queue, stats, receiver = self._start_turn_receiver(
                            websocket,
                            start_already_received=start_already_received,
                        )

                        turn_number += 1

                        result = await self._complete_turn(
                            websocket,
                            session,
                            queue,
                            stats,
                            receiver,
                            turn_number=turn_number,
                        )

                        if result != "done":
                            return
        finally:
            client.close()

    def _start_turn_receiver(
        self,
        websocket: ServerConnection,
        start_already_received: bool,
    ):
        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)
        stats = TurnStats(started_at=time.perf_counter())
        receiver = asyncio.create_task(
            self._receive_turn_input(
                websocket,
                queue,
                stats,
                start_already_received=start_already_received,
            ),
            name="box-audio-receiver",
        )
        return queue, stats, receiver

    async def _complete_turn(
        self,
        websocket: ServerConnection,
        session,
        input_queue: asyncio.Queue,
        stats: TurnStats,
        receiver_task: asyncio.Task,
        turn_number: int,
    ) -> str:
        gemini_task = asyncio.create_task(
            self._gemini_turn_existing_session(
                websocket,
                session,
                input_queue,
                stats,
                turn_number,
            ),
            name=f"gemini-turn-{turn_number}",
        )

        try:
            receiver_result = await receiver_task

            if receiver_result == "cancelled":
                if not gemini_task.done():
                    gemini_task.cancel()
                await asyncio.gather(gemini_task, return_exceptions=True)
                await websocket.send("DONE")
                return "cancelled"

            if receiver_result != "ended":
                raise RuntimeError(
                    f"Estado de receção inesperado: {receiver_result!r}"
                )

            gemini_result = await gemini_task

            if gemini_result != "done":
                raise RuntimeError(
                    f"Estado Gemini inesperado: {gemini_result!r}"
                )

            await websocket.send("DONE")
            print(f"[VOICE-WS] Turno {turn_number} concluído | contexto preservado")
            return "done"
        finally:
            for task in (receiver_task, gemini_task):
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
        start_already_received: bool,
    ) -> str:
        if not start_already_received:
            first_message = await asyncio.wait_for(
                websocket.recv(),
                timeout=TURN_START_TIMEOUT_SECONDS,
            )

            if first_message == "CANCEL":
                await input_queue.put(_QUEUE_CANCEL)
                return "cancelled"

            if first_message != "START":
                raise RuntimeError(
                    f"Esperado START; recebido {first_message!r}"
                )

        await input_queue.put(_QUEUE_START)
        print("[VOICE-WS] START recebido; áudio BOX já pode entrar")

        while True:
            message = await asyncio.wait_for(
                websocket.recv(),
                timeout=TURN_INPUT_TIMEOUT_SECONDS,
            )

            if isinstance(message, bytes):
                if not message:
                    continue

                if len(message) % 2 != 0:
                    raise RuntimeError("Frame PCM16 com número ímpar de bytes")

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

            if message == "SESSION_END":
                await input_queue.put(_QUEUE_CANCEL)
                return "cancelled"

            raise RuntimeError(
                f"Mensagem de controlo desconhecida durante turno: {message!r}"
            )

    async def _gemini_turn_existing_session(
        self,
        websocket: ServerConnection,
        session,
        input_queue: asyncio.Queue,
        stats: TurnStats,
        turn_number: int,
    ) -> str:
        first_item = await input_queue.get()

        if first_item is _QUEUE_CANCEL:
            return "cancelled"

        if first_item is not _QUEUE_START:
            raise RuntimeError("Fila Live não começou com START")

        await session.send_realtime_input(
            activity_start=types.ActivityStart()
        )

        print(f"[VOICE-WS] Turno {turn_number}: START entregue ao Gemini")

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
                raise RuntimeError(f"Item inesperado na fila: {item!r}")

            target_send_at = pacing_started_at + audio_seconds_forwarded
            delay = target_send_at - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)

            await session.send_realtime_input(
                audio=types.Blob(
                    data=item,
                    mime_type="audio/pcm;rate=16000",
                )
            )

            bytes_forwarded += len(item)
            audio_seconds_forwarded += len(item) / INPUT_BYTES_PER_SECOND

        await session.send_realtime_input(
            activity_end=types.ActivityEnd()
        )

        print(
            f"[VOICE-WS] Turno {turn_number}: END entregue ao Gemini | "
            f"{bytes_forwarded} bytes | "
            f"{stats.pcm_duration_seconds:.2f} s PCM | "
            f"{stats.receive_wall_seconds:.2f} s BOX->PC"
        )

        converter = Pcm24kTo16k()
        first_audio = True
        response_start = time.perf_counter()
        total_output = 0

        async with asyncio.timeout(TURN_RESPONSE_TIMEOUT_SECONDS):
            async for response in session.receive():
                content = response.server_content

                if content is None:
                    continue

                if content.input_transcription:
                    value = content.input_transcription.text
                    if value:
                        print(f"[VOICE-WS] Tu: {value}")

                if content.output_transcription:
                    value = content.output_transcription.text
                    if value:
                        print(f"[VOICE-WS] Jarvis: {value}")

                if content.model_turn is None:
                    continue

                for part in content.model_turn.parts:
                    if part.inline_data is None or part.inline_data.data is None:
                        continue

                    pcm16 = converter.convert(part.inline_data.data)
                    if not pcm16:
                        continue

                    if first_audio:
                        print(
                            f"[PERF] Turno {turn_number}: primeiro áudio Gemini "
                            f"em {time.perf_counter() - response_start:.2f} s"
                        )
                        first_audio = False

                    total_output += len(pcm16)

                    for offset in range(0, len(pcm16), OUTPUT_WS_CHUNK_BYTES):
                        await websocket.send(
                            pcm16[offset:offset + OUTPUT_WS_CHUNK_BYTES]
                        )

        if first_audio:
            raise RuntimeError("Gemini Live terminou sem devolver áudio")

        print(
            f"[VOICE-WS] Turno {turn_number}: resposta concluída | "
            f"{total_output} bytes PCM16 / 16 kHz"
        )
        return "done"

    async def _send_error_control(
        self,
        websocket: ServerConnection,
        exc: BaseException,
    ) -> None:
        message = f"ERROR:{type(exc).__name__}"
        encoded = message.encode("utf-8")

        if len(encoded) > FIRMWARE_CONTROL_MAX_BYTES:
            message = "ERROR:ServerError"

        try:
            await websocket.send(message)
        except ConnectionClosed:
            pass

    @staticmethod
    def _format_exception(exc: BaseException) -> str:
        text = str(exc).strip()
        if text:
            return f"{type(exc).__name__}: {text}"
        return f"{type(exc).__name__}: {exc!r}"
