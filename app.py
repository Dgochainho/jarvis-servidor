import os
import secrets
import wave
import time
import math
import struct
from pathlib import Path

from flask import (
    Flask,
    request,
    redirect,
    jsonify,
    render_template,
    Response,
    stream_with_context,
)

from spotify_client import SpotifyClient
from cover_service import CoverService
from mdns_service import MdnsService
from gemini_live_service import stream_gemini_live_reply
from live_voice_ws_server import LiveVoiceWebSocketServer

from dotenv import load_dotenv

from transcription_service import transcribe_audio
from intent_service import understand_command
from action_service import execute_intent
#from voice_understanding_service import understand_audio
from local_intent_service import understand_command_local



# ---------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------

load_dotenv()


CLIENT_ID = os.getenv(
    "SPOTIFY_CLIENT_ID"
)

CLIENT_SECRET = os.getenv(
    "SPOTIFY_CLIENT_SECRET"
)

REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI"
)


BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
)


TOKEN_FILE = (
    BASE_DIR
    / ".spotify_token.json"
)


SCOPES = [

    "user-read-currently-playing",

    "user-read-playback-state",

    "user-modify-playback-state",
]


app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
VOICE_WAV_PATH = BASE_DIR / "command.wav"


spotify = SpotifyClient(

    client_id=CLIENT_ID,

    client_secret=CLIENT_SECRET,

    redirect_uri=REDIRECT_URI,

    token_file=TOKEN_FILE,
)

cover_service = CoverService()

mdns_service = MdnsService(
    hostname="spotify-service",
    port=8888,
)

voice_ws_server = LiveVoiceWebSocketServer(
    host="0.0.0.0",
    port=8765,
)

state_value = None

def make_audio_ack():
    sample_rate = 16000
    amplitude = 5000

    pcm = bytearray()

    def add_tone(freq, duration_ms):
        samples = int(
            sample_rate * duration_ms / 1000
        )

        for n in range(samples):
            value = int(
                amplitude *
                math.sin(
                    2.0 *
                    math.pi *
                    freq *
                    n /
                    sample_rate
                )
            )

            pcm.extend(
                struct.pack("<h", value)
            )

    def add_silence(duration_ms):
        samples = int(
            sample_rate * duration_ms / 1000
        )

        pcm.extend(
            b"\x00\x00" * samples
        )

    # Dois tons diferentes
    add_tone(880, 140)
    add_silence(80)
    add_tone(1200, 140)

    # Silêncio final para evitar que o microfone
    # seja rearmado enquanto o speaker ainda termina.
    add_silence(180)

    return bytes(pcm)

