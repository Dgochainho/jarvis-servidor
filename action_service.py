import requests


BASE_URL = "http://127.0.0.1:8888"


def execute_intent(intent):
    action = intent.action

    try:
        # -----------------------------------------
        # PAUSE
        # -----------------------------------------
        if action == "pause":
            response = requests.post(
                f"{BASE_URL}/api/pause",
                timeout=10,
            )

            response.raise_for_status()

            return {
                "ok": True,
                "action": action,
                "message": "Reprodução pausada.",
            }

        # -----------------------------------------
        # RESUME / PLAY
        # -----------------------------------------
        if action == "resume":
            response = requests.post(
                f"{BASE_URL}/api/play",
                timeout=10,
            )

            response.raise_for_status()

            return {
                "ok": True,
                "action": action,
                "message": "Reprodução retomada.",
            }

        # -----------------------------------------
        # NEXT
        # -----------------------------------------
        if action == "next":
            response = requests.post(
                f"{BASE_URL}/api/next",
                timeout=10,
            )

            response.raise_for_status()

            return {
                "ok": True,
                "action": action,
                "message": "Passei para a próxima música.",
            }

        # -----------------------------------------
        # PREVIOUS
        # -----------------------------------------
        if action == "previous":
            response = requests.post(
                f"{BASE_URL}/api/previous",
                timeout=10,
            )

            response.raise_for_status()

            return {
                "ok": True,
                "action": action,
                "message": "Voltei à música anterior.",
            }

        # -----------------------------------------
        # CURRENT TRACK
        # -----------------------------------------
        if action == "current_track":
            # Esta chamada acontece dentro de um turno de voz, com o
            # utilizador à espera. Uma ida fresca à API do Spotify custa
            # entre 1 e 5 s; para dizer que música está a tocar, uma
            # resposta com alguns segundos é indistinguível da actual.
            #
            # 15 s e não 8 porque o polling da BOX fica suspenso durante a
            # voz: quando este pedido chega, o último polling já tem a
            # duração do turno. Com 8 s acertávamos em cerca de metade das
            # vezes; com 15 acertamos quase sempre.
            #
            # Seguro porque send_command invalida a cache — depois de um
            # "passa esta" a resposta seguinte é sempre fresca.
            response = requests.get(
                f"{BASE_URL}/api/status",
                params={"max_age": 15},
                timeout=10,
            )

            response.raise_for_status()

            status = response.json()

            if not status.get("active"):
                return {
                    "ok": True,
                    "action": action,
                    "message": "Não há nenhuma música a tocar.",
                }

            track = status.get("track", "")
            artist = status.get("artist", "")

            return {
                "ok": True,
                "action": action,
                "track": track,
                "artist": artist,
                "message": f"Está a tocar {track}, de {artist}.",
            }

        # -----------------------------------------
        # AINDA NÃO IMPLEMENTADOS
        # -----------------------------------------
        if action == "play_search":
            return {
                "ok": False,
                "action": action,
                "message": (
                    "Pesquisa e reprodução ainda não implementadas."
                ),
            }

        if action == "set_volume":
            return {
                "ok": False,
                "action": action,
                "message": (
                    "Controlo de volume ainda não implementado."
                ),
            }

        return {
            "ok": False,
            "action": action,
            "message": "Comando não reconhecido.",
        }

    except requests.RequestException as exc:
        return {
            "ok": False,
            "action": action,
            "message": f"Erro ao executar comando Spotify: {exc}",
        }

class _SpotifyIntent:
    def __init__(self, action):
        self.action = action


def execute_spotify_action(action):
    """
    Adaptador simples para permitir ao Gemini Live
    executar as ações Spotify já existentes.
    """
    allowed_actions = {
        "pause",
        "resume",
        "next",
        "previous",
        "current_track",
    }

    if action not in allowed_actions:
        return {
            "ok": False,
            "action": action,
            "message": "Ação Spotify não permitida.",
        }

    return execute_intent(
        _SpotifyIntent(action)
    )