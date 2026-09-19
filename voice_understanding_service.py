import base64
import os
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field


load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY não encontrada no ficheiro .env"
    )


client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(
        timeout=6000,
        retry_options=types.HttpRetryOptions(
            attempts=1
        ),
    ),
)


class VoiceCommand(BaseModel):
    transcript: str = Field(
        description=(
            "Transcrição curta e fiel do comando falado "
            "pelo utilizador, em português quando aplicável."
        )
    )

    action: Literal[
        "pause",
        "resume",
        "next",
        "previous",
        "current_track",
        "play_search",
        "set_volume",
        "unknown",
    ]

    query: Optional[str] = Field(
        default=None,
        description=(
            "Música, artista, álbum ou playlist a pesquisar "
            "quando action=play_search."
        ),
    )

    volume_percent: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Volume entre 0 e 100 quando action=set_volume."
        ),
    )


def understand_audio(wav_path) -> VoiceCommand:
    with open(wav_path, "rb") as audio_file:
        audio_bytes = audio_file.read()

    audio_base64 = base64.b64encode(
        audio_bytes
    ).decode("utf-8")

    prompt = """
O áudio contém um comando dirigido a um assistente Spotify
chamado Jarvis.

O utilizador fala principalmente português de Portugal.

Faz duas coisas:

1. Transcreve fielmente aquilo que o utilizador disse.
2. Converte o pedido numa única ação Spotify.

Ações possíveis:

pause
- pausar a reprodução

resume
- continuar ou retomar a reprodução

next
- passar para a próxima música

previous
- voltar à música anterior

current_track
- perguntar qual música ou artista está atualmente a tocar

play_search
- reproduzir uma música, artista, álbum ou playlist
- coloca o termo de pesquisa em query

set_volume
- alterar o volume
- coloca um valor de 0 a 100 em volume_percent

unknown
- qualquer pedido que não corresponda às ações acima

Exemplos:

"passa esta"
→ action=next

"faz pausa"
→ action=pause

"continua"
→ action=resume

"qual é a música a tocar?"
→ action=current_track

"põe Arctic Monkeys"
→ action=play_search
→ query="Arctic Monkeys"

"mete o volume a quarenta"
→ action=set_volume
→ volume_percent=40

Não inventes nomes, valores ou comandos.
"""

    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input=[
            {
                "type": "text",
                "text": prompt,
            },
            {
                "type": "audio",
                "data": audio_base64,
                "mime_type": "audio/wav",
            },
        ],
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": VoiceCommand.model_json_schema(),
        },
    )

    return VoiceCommand.model_validate_json(
        interaction.output_text
    )