def load_jarvis_reply():
    wav_path = "jarvis_reply.wav"

    with wave.open(wav_path, "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()

        if channels != 1:
            raise RuntimeError(
                f"jarvis_reply.wav tem {channels} canais; esperado 1"
            )

        if sample_width != 2:
            raise RuntimeError(
                f"jarvis_reply.wav usa {sample_width * 8} bits; esperado 16"
            )

        if sample_rate != 16000:
            raise RuntimeError(
                f"jarvis_reply.wav usa {sample_rate} Hz; esperado 16000"
            )

        return wav.readframes(
            wav.getnframes()
        )


# ---------------------------------------------------------
# INTERFACE
# ---------------------------------------------------------

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ---------------------------------------------------------
# LOGIN
# ---------------------------------------------------------

@app.route("/login")
def login():

    global state_value

    state_value = (
        secrets.token_urlsafe(16)
    )


    url = spotify.authorization_url(
        state_value,
        SCOPES,
    )


    return redirect(url)


# ---------------------------------------------------------
# CALLBACK OAUTH
# ---------------------------------------------------------

@app.route("/callback")
def callback():

    global state_value


    error = request.args.get(
        "error"
    )

    code = request.args.get(
        "code"
    )

    received_state = (
        request.args.get(
            "state"
        )
    )


    if error:

        return (
            "Spotify recusou "
            f"a autorização: {error}"
        )


    if (
        not state_value
        or received_state
        != state_value
    ):

        return (
            "Erro: state inválido.",
            400
        )


    success, error_message = (
        spotify.exchange_code(
            code
        )
    )


    if not success:

        return (
            "Erro ao obter token: "
            f"{error_message}",
            500
        )


    state_value = None


    print()
    print("==============================")
    print("SPOTIFY AUTENTICADO")
    print("==============================")
    print()


    return redirect("/")

# ---------------------------------------------------------
# STATUS
# ---------------------------------------------------------

@app.route("/api/status")
def api_status():

    data, status_code = (
        spotify.get_status()
    )

    return (
        jsonify(data),
        status_code
    )

# ---------------------------------------------------------
# CAPA
# ---------------------------------------------------------

@app.route("/api/cover.rgb565")
def api_cover():

    status, status_code = (
        spotify.get_status()
    )

    if status_code != 200:

        return (
            "Não foi possível obter "
            "estado Spotify.",
            status_code
        )


    if not status.get("active"):

        return (
            "Sem reprodução ativa.",
            404
        )


    cover_url = status.get(
        "cover"
    )


    if not cover_url:

        return (
            "Faixa sem capa.",
            404
        )


    try:

        image_data = (
            cover_service.get_rgb565(
                cover_url,
                width=120,
                height=120,
            )
        )

    except Exception as error:

        print(
            "Erro ao processar capa:",
            error
        )

        return (
            "Erro ao processar capa.",
            500
        )


    return Response(
        image_data,
        mimetype="application/octet-stream",

        headers={
            "X-Image-Width": "120",
            "X-Image-Height": "120",
            "X-Image-Format": "RGB565",
            "Cache-Control": "no-store",
        }
    )

# ---------------------------------------------------------
# COMANDOS
# ---------------------------------------------------------

@app.route(
    "/api/play",
    methods=["POST"]
)
def api_play():

    data, status_code = (
        spotify.send_command(
            "PUT",
            "/me/player/play"
        )
    )

    return jsonify(data), status_code


@app.route(
    "/api/pause",
    methods=["POST"]
)
def api_pause():

    data, status_code = (
        spotify.send_command(
            "PUT",
            "/me/player/pause"
        )
    )

    return jsonify(data), status_code


@app.route(
    "/api/next",
    methods=["POST"]
)
def api_next():

    data, status_code = (
        spotify.send_command(
            "POST",
            "/me/player/next"
        )
    )

    return jsonify(data), status_code


@app.route(
    "/api/previous",
    methods=["POST"]
)
def api_previous():

    data, status_code = (
        spotify.send_command(
            "POST",
            "/me/player/previous"
        )
    )

    return jsonify(data), status_code

@app.post("/api/voice")
def api_voice():
    request_start = time.perf_counter()

    pcm_data = request.get_data(cache=False)

    if not pcm_data:
        return jsonify({
            "ok": False,
            "error": "Nenhum audio recebido"
        }), 400

    # PCM 16-bit tem sempre 2 bytes por amostra.
    if len(pcm_data) % 2 != 0:
        return jsonify({
            "ok": False,
            "error": "Tamanho PCM invalido para audio 16-bit"
        }), 400

    # Limite defensivo.
    # A BOX atualmente grava no máximo ~384 KB.
    if len(pcm_data) > 512000:
        return jsonify({
            "ok": False,
            "error": "Audio demasiado grande"
        }), 413

    try:
        with wave.open(str(VOICE_WAV_PATH), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)      # 16-bit = 2 bytes
            wav_file.setframerate(16000)
            wav_file.writeframes(pcm_data)

    except Exception as exc:
        print(f"[VOICE] Erro ao criar WAV: {exc}")

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 500
    
    try:
        if request.headers.get("X-Response-Audio") == "pcm16":

            print()
            print("[LIVE] ===============================")
            print("[LIVE] Modo Gemini Live")
            print("[LIVE] Audio BOX -> Gemini -> BOX")
            print("[LIVE] ===============================")
            print()

            return Response(
                stream_with_context(
                    stream_gemini_live_reply(
                        pcm_data
                    )
                ),
                status=200,
                mimetype="application/octet-stream",
                headers={
                    "X-Audio-Sample-Rate": "16000",
                    "X-Audio-Channels": "1",
                    "X-Audio-Bits": "16",
                },
            )


        transcribe_start = time.perf_counter()

        transcript = transcribe_audio(
            VOICE_WAV_PATH
        )

        transcribe_time = time.perf_counter() - transcribe_start


        intent_start = time.perf_counter()

        intent = understand_command_local(
            transcript
        )

        used_llm_for_intent = False

        if intent is None:
            used_llm_for_intent = True

            intent = understand_command(
                transcript
            )

        intent_time = time.perf_counter() - intent_start

        print()
        print("[JARVIS] ===============================")
        print(f"[JARVIS] Acao: {intent.action}")
        print(f"[JARVIS] Query: {intent.query}")
        print(f"[JARVIS] Volume: {intent.volume_percent}")
        print("[JARVIS] ===============================")
        print()

        spotify_start = time.perf_counter()

        execution = execute_intent(intent)

        spotify_time = time.perf_counter() - spotify_start

        print()
        print("[JARVIS] ===============================")
        print(f"[JARVIS] Executado: {execution['ok']}")
        print(f"[JARVIS] Resposta: {execution['message']}")
        print("[JARVIS] ===============================")
        print()

    except Exception as exc:
        print(f"[VOICE] Erro na transcricao Gemini: {exc}")

        return jsonify({
            "ok": False,
            "error": f"Erro na transcricao: {exc}"
        }), 500





    duration_seconds = len(pcm_data) / 32000.0

    print()
    print("[VOICE] ===============================")
    print("[VOICE] Audio recebido da BOX")
    print(f"[VOICE] Bytes: {len(pcm_data)}")
    print(f"[VOICE] Duracao: {duration_seconds:.2f} s")
    print(f"[VOICE] WAV: {VOICE_WAV_PATH}")
    print("[VOICE] ===============================")
    print()


    total_time = time.perf_counter() - request_start

    print()
    print("[PERF] =================================")
    print(f"[PERF] Transcricao:        {transcribe_time:.2f} s")
    print(f"[PERF] Interpretacao:      {intent_time:.3f} s")
    print(f"[PERF] Intent usou Gemini: {used_llm_for_intent}")
    print(f"[PERF] Spotify:            {spotify_time:.2f} s")
    print(f"[PERF] Total servidor:     {total_time:.2f} s")
    print("[PERF] =================================")
    print()

    return jsonify({
        "ok": True,
        "bytes": len(pcm_data),
        "duration_seconds": round(duration_seconds, 2),
        "file": "command.wav",
        "transcript": transcript,
        "intent": intent.model_dump(),
        "execution": execution
    })

# ---------------------------------------------------------
# ARRANQUE
# ---------------------------------------------------------

if __name__ == "__main__":

    if not CLIENT_ID:

        raise RuntimeError(
            "SPOTIFY_CLIENT_ID "
            "não encontrado."
        )


    if not CLIENT_SECRET:

        raise RuntimeError(
            "SPOTIFY_CLIENT_SECRET "
            "não encontrado."
        )


    if not REDIRECT_URI:

        raise RuntimeError(
            "SPOTIFY_REDIRECT_URI "
            "não encontrado."
        )


    print()
    print("==============================")
    print("Spotify Service")
    print("==============================")
    print()


    if spotify.restore_session():

        print(
            "Sessão Spotify "
            "restaurada automaticamente!"
        )

    else:

        print(
            "Não existe sessão Spotify válida."
        )

        print(
            "Se necessário, autentica em /login."
        )


    print()
    print("Interface:")
    print(
        "http://127.0.0.1:8888"
    )

    print()

    print("API:")
    print(
        "http://127.0.0.1:8888/api/status"
    )

    print()


    mdns_service.start()

    try:
        voice_ws_server.start()

        app.run(
            host="0.0.0.0",
            port=8888,
            debug=False,
            use_reloader=False,
        )

    finally:
        voice_ws_server.stop()
        mdns_service.stop()