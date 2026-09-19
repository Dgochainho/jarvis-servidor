import os

from dotenv import load_dotenv
from google import genai


load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY não encontrada no ficheiro .env"
    )


client = genai.Client(api_key=api_key)


def transcribe_audio(wav_path):
    audio_file = client.files.upload(
        file=str(wav_path)
    )

    interaction = client.interactions.create(
        model="gemini-3.5-transcribe",
        input=[
            {
                "type": "audio",
                "uri": audio_file.uri,
                "mime_type": audio_file.mime_type,
            }
        ],
        generation_config={
            "transcription_config": {
                "language_codes": ["pt-PT"],
                "mode": {
                    "type": "verbatim"
                },
            }
        },
    )

    return interaction.output_text.strip()