import re

from intent_service import SpotifyIntent


def understand_command_local(text: str):
    original = text.strip()
    t = original.lower().strip(" .!?,")

    # NEXT
    if t in {
        "próxima",
        "proxima",
        "passa esta",
        "passa",
        "seguinte",
        "próxima música",
        "proxima musica",
    }:
        return SpotifyIntent(action="next")

    # PREVIOUS
    if t in {
        "anterior",
        "música anterior",
        "musica anterior",
        "volta atrás",
        "volta atras",
        "volta à anterior",
        "volta a anterior",
    }:
        return SpotifyIntent(action="previous")

    # PAUSE
    if t in {
        "pausa",
        "faz pausa",
        "para",
        "pára",
        "para a música",
        "para a musica",
    }:
        return SpotifyIntent(action="pause")

    # RESUME
    if t in {
        "continua",
        "retoma",
        "continua a tocar",
        "volta a tocar",
        "play",
    }:
        return SpotifyIntent(action="resume")

    # CURRENT TRACK
    current_patterns = [
        r"qual .*música.*tocar",
        r"qual .*musica.*tocar",
        r"o que .*tocar",
        r"que música.*",
        r"que musica.*",
        r"quem .*canta",
    ]

    if any(re.search(pattern, t) for pattern in current_patterns):
        return SpotifyIntent(action="current_track")

    # VOLUME
    match = re.search(
        r"(?:volume|som).*?(\d{1,3})",
        t,
    )

    if match:
        value = max(0, min(100, int(match.group(1))))

        return SpotifyIntent(
            action="set_volume",
            volume_percent=value,
        )

    # PLAY / SEARCH simples
    play_prefixes = [
        "põe ",
        "poe ",
        "toca ",
        "mete ",
        "quero ouvir ",
    ]

    for prefix in play_prefixes:
        if t.startswith(prefix):
            query = original[len(prefix):].strip(" .!?,")

            if query:
                return SpotifyIntent(
                    action="play_search",
                    query=query,
                )

    return None