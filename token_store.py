import json
import os
from pathlib import Path


def save_refresh_token(token_file, token):
    if not token:
        return False

    token_file = Path(token_file)

    temp_file = token_file.with_name(
        token_file.name + ".tmp"
    )

    data = {
        "refresh_token": token
    }

    try:
        temp_file.write_text(
            json.dumps(data),
            encoding="utf-8"
        )

        os.replace(
            temp_file,
            token_file
        )

        print("Refresh token guardado no disco.")

        return True

    except OSError as error:
        print(
            "Erro ao guardar refresh token:",
            error
        )

        return False


def load_refresh_token(token_file):
    token_file = Path(token_file)

    if not token_file.exists():
        return None

    try:
        data = json.loads(
            token_file.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError
    ) as error:

        print(
            "Erro ao carregar refresh token:",
            error
        )

        return None


    token = data.get("refresh_token")

    if not token:
        return None

    print("Refresh token carregado do disco.")

    return token