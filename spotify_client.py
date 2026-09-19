import base64
import time
from urllib.parse import urlencode

import requests

from token_store import (
    save_refresh_token,
    load_refresh_token,
)


class SpotifyClient:

    API_BASE_URL = "https://api.spotify.com/v1"

    TOKEN_URL = (
        "https://accounts.spotify.com/api/token"
    )

    AUTHORIZE_URL = (
        "https://accounts.spotify.com/authorize"
    )


    def __init__(
        self,
        client_id,
        client_secret,
        redirect_uri,
        token_file,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_file = token_file

        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = 0


    # -----------------------------------------------------
    # AUTENTICAÇÃO BÁSICA
    # -----------------------------------------------------

    def _basic_auth(self):

        credentials = (
            f"{self.client_id}:"
            f"{self.client_secret}"
        )

        encoded = base64.b64encode(
            credentials.encode()
        ).decode()

        return encoded


    # -----------------------------------------------------
    # URL DE LOGIN
    # -----------------------------------------------------

    def authorization_url(
        self,
        state,
        scopes,
    ):

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
        }

        return (
            self.AUTHORIZE_URL
            + "?"
            + urlencode(params)
        )


    # -----------------------------------------------------
    # TROCAR AUTHORIZATION CODE POR TOKENS
    # -----------------------------------------------------

    def exchange_code(self, code):

        headers = {
            "Authorization":
                f"Basic {self._basic_auth()}",

            "Content-Type":
                "application/x-www-form-urlencoded",
        }

        data = {
            "grant_type":
                "authorization_code",

            "code":
                code,

            "redirect_uri":
                self.redirect_uri,
        }

        try:

            response = requests.post(
                self.TOKEN_URL,
                headers=headers,
                data=data,
                timeout=10,
            )

        except requests.RequestException as error:

            return False, str(error)


        if response.status_code != 200:

            return False, response.text


        token_data = response.json()

        self.access_token = (
            token_data["access_token"]
        )

        self.token_expires_at = (
            time.time()
            + token_data.get(
                "expires_in",
                3600
            )
            - 60
        )


        new_refresh_token = (
            token_data.get(
                "refresh_token"
            )
        )

        if new_refresh_token:

            self.refresh_token = (
                new_refresh_token
            )

            save_refresh_token(
                self.token_file,
                self.refresh_token,
            )


        return True, None


    # -----------------------------------------------------
    # RENOVAR ACCESS TOKEN
    # -----------------------------------------------------

    def refresh_access_token(self):

        if not self.refresh_token:
            return False


        headers = {
            "Authorization":
                f"Basic {self._basic_auth()}",

            "Content-Type":
                "application/x-www-form-urlencoded",
        }


        data = {
            "grant_type":
                "refresh_token",

            "refresh_token":
                self.refresh_token,
        }


        try:

            response = requests.post(
                self.TOKEN_URL,
                headers=headers,
                data=data,
                timeout=10,
            )

        except requests.RequestException as error:

            print(
                "Erro ao renovar token:",
                error
            )

            return False


        if response.status_code != 200:

            print(
                "Erro ao renovar token:",
                response.text
            )

            return False


        token_data = response.json()

        self.access_token = (
            token_data["access_token"]
        )


        self.token_expires_at = (
            time.time()
            + token_data.get(
                "expires_in",
                3600
            )
            - 60
        )


        new_refresh_token = (
            token_data.get(
                "refresh_token"
            )
        )


        if new_refresh_token:

            self.refresh_token = (
                new_refresh_token
            )

            save_refresh_token(
                self.token_file,
                self.refresh_token,
            )


        print(
            "Access token Spotify renovado."
        )

        return True


    # -----------------------------------------------------
    # RESTAURAR SESSÃO AO ARRANCAR
    # -----------------------------------------------------

    def restore_session(self):

        token = load_refresh_token(
            self.token_file
        )

        if not token:
            return False

        self.refresh_token = token

        return self.refresh_access_token()


    # -----------------------------------------------------
    # GARANTIR ACCESS TOKEN VÁLIDO
    # -----------------------------------------------------

    def get_valid_access_token(self):

        if not self.access_token:
            return None


        if (
            time.time()
            >= self.token_expires_at
        ):

            if not self.refresh_access_token():
                return None


        return self.access_token


    # -----------------------------------------------------
    # PEDIDO GENÉRICO À SPOTIFY API
    # -----------------------------------------------------

    def _request(
        self,
        method,
        endpoint,
    ):

        token = (
            self.get_valid_access_token()
        )

        if not token:

            return None, "not_authenticated"


        headers = {
            "Authorization":
                f"Bearer {token}"
        }


        url = (
            self.API_BASE_URL
            + endpoint
        )


        try:

            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=10,
            )

        except requests.RequestException as error:

            return None, str(error)


        # Token inesperadamente rejeitado.
        # Tentamos renová-lo uma vez.

        if response.status_code == 401:

            if not self.refresh_access_token():

                return (
                    None,
                    "authentication_failed"
                )


            headers = {
                "Authorization":
                    f"Bearer {self.access_token}"
            }


            try:

                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    timeout=10,
                )

            except requests.RequestException as error:

                return None, str(error)


        return response, None


    # -----------------------------------------------------
    # ESTADO ATUAL
    # -----------------------------------------------------

    def get_status(self):

        response, error = self._request(
            "GET",
            "/me/player",
        )


        if response is None:

            if error == "not_authenticated":

                return {
                    "authenticated": False
                }, 401


            return {
                "error":
                    "spotify_unreachable",

                "details":
                    error,
            }, 503


        if response.status_code == 204:

            return {
                "authenticated": True,
                "active": False,
                "playing": False,
            }, 200


        if response.status_code != 200:

            return {
                "error":
                    "spotify_error",

                "status":
                    response.status_code,

                "details":
                    response.text,
            }, response.status_code


        info = response.json()

        item = info.get("item")


        if not item:

            return {
                "authenticated": True,
                "active": False,
                "playing": False,
            }, 200


        artists = ", ".join(
            artist["name"]
            for artist
            in item.get(
                "artists",
                []
            )
        )


        album_info = (
            item.get(
                "album",
                {}
            )
        )


        images = (
            album_info.get(
                "images",
                []
            )
        )


        cover = ""

        if images:
            cover = (
                images[0].get(
                    "url",
                    ""
                )
            )


        device = (
            info.get("device")
            or {}
        )


        return {

            "authenticated": True,
            "active": True,

            "track":
                item.get(
                    "name",
                    ""
                ),

            "artist":
                artists,

            "album":
                album_info.get(
                    "name",
                    ""
                ),

            "playing":
                info.get(
                    "is_playing",
                    False
                ),

            "progress_ms":
                info.get(
                    "progress_ms"
                )
                or 0,

            "duration_ms":
                item.get(
                    "duration_ms"
                )
                or 0,

            "device":
                device.get(
                    "name",
                    ""
                ),

            "volume_percent":
                device.get(
                    "volume_percent"
                ),

            "cover":
                cover,

            "spotify_timestamp":
                info.get(
                    "timestamp"
                ),

            "server_time_ms":
                int(
                    time.time()
                    * 1000
                ),

        }, 200


    # -----------------------------------------------------
    # COMANDOS
    # -----------------------------------------------------

    def send_command(
        self,
        method,
        endpoint,
    ):

        response, error = self._request(
            method,
            endpoint,
        )


        if response is None:

            return {
                "success": False,
                "error": error,
            }, 401


        if response.status_code == 204:

            return {
                "success": True
            }, 200


        return {
            "success": False,

            "spotify_status":
                response.status_code,

            "details":
                response.text,

        }, response.status_code