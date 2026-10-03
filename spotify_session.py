"""
A sessão Spotify do processo. Uma, e só uma.

Porque é que isto é um módulo próprio e não fica no app.py:

O `action_service` precisa do cliente para falar com o Spotify directamente,
e o `app.py` também. Mas o `app.py` importa o servidor WebSocket, que importa
o `jarvis_live`, que importa o `action_service` — se o `action_service`
importasse do `app.py`, fechava o ciclo.

E não serve criar um cliente em cada sítio. O `SpotifyClient` guarda estado
que **tem** de ser partilhado:

  - a cache de `get_status`, com a invalidação feita em `send_command`.
    Dois clientes significariam que um "passa esta" dado pela voz não
    invalidava a cache que o LCD lê, e o LCD mostrava a faixa anterior.
  - o access token e o seu ciclo de renovação. Dois clientes renovariam em
    separado, duplicando os pedidos ao Spotify sem razão.

Portanto: uma instância, aqui, e toda a gente importa esta.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from spotify_client import SpotifyClient


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent

TOKEN_FILE = BASE_DIR / ".spotify_token.json"


# Os scopes de que o serviço precisa.
#
# Cobrem tudo o que a Fase 2 vai acrescentar — a pesquisa não exige scope de
# utilizador, e o `user-modify-playback-state` já cobre play, volume, next,
# previous e pause. Não é preciso reautenticar.
SCOPES = [
    "user-read-currently-playing",
    "user-read-playback-state",
    "user-modify-playback-state",
]


spotify = SpotifyClient(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    token_file=TOKEN_FILE,
)
