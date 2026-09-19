import os
import time
import secrets
import base64
import requests
from urllib.parse import urlencode

from flask import Flask, request, redirect, jsonify, Response
from dotenv import load_dotenv

import json
from pathlib import Path


# ---------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------

load_dotenv()

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
TOKEN_FILE = Path(__file__).resolve().with_name(
    ".spotify_token.json"
)

SCOPES = [
    "user-read-currently-playing",
    "user-read-playback-state",
    "user-modify-playback-state",
]

app = Flask(__name__)

state_value = None

access_token = None
refresh_token = None
token_expires_at = 0


# ---------------------------------------------------------
# SPOTIFY - AUTENTICAÇÃO
# ---------------------------------------------------------

def spotify_basic_auth():
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"

    encoded = base64.b64encode(
        credentials.encode()
    ).decode()

    return encoded

def save_refresh_token(token):
    if not token:
        return

    data = {
        "refresh_token": token
    }

    temp_file = TOKEN_FILE.with_name(
        TOKEN_FILE.name + ".tmp"
    )

    try:
        temp_file.write_text(
            json.dumps(data),
            encoding="utf-8"
        )

        os.replace(
            temp_file,
            TOKEN_FILE
        )

        print("Refresh token guardado no disco.")

    except OSError as error:
        print(
            "Erro ao guardar refresh token:",
            error
        )


def load_refresh_token():
    global refresh_token

    if not TOKEN_FILE.exists():
        return False

    try:
        data = json.loads(
            TOKEN_FILE.read_text(
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

        return False


    token = data.get("refresh_token")

    if not token:
        return False

    refresh_token = token

    print(
        "Refresh token carregado do disco."
    )

    return True

def refresh_access_token():
    global access_token
    global refresh_token
    global token_expires_at

    if not refresh_token:
        return False

    headers = {
        "Authorization": f"Basic {spotify_basic_auth()}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers=headers,
        data=data,
        timeout=10,
    )

    if response.status_code != 200:
        print("Erro ao renovar token:")
        print(response.text)
        return False

    token_data = response.json()

    access_token = token_data["access_token"]

    token_expires_at = (
        time.time()
        + token_data.get("expires_in", 3600)
        - 60
    )

    new_refresh_token = token_data.get(
        "refresh_token"
    )

    if new_refresh_token:
        refresh_token = new_refresh_token

        save_refresh_token(
            refresh_token
        )


    print("Token Spotify renovado.")

    return True


def get_valid_access_token():
    if not access_token:
        return None

    if time.time() >= token_expires_at:
        if not refresh_access_token():
            return None

    return access_token


# ---------------------------------------------------------
# LOGIN
# ---------------------------------------------------------

@app.route("/login")
def login():
    global state_value

    state_value = secrets.token_urlsafe(16)

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state_value,
    }

    authorization_url = (
        "https://accounts.spotify.com/authorize?"
        + urlencode(params)
    )

    return redirect(authorization_url)


@app.route("/callback")
def callback():
    global access_token
    global refresh_token
    global token_expires_at
    global state_value

    error = request.args.get("error")
    code = request.args.get("code")
    received_state = request.args.get("state")

    if error:
        return f"Spotify recusou a autorização: {error}"

    if received_state != state_value:
        return "Erro: state inválido."

    headers = {
        "Authorization": f"Basic {spotify_basic_auth()}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers=headers,
        data=data,
        timeout=10,
    )

    if response.status_code != 200:
        return f"Erro ao obter token: {response.text}"

    token_data = response.json()

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    if refresh_token:
        save_refresh_token(
            refresh_token
        )

    token_expires_at = (
        time.time()
        + token_data.get("expires_in", 3600)
        - 60
    )

    print()
    print("==============================")
    print("SPOTIFY AUTENTICADO")
    print("==============================")
    print("Refresh token:", bool(refresh_token))
    print()

    return redirect("/")


# ---------------------------------------------------------
# API QUE FUTURAMENTE SERÁ USADA PELO ESP32
# ---------------------------------------------------------

@app.route("/api/status")
def api_status():

    token = get_valid_access_token()

    if not token:
        return jsonify({
            "authenticated": False
        }), 401

    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(
        "https://api.spotify.com/v1/me/player",
        headers=headers,
        timeout=10,
    )

    # Nenhuma reprodução/dispositivo ativo
    if response.status_code == 204:
        return jsonify({
            "authenticated": True,
            "active": False,
            "playing": False,
        })

    # Token inválido/expirado
    if response.status_code == 401:

        if refresh_access_token():
            return redirect("/api/status")

        return jsonify({
            "authenticated": False
        }), 401

    if response.status_code != 200:
        return jsonify({
            "error": "spotify_error",
            "status": response.status_code,
            "details": response.text,
        }), response.status_code

    info = response.json()

    item = info.get("item")

    if not item:
        return jsonify({
            "authenticated": True,
            "active": False,
            "playing": False,
        })

    artists = ", ".join(
        artist["name"]
        for artist in item.get("artists", [])
    )

    album_info = item.get("album", {})

    album = album_info.get("name", "")

    images = album_info.get("images", [])

    cover = ""

    if images:
        cover = images[0].get("url", "")

    device = info.get("device") or {}

    progress_ms = info.get("progress_ms") or 0
    duration_ms = item.get("duration_ms") or 0

    return jsonify({
        "authenticated": True,
        "active": True,

        "track": item.get("name", ""),
        "artist": artists,
        "album": album,

        "playing": info.get("is_playing", False),

        "progress_ms": progress_ms,
        "duration_ms": duration_ms,

        "device": device.get("name", ""),
        "volume_percent": device.get("volume_percent"),

        "cover": cover,

        "spotify_timestamp": info.get("timestamp"),
        "server_time_ms": int(time.time() * 1000),
    })
# ---------------------------------------------------------
# CONTROLO DO PLAYER
# ---------------------------------------------------------

def send_spotify_command(method, endpoint):
    token = get_valid_access_token()

    if not token:
        return jsonify({
            "success": False,
            "error": "not_authenticated"
        }), 401

    headers = {
        "Authorization": f"Bearer {token}"
    }

    url = f"https://api.spotify.com/v1{endpoint}"

    response = requests.request(
        method,
        url,
        headers=headers,
        timeout=10,
    )

    # Se o token tiver expirado, tenta renová-lo uma vez
    if response.status_code == 401:

        if not refresh_access_token():
            return jsonify({
                "success": False,
                "error": "authentication_failed"
            }), 401

        headers = {
            "Authorization": f"Bearer {access_token}"
        }

        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=10,
        )

    # Os comandos Player devolvem 204 quando funcionam
    if response.status_code == 204:

        return jsonify({
            "success": True
        })

    return jsonify({
        "success": False,
        "spotify_status": response.status_code,
        "details": response.text,
    }), response.status_code


