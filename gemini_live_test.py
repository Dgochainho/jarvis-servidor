import asyncio
import os
import time
import wave

from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY não encontrada no .env"
    )


client = genai.Client(
    api_key=api_key
)


MODEL = "gemini-3.1-flash-live-preview"

INPUT_WAV = "command.wav"
OUTPUT_WAV = "gemini_live_reply.wav"

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000

# 100 ms:
# 16000 amostras/s * 2 bytes * 0.1 s
CHUNK_BYTES = 3200


def load_input_audio():
    with wave.open(INPUT_WAV, "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()

        if channels != 1:
            raise RuntimeError(
                f"command.wav tem {channels} canais; esperado 1"
            )

        if width != 2:
            raise RuntimeError(
                f"command.wav tem {width * 8} bits; esperado 16"
            )

        if rate != INPUT_SAMPLE_RATE:
            raise RuntimeError(
                f"command.wav tem {rate} Hz; esperado 16000"
            )

        pcm = wav.readframes(
            wav.getnframes()
        )

    duration = len(pcm) / 32000.0

    print(
        f"[LIVE] Audio carregado: "
        f"{len(pcm)} bytes | {duration:.2f} s"
    )

    return pcm


async def main():
    pcm = load_input_audio()

    config = {
        "response_modalities": ["AUDIO"],

        "input_audio_transcription": {},
        "output_audio_transcription": {},

        "system_instruction": {
            "parts": [
                {
                    "text": (
                        "És Jarvis, um assistente pessoal de inteligência "
                        "artificial. Fala sempre em português de Portugal, "
                        "a menos que o utilizador peça outra língua. "
                        "Responde de forma natural, útil e relativamente "
                        "concisa. Estás a conversar por voz com o utilizador."
                    )
                }
            ]
        },
    }

    print(
        f"[LIVE] A ligar a {MODEL}..."
    )

    async with client.aio.live.connect(
        model=MODEL,
        config=config,
    ) as session:

        print("[LIVE] Sessão ligada")
        print("[LIVE] A enviar áudio...")

        send_start = time.perf_counter()

        for offset in range(
            0,
            len(pcm),
            CHUNK_BYTES,
        ):
            chunk = pcm[
                offset:offset + CHUNK_BYTES
            ]

            await session.send_realtime_input(
                audio=types.Blob(
                    data=chunk,
                    mime_type="audio/pcm;rate=16000",
                )
            )

            # Enviamos aproximadamente em tempo real.
            await asyncio.sleep(
                len(chunk) / 32000.0
            )

        await session.send_realtime_input(
            audio_stream_end=True
        )

        print("[LIVE] Fim do áudio enviado")
        print("[LIVE] À espera da resposta...")

        response_start = time.perf_counter()

        output_pcm = bytearray()
        first_audio_time = None

        async for response in session.receive():

            content = response.server_content

            if content is None:
                continue

            if content.input_transcription:
                text = content.input_transcription.text

                if text:
                    print(
                        f"[LIVE] Tu: {text}"
                    )

            if content.output_transcription:
                text = content.output_transcription.text

                if text:
                    print(
                        f"[LIVE] Jarvis: {text}"
                    )

            if content.model_turn:
                for part in content.model_turn.parts:

                    if (
                        part.inline_data is not None
                        and
                        part.inline_data.data is not None
                    ):
                        if first_audio_time is None:
                            first_audio_time = (
                                time.perf_counter()
                            )

                            latency = (
                                first_audio_time
                                - response_start
                            )

                            print(
                                f"[PERF] Primeiro áudio Gemini: "
                                f"{latency:.2f} s"
                            )

                        output_pcm.extend(
                            part.inline_data.data
                        )

        total = (
            time.perf_counter()
            - send_start
        )

    if not output_pcm:
        raise RuntimeError(
            "Gemini Live não devolveu áudio"
        )

    with wave.open(
        OUTPUT_WAV,
        "wb"
    ) as wav:

        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(
            OUTPUT_SAMPLE_RATE
        )

        wav.writeframes(
            output_pcm
        )

    duration = (
        len(output_pcm)
        /
        (OUTPUT_SAMPLE_RATE * 2)
    )

    print()
    print("[LIVE] =============================")
    print(
        f"[LIVE] Resposta: {len(output_pcm)} bytes"
    )
    print(
        f"[LIVE] Duração resposta: {duration:.2f} s"
    )
    print(
        f"[LIVE] Ficheiro: {OUTPUT_WAV}"
    )
    print(
        f"[PERF] Processo completo: {total:.2f} s"
    )
    print("[LIVE] =============================")


if __name__ == "__main__":
    asyncio.run(main())