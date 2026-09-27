"""
O que os dois caminhos Gemini Live têm em comum.

Antes deste módulo existiam duas cópias do reamostrador, da configuração da
sessão e do despacho de ferramentas — uma em `live_voice_ws_server.py`
(WebSocket persistente, o caminho normal) e outra em `gemini_live_service.py`
(fallback HTTP). Já tinham divergido em três sítios: a descrição da ferramenta
`spotify_control`, o texto do `system_instruction` e o log das transcrições.

Nenhuma dessas divergências foi decidida. Todas são o resultado de editar uma
cópia e esquecer a outra — foi assim que o bug B2 passou meses a viver só num
dos ficheiros.

Regra a partir daqui: **o que os dois caminhos partilham vive aqui e só aqui.**
"""

import asyncio
import struct

from google.genai import types

from action_service import execute_spotify_action


MODEL = "gemini-3.1-flash-live-preview"


# ---------------------------------------------------------------------
# REAMOSTRAGEM 24 kHz -> 16 kHz
# ---------------------------------------------------------------------

class Pcm24kTo16k:
    """
    Conversor stateful: PCM16 mono 24 kHz -> PCM16 mono 16 kHz.

    O Gemini devolve áudio a 24 kHz; a BOX reproduz a 16 kHz. A razão é
    exactamente 3:2 — 3 amostras de entrada produzem 2 de saída.

    `carry` conserva os bytes que sobram entre chunks, o que permite
    converter uma resposta recebida por streaming sem estalidos nas
    fronteiras.
    """

    def __init__(self) -> None:
        self.carry = b""

    def convert(self, pcm24: bytes) -> bytes:
        data = self.carry + pcm24

        # 3 amostras PCM16 = 6 bytes.
        usable = (len(data) // 6) * 6

        if usable == 0:
            self.carry = data
            return b""

        output = bytearray()

        for offset in range(0, usable, 6):
            a, b, c = struct.unpack_from(
                "<hhh",
                data,
                offset,
            )

            # Pontos de saída nas posições 0 e 1,5.
            out1 = a
            out2 = int((int(b) + int(c)) / 2)

            output.extend(
                struct.pack(
                    "<hh",
                    out1,
                    out2,
                )
            )

        self.carry = data[usable:]

        return bytes(output)


# ---------------------------------------------------------------------
# FERRAMENTAS
# ---------------------------------------------------------------------

SPOTIFY_ACTIONS = [
    "pause",
    "resume",
    "next",
    "previous",
    "current_track",
]


SPOTIFY_CONTROL_DECLARATION = {
    "name": "spotify_control",

    "description": (
        "Controla a reprodução Spotify do utilizador. "
        "Usa esta função para pausar, retomar, avançar para a próxima "
        "música, voltar à música anterior, ou consultar a música que "
        "está a tocar."
    ),

    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": SPOTIFY_ACTIONS,
                "description": "A ação Spotify a executar.",
            }
        },
        "required": ["action"],
    },
}


# Fase 1.4 — fecho de conversa por voz.
# Acrescentar aqui a declaração `end_conversation` e tratá-la em
# dispatch_tool_calls. Ver claude/Fase_1-2_Consolidar_Live.md.


FUNCTION_DECLARATIONS = [
    SPOTIFY_CONTROL_DECLARATION,
]


SYSTEM_INSTRUCTION = (
    "És Jarvis, um assistente pessoal de inteligência artificial. "

    "Fala em português de Portugal, salvo se o utilizador pedir "
    "outra língua. "

    "Responde de forma natural e útil. Como estás num assistente de "
    "voz, prefere respostas relativamente concisas, excepto quando o "
    "utilizador pedir mais detalhe. "

    "Quando o utilizador pedir uma ação sobre o Spotify, usa "
    "obrigatoriamente a ferramenta spotify_control. "

    "Usa-a também quando o utilizador perguntar que música está "
    "atualmente a tocar. "

    "Para comandos Spotify, chama primeiro a ferramenta e só depois "
    "responde verbalmente. "

    "Nunca digas que uma ação Spotify foi executada sem teres "
    "recebido sucesso da ferramenta."
)


def build_live_config():
    """
    Configuração da sessão Gemini Live, igual para os dois caminhos.

    Devolve um dicionário novo a cada chamada, e uma lista nova de
    declarações: o SDK pode mutar o que recebe, e duas sessões a partilhar
    o mesmo objecto seria exactamente o género de acoplamento que este
    módulo existe para evitar.

    As declarações em si continuam a ser os mesmos dicionários — são
    constantes e ninguém as deve alterar em tempo de execução.
    """
    return {
        "response_modalities": ["AUDIO"],

        "tools": [
            {
                "function_declarations": list(FUNCTION_DECLARATIONS),
            }
        ],

        "input_audio_transcription": {},
        "output_audio_transcription": {},

        # A BOX já correu WakeNet e VAD: sabe exactamente onde a fala
        # começa e acaba. O VAD automático do Gemini só atrapalharia.
        "realtime_input_config": {
            "automatic_activity_detection": {
                "disabled": True
            }
        },

        "system_instruction": {
            "parts": [
                {"text": SYSTEM_INSTRUCTION}
            ]
        },
    }


# ---------------------------------------------------------------------
# DESPACHO DE FERRAMENTAS
# ---------------------------------------------------------------------

async def dispatch_tool_calls(tool_call, log_prefix):
    """
    Executa as ferramentas pedidas pelo Gemini e devolve as respostas.

    `log_prefix` é só a etiqueta do log ("[LIVE]" ou "[VOICE-WS]"), para
    que os dois caminhos continuem distinguíveis no stdout.

    Uma ferramenta desconhecida não levanta excepção: devolve um resultado
    com ok=False. O Gemini sabe explicar isso ao utilizador; uma excepção
    aqui derrubava a conversa inteira.
    """
    function_responses = []

    for fc in tool_call.function_calls:
        print(f"{log_prefix} Tool call: {fc.name}({fc.args})")

        if fc.name == "spotify_control":
            args = dict(fc.args or {})
            action = args.get("action")

            # action_service usa requests síncrono. Corre fora do event
            # loop para não bloquear a ligação Gemini Live.
            result = await asyncio.to_thread(
                execute_spotify_action,
                action,
            )

            print(f"{log_prefix} Spotify: {action} -> {result}")

        else:
            result = {
                "ok": False,
                "message": f"Ferramenta desconhecida: {fc.name}",
            }

        function_responses.append(
            types.FunctionResponse(
                id=fc.id,
                name=fc.name,
                response={"result": result},
            )
        )

    return function_responses