@app.route("/api/play", methods=["POST"])
def api_play():
    return send_spotify_command(
        "PUT",
        "/me/player/play"
    )


@app.route("/api/pause", methods=["POST"])
def api_pause():
    return send_spotify_command(
        "PUT",
        "/me/player/pause"
    )


@app.route("/api/next", methods=["POST"])
def api_next():
    return send_spotify_command(
        "POST",
        "/me/player/next"
    )


@app.route("/api/previous", methods=["POST"])
def api_previous():
    return send_spotify_command(
        "POST",
        "/me/player/previous"
    )


# ---------------------------------------------------------
# INTERFACE WEB
# ---------------------------------------------------------

HTML_PAGE = """
<!DOCTYPE html>

<html lang="pt">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>Spotify Monitor</title>

<style>

    * {
        box-sizing: border-box;
    }

    body {
        margin: 0;
        min-height: 100vh;

        background:
            linear-gradient(
                160deg,
                #161616,
                #080808
            );

        color: white;

        font-family:
            Arial,
            Helvetica,
            sans-serif;

        display: flex;
        justify-content: center;
        align-items: center;
    }

    .player {
        width: min(430px, 92vw);

        padding: 28px;

        background:
            rgba(255, 255, 255, 0.06);

        border-radius: 24px;

        box-shadow:
            0 20px 60px
            rgba(0, 0, 0, 0.45);
    }

    .cover {
        width: 100%;
        aspect-ratio: 1 / 1;

        object-fit: cover;

        border-radius: 18px;

        background: #222;

        display: block;
    }

    .track {
        margin-top: 22px;

        font-size: 27px;
        font-weight: bold;

        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
    }

    .artist {
        margin-top: 7px;

        font-size: 18px;

        color: #bbbbbb;

        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
    }

    .album {
        margin-top: 5px;

        font-size: 14px;

        color: #777777;

        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
    }

    .progress-area {
        margin-top: 28px;
    }

    .progress-background {
        position: relative;

        height: 6px;

        background: #3a3a3a;

        border-radius: 20px;

        overflow: hidden;
    }

    .progress-bar {
        position: absolute;

        top: 0;
        left: 0;

        height: 100%;
        width: 0%;

        background: white;

        border-radius: 20px;
    }

    .time-row {
        display: flex;

        justify-content: space-between;

        margin-top: 8px;

        font-size: 13px;

        color: #999999;
    }

    .controls {
        display: flex;
        justify-content: center;
        align-items: center;
        
        gap: 32px;

        margin-top: 25px;
        margin-bottom: 10px;
    }

    .control-button {
        width: 52px;
        height: 52px;

        border: none;
        border-radius: 50%;

        background: transparent;

        color: white;

        font-size: 20px;

        cursor: pointer;

        transition:
            transform 0.15s,
            background 0.15s;
    }


    .control-button:hover {
        background:
            rgba(255,255,255,0.10);

        transform: scale(1.08);
    }


    .control-button:active {
        transform: scale(0.92);
    }


    .main-button {
        width: 66px;
        height: 66px;

        background: white;

        color: black;

        font-size: 25px;
    }


    .main-button:hover {
        background: #dddddd;
    }


    .status-row {
        display: flex;

        justify-content: space-between;

        margin-top: 24px;

        padding-top: 18px;

        border-top:
            1px solid
            rgba(255, 255, 255, 0.08);

        color: #999999;

        font-size: 14px;
    }

    .playing {
        color: #eeeeee;
    }

    .login {
        text-align: center;
    }

    .login a {
        color: white;
        text-decoration: none;

        padding: 12px 20px;

        border:
            1px solid
            #666666;

        border-radius: 20px;
    }

</style>

</head>


<body>

<div class="player" id="player">

    <div id="loginScreen"
         class="login"
         style="display:none">

        <h2>Spotify não autenticado</h2>

        <p>
            <a href="/login">
                Ligar ao Spotify
            </a>
        </p>

    </div>


    <div id="playerScreen"
         style="display:none">

        <img
            id="cover"
            class="cover"
            alt="Capa do álbum"
        >

        <div
            id="track"
            class="track">
        </div>

        <div
            id="artist"
            class="artist">
        </div>

        <div
            id="album"
            class="album">
        </div>


        <div class="progress-area">

            <div class="progress-background">

                <div
                    id="progressBar"
                    class="progress-bar">
                </div>

            </div>

            <div class="time-row">

                <span id="currentTime">
                    0:00
                </span>

                <span id="duration">
                    0:00
                </span>

            </div>

	</div>


	<!-- CONTROLOS -->
	<div class="controls">

    	<button
        	class="control-button"
        	onclick="previousTrack()">
        	◀◀
    	</button>

    	<button
        	id="playPauseButton"
        	class="control-button main-button"
        	onclick="togglePlayPause()">
        	▶
    	</button>

    	<button
        	class="control-button"
        	onclick="nextTrack()">
        	▶▶
    	</button>

	</div>
	

	<!-- STATUS -->
        <div class="status-row">

            <span id="device"></span>

            <span
                id="state"
                class="playing">
            </span>

        </div>

</div>

    <div
        id="waitingScreen"
        style="display:none">

        <h2>Spotify ligado</h2>

        <p>
            Não existe reprodução ativa.
        </p>

    </div>

</div>


<script>

let progressMs = 0;
let durationMs = 0;
let playing = false;

let progressAnchorTime = Date.now();


function formatTime(milliseconds) {

    if (!milliseconds) {
        return "0:00";
    }

    const totalSeconds =
        Math.floor(milliseconds / 1000);

    const minutes =
        Math.floor(totalSeconds / 60);

    const seconds =
        totalSeconds % 60;

    return (
        minutes
        + ":"
        + seconds
            .toString()
            .padStart(2, "0")
    );
}


function updateProgressDisplay() {

    let currentProgress = progressMs;

    if (playing) {

        const elapsed =
            Date.now()
            - progressAnchorTime;

        currentProgress += elapsed;

    }

    if (
        durationMs > 0
        &&
        currentProgress > durationMs
    ) {
        currentProgress = durationMs;
    }

    let percent = 0;

    if (durationMs > 0) {

        percent =
            (
                currentProgress
                /
                durationMs
            )
            * 100;

    }

    document
        .getElementById("progressBar")
        .style.width =
            percent + "%";

    document
        .getElementById("currentTime")
        .textContent =
            formatTime(currentProgress);

    document
        .getElementById("duration")
        .textContent =
            formatTime(durationMs);

}


async function loadStatus() {

    try {

        const response =
            await fetch(
                "/api/status",
                {
                    cache: "no-store"
                }
            );


        if (response.status === 401) {

            document
                .getElementById("loginScreen")
                .style.display = "block";

            document
                .getElementById("playerScreen")
                .style.display = "none";

            document
                .getElementById("waitingScreen")
                .style.display = "none";

            return;

        }


        const data =
            await response.json();


        if (!data.active) {

            playing = false;
            progressMs = 0;
            durationMs = 0;
            progressAnchorTime = Date.now();

            document
                .getElementById("waitingScreen")
                .style.display = "block";

            document
                .getElementById("playerScreen")
                .style.display = "none";

            document
                .getElementById("loginScreen")
                .style.display = "none";

            return;

        }


        document
            .getElementById("playerScreen")
            .style.display = "block";

        document
            .getElementById("waitingScreen")
            .style.display = "none";

        document
            .getElementById("loginScreen")
            .style.display = "none";


        document
            .getElementById("track")
            .textContent =
                data.track;


        document
            .getElementById("artist")
            .textContent =
                data.artist;


        document
            .getElementById("album")
            .textContent =
                data.album;


        document
            .getElementById("device")
            .textContent =
                data.device;


        document
            .getElementById("state")
            .textContent =
                data.playing
                ? "PLAYING"
                : "PAUSED";


        const coverElement =
            document.getElementById("cover");

        if (data.cover) {

            coverElement.src = data.cover;
            coverElement.style.display = "block";

        }
        else {

            coverElement.removeAttribute("src");
            coverElement.style.display = "none";

        }


        progressMs =
            data.progress_ms || 0;

        durationMs =
            data.duration_ms || 0;

        playing =
            data.playing;
        
        document
            .getElementById("playPauseButton")
            .textContent =
                playing
                ? "❚❚"
                : "▶";

        progressAnchorTime =
            Date.now();


        updateProgressDisplay();

    }

    catch (error) {

        console.error(
            "Erro ao consultar Spotify:",
            error
        );

    }

}

async function sendCommand(command) {

    try {

        const response =
            await fetch(
                "/api/" + command,
                {
                    method: "POST"
                }
            );

        const result =
            await response.json();


        if (!result.success) {

            console.error(
                "Erro no comando Spotify:",
                result
            );

            return false;
        }

        return true;

    }

    catch (error) {

        console.error(
            "Erro ao enviar comando:",
            error
        );

        return false;
    }

}


async function togglePlayPause() {

    const button =
        document.getElementById(
            "playPauseButton"
        );


    if (playing) {

        const success =
            await sendCommand("pause");

        if (success) {

            // Calcula a posição atual antes de parar
            progressMs +=
                Date.now()
                - progressAnchorTime;

            playing = false;

            progressAnchorTime =
                Date.now();

            button.textContent = "▶";

            document
                .getElementById("state")
                .textContent =
                    "PAUSED";
        }

    }

    else {

        const success =
            await sendCommand("play");

        if (success) {

            playing = true;

            progressAnchorTime =
                Date.now();

            button.textContent = "❚❚";

            document
                .getElementById("state")
                .textContent =
                    "PLAYING";
        }

    }


    // Confirma depois o estado real no Spotify
    setTimeout(
        loadStatus,
        500
    );
}


async function nextTrack() {

    const success =
        await sendCommand("next");

    if (success) {

        // Dá algum tempo ao Spotify
        // para mudar de faixa

        setTimeout(
            loadStatus,
            500
        );
    }
}


async function previousTrack() {

    const success =
        await sendCommand("previous");

    if (success) {

        setTimeout(
            loadStatus,
            500
        );
    }
}
// Sincronização com o Spotify
// a cada 5 segundos.

setInterval(
    loadStatus,
    5000
);


// Movimento visual suave.
// Não faz pedidos ao Spotify.

setInterval(
    updateProgressDisplay,
    100
);


// Primeira consulta imediatamente.

loadStatus();

</script>


</body>

</html>
"""


