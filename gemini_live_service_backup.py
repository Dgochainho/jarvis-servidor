import asyncio
import os
import queue
import struct
import threading

from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY não encontrada no .env"
    )


MODEL = "gemini-3.1-flash-live-preview"

# 100 ms de PCM16 mono a 16 kHz
INPUT_CHUNK_BYTES = 3200

_END = object()


class Pcm24kTo16k:
    """
    Conversor simples e stateful:
    PCM16 mono 24 kHz -> PCM16 mono 16 kHz.

    A razão é exatamente 3:2:
    3 amostras de entrada -> 2 amostras de saída.
    """

    def __init__(self):
        self.carry = b""

    def convert(self, pcm24):
        data = self.carry + pcm24

        # 3 amostras PCM16 = 6 bytes
        usable = (len(data) // 6) * 6

        if usable == 0:
            self.carry = data
            return b""

        output = bytearray()

        for offset in range(0, usable, 6):
            a, b, c = struct.unpack_from(
                "<hhh",
                data,
                offset
            )

            # Primeira amostra de saída
            out1 = a

            # Segunda fica a meio entre b e c
            out2 = int(
                (int(b) + int(c)) / 2
            )

            output.extend(
                struct.pack(
                    "<hh",
                    out1,
                    out2
                )
            )

        self.carry = data[usable:]

        return bytes(output)


async def _live_worker(pcm16, output_queue):
    try:
        client = genai.Client(
            api_key=API_KEY
        )

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
                            "inteligência artificial. "
                            "Fala em português de Portugal, salvo se "
                            "o utilizador pedir outra língua. "
                            "Responde de forma natural e útil. "
                            "Como estás num assistente de voz, prefere "
                            "respostas relativamente concisas, exceto "
                            "quando o utilizador pedir mais detalhe."
                        )
                    }
                ]
            },
        }

        print(
            f"[LIVE] A abrir sessão {MODEL}..."
        )

        async with client.aio.live.connect(
            model=MODEL,
            config=config,
        ) as session:

            print("[LIVE] Sessão ligada")

            await session.send_realtime_input(
                activity_end=types.ActivityEnd()
            )

            # Envia o áudio já recebido da BOX.
            for offset in range(
                0,
                len(pcm16),
                INPUT_CHUNK_BYTES,
            ):
                chunk = pcm16[
                    offset:
                    offset + INPUT_CHUNK_BYTES
                ]

                await session.send_realtime_input(
                    audio=types.Blob(
                        data=chunk,
                        mime_type="audio/pcm;rate=16000",
                    )
                )

                # Apenas permite ao event loop respirar.
                # Não esperamos 100 ms porque este áudio
                # já foi gravado pela BOX.
                await asyncio.sleep(
                    len(chunk) / 32000.0
                )

            await session.send_realtime_input(
                audio_stream_end=True
            )

            print(
                "[LIVE] Áudio enviado; "
                "a receber resposta..."
            )

            converter = Pcm24kTo16k()
            first_audio = True
            total_16k = 0

            async for response in session.receive():
                content = response.server_content

                if content is None:
                    continue

                if content.input_transcription:
                    text = (
                        content
                        .input_transcription
                        .text
                    )

                    if text:
                        print(
                            f"[LIVE] Tu: {text}"
                        )

                if content.output_transcription:
                    text = (
                        content
                        .output_transcription
                        .text
                    )

                    if text:
                        print(
                            f"[LIVE] Jarvis: {text}"
                        )

                if content.model_turn is None:
                    continue

                for part in content.model_turn.parts:
                    if (
                        part.inline_data is None
                        or
                        part.inline_data.data is None
                    ):
                        continue

                    pcm24 = part.inline_data.data

                    pcm16_out = converter.convert(
                        pcm24
                    )

                    if not pcm16_out:
                        continue

                    if first_audio:
                        print(
                            "[LIVE] >>> primeiro chunk "
                            "de voz recebido <<<"
                        )

                        first_audio = False

                    total_16k += len(
                        pcm16_out
                    )

                    # Este chunk fica imediatamente
                    # disponível para o HTTP/BOX.
                    output_queue.put(
                        pcm16_out
                    )

            print(
                f"[LIVE] Resposta terminada | "
                f"{total_16k} bytes a 16 kHz"
            )

    except Exception as exc:
        print(
            f"[LIVE] ERRO: {exc}"
        )

        output_queue.put(exc)

    finally:
        output_queue.put(_END)


def stream_gemini_live_reply(pcm16):
    output_queue = queue.Queue(
        maxsize=32
    )

    def runner():
        asyncio.run(
            _live_worker(
                pcm16,
                output_queue
            )
        )

    thread = threading.Thread(
        target=runner,
        daemon=True,
        name="gemini-live",
    )

    thread.start()

    while True:
        item = output_queue.get()

        if item is _END:
            break

        if isinstance(
            item,
            BaseException
        ):
            raise item

        yield item