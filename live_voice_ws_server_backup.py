import asyncio
import os
import struct
import threading
import time
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed


load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY não encontrada no .env"
    )


MODEL = "gemini-3.1-flash-live-preview"

VOICE_WS_PATH = "/voice"
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
SESSION_INPUT_TIMEOUT_SECONDS = 20
SESSION_RESPONSE_TIMEOUT_SECONDS = 90


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
    Servidor WebSocket local para a BOX.

    Protocolo:
      servidor -> "READY"
      BOX      -> "START"
      BOX      -> frames binários PCM16 / 16 kHz / mono
      BOX      -> "END"
      servidor -> frames binários PCM16 / 16 kHz / mono
      servidor -> "DONE"

    Cada ligação corresponde, por enquanto, a uma única interação
    half-duplex. A chave Gemini permanece apenas no servidor.
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
        self._session_lock: Optional[asyncio.Lock] = None

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
            raise RuntimeError(
                "Timeout ao iniciar o servidor WebSocket de voz"
            )

        if self._startup_error is not None:
            raise RuntimeError(
                "Falha ao iniciar servidor WebSocket de voz"
            ) from self._startup_error

    def stop(self, timeout: float = 5.0) -> None:
        loop = self._loop
        stop_event = self._stop_event

        if loop is not None and stop_event is not None:
            loop.call_soon_threadsafe(stop_event.set)

        if self._thread is not None:
            self._thread.join(timeout=timeout)

        self._thread = None
        self._loop = None
        self._stop_event = None

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run_server())
        except BaseException as exc:
            self._startup_error = exc
            self._started.set()
            print(f"[VOICE-WS] ERRO fatal: {exc}")

    async def _run_server(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._session_lock = asyncio.Lock()

        try:
            async with serve(
                self._handle_connection,
                self.host,
                self.port,
                compression=None,
                max_size=64 * 1024,
                max_queue=64,
                write_limit=64 * 1024,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            ):
                print()
                print("[VOICE-WS] ==============================")
                print(
                    f"[VOICE-WS] Ativo em ws://{self.host}:{self.port}{VOICE_WS_PATH}"
                )
                print("[VOICE-WS] ==============================")
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

        assert self._session_lock is not None

        async with self._session_lock:
            peer = websocket.remote_address
            print(f"[VOICE-WS] BOX ligada: {peer}")

            try:
                await self._run_interaction(websocket)
            except ConnectionClosed as exc:
                print(
                    f"[VOICE-WS] Ligação fechada: "
                    f"code={exc.code} reason={exc.reason}"
                )
            except Exception as exc:
                print(f"[VOICE-WS] ERRO: {exc}")

                try:
                    await websocket.send(
                        f"ERROR:{type(exc).__name__}:{exc}"
                    )
                except Exception:
                    pass
            finally:
                print(f"[VOICE-WS] BOX desligada: {peer}")

    async def _run_interaction(
        self,
        websocket: ServerConnection,
    ) -> None:
        client = genai.Client(api_key=API_KEY)

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
                            "És Jarvis, um assistente pessoal de "
                            "inteligência artificial. Fala em português "
                            "de Portugal, salvo se o utilizador pedir "
                            "outra língua. Responde de forma natural, "
                            "útil e relativamente concisa."
                        )
                    }
                ]
            },
        }

        print(f"[VOICE-WS] A abrir sessão {MODEL}...")

        async with client.aio.live.connect(
            model=MODEL,
            config=config,
        ) as session:
            await websocket.send("READY")
            print("[VOICE-WS] Gemini pronto; READY enviado")

            first_message = await asyncio.wait_for(
                websocket.recv(),
                timeout=10,
            )

            if first_message != "START":
                raise RuntimeError(
                    f"Esperado START; recebido {first_message!r}"
                )

            await session.send_realtime_input(
                activity_start=types.ActivityStart()
            )

            print("[VOICE-WS] START recebido; áudio em streaming")

            bytes_received = 0
            input_started = time.perf_counter()

            while True:
                message = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=SESSION_INPUT_TIMEOUT_SECONDS,
                )

                if isinstance(message, bytes):
                    if not message:
                        continue

                    if len(message) % 2 != 0:
                        raise RuntimeError(
                            "Frame PCM16 com número ímpar de bytes"
                        )

                    bytes_received += len(message)

                    await session.send_realtime_input(
                        audio=types.Blob(
                            data=message,
                            mime_type="audio/pcm;rate=16000",
                        )
                    )
                    continue

                if message == "END":
                    break

                if message == "CANCEL":
                    print("[VOICE-WS] Interação cancelada pela BOX")
                    await websocket.send("DONE")
                    return

                raise RuntimeError(
                    f"Mensagem de controlo desconhecida: {message!r}"
                )

            await session.send_realtime_input(
                activity_end=types.ActivityEnd()
            )

            input_duration = bytes_received / 32000.0
            wall_duration = time.perf_counter() - input_started

            print(
                f"[VOICE-WS] END recebido | "
                f"{bytes_received} bytes | "
                f"{input_duration:.2f} s PCM | "
                f"{wall_duration:.2f} s reais"
            )

            converter = Pcm24kTo16k()
            first_audio = True
            response_start = time.perf_counter()
            total_output = 0

            async with asyncio.timeout(
                SESSION_RESPONSE_TIMEOUT_SECONDS
            ):
                async for response in session.receive():
                    content = response.server_content

                    if content is None:
                        continue

                    if content.input_transcription:
                        text = content.input_transcription.text
                        if text:
                            print(f"[VOICE-WS] Tu: {text}")

                    if content.output_transcription:
                        text = content.output_transcription.text
                        if text:
                            print(f"[VOICE-WS] Jarvis: {text}")

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
                                f"[PERF] Primeiro áudio Gemini Live WS: "
                                f"{latency:.2f} s"
                            )
                            first_audio = False

                        total_output += len(pcm16)
                        await websocket.send(pcm16)

            if first_audio:
                raise RuntimeError(
                    "Gemini Live terminou sem devolver áudio"
                )

            await websocket.send("DONE")

            print(
                f"[VOICE-WS] Resposta concluída | "
                f"{total_output} bytes PCM16 / 16 kHz"
            )