@app.route("/")
def index():
    return Response(
        HTML_PAGE,
        mimetype="text/html"
    )


# ---------------------------------------------------------
# ARRANQUE
# ---------------------------------------------------------

if __name__ == "__main__":

    if not CLIENT_ID:
        print("ERRO: SPOTIFY_CLIENT_ID não encontrado.")

    elif not CLIENT_SECRET:
        print("ERRO: SPOTIFY_CLIENT_SECRET não encontrado.")

    elif not REDIRECT_URI:
        print("ERRO: SPOTIFY_REDIRECT_URI não encontrado.")

    else:

        print()
        print("==============================")
        print("Spotify Service")
        print("==============================")
        print()
        print("Interface:")
        print("http://127.0.0.1:8888")
        print()
        print("API:")
        print("http://127.0.0.1:8888/api/status")
        print()

        if load_refresh_token():

            print(
                "A tentar restaurar sessão Spotify..."
            )

            if refresh_access_token():

                print(
                    "Sessão Spotify restaurada automaticamente!"
                )


            else:

                print(
                    "Não foi possível restaurar a sessão."
                )

        else:

            print(
                "Ainda não existe refresh token guardado."
            )

            print(
                "Será necessário autenticar uma vez."
            )

        app.run(
            host="0.0.0.0",
            port=8888,
            debug=True,
        )