import os
from typing import Literal, Optional

from click import prompt
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field


load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY não encontrada no ficheiro .env"
    )


client = genai.Client(api_key=api_key)


class SpotifyIntent(BaseModel):
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
            "Nome da música, artista, álbum ou playlist "
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


def understand_command(text: str) -> SpotifyIntent:
    prompt = f"""
És o interpretador de comandos de voz de um assistente Spotify
chamado Jarvis.

O utilizador fala principalmente português de Portugal.

Transforma o pedido numa única intenção Spotify.

Ações disponíveis:

pause
- parar temporariamente a reprodução

resume
- continuar ou retomar a reprodução

next
- passar para a próxima música

previous
- voltar à música anterior

current_track
- perguntar qual música, artista ou conteúdo está atualmente a tocar

play_search
- reproduzir uma música, artista, álbum ou playlist específica
- coloca aquilo que deve ser pesquisado em query

set_volume
- alterar o volume
- coloca o valor entre 0 e 100 em volume_percent

unknown
- pedido que não corresponde a nenhuma destas operações Spotify

Interpreta linguagem natural.
Exemplos:

"passa esta" -> next
"próxima" -> next
"volta atrás" -> previous
"faz pausa" -> pause
"continua" -> resume
"o que está a tocar?" -> current_track
"qual é esta música?" -> current_track
"põe Arctic Monkeys" -> play_search, query="Arctic Monkeys"
"toca Do I Wanna Know" -> play_search, query="Do I Wanna Know"
"mete o volume a quarenta" -> set_volume, volume_percent=40

Informação sobre o utilizador:
Nome: Dinis
Artista favorito: Tame Impala


Não inventes nomes, músicas ou valores.

Pedido do utilizador:

{text}
"""

    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input= prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": SpotifyIntent.model_json_schema(),
        },
    )

    return SpotifyIntent.model_validate_json(
        interaction.output_text
    )