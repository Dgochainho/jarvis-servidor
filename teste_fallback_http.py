"""
T20 · Fallback HTTP — exercita /api/voice sem envolver a BOX.

Porque existe:

O caminho HTTP só corre no firmware quando a sessão WebSocket nunca chega
a armar (voice.c, l. 1627-1647). Isso é raro e difícil de provocar à mão,
e foi por isso que o bug B2 sobreviveu meses sem ninguém dar por ele: o
ramo estava sempre a rebentar, mas quase nunca era chamado.

Este script chama o endpoint directamente, com um comando gravado que já
existe na pasta. Passa a ser um teste de um comando em vez de uma
encenação com a BOX.

Uso (com o venv activo, e o app.py a correr):

    python teste_fallback_http.py

Passa se: HTTP 200 e áudio devolvido com duração plausível.
Falha se:  HTTP != 200, ou zero bytes — que é como o B2 se manifestava.
"""

import sys
import wave
from pathlib import Path

import requests


ENDPOINT = "http://127.0.0.1:8888/api/voice"

# Fixture estável, versionada no repositório.
#
# NÃO usar command.wav: esse ficheiro é reescrito pelo /api/voice a cada
# pedido de voz — incluindo pelos pedidos deste script — e está no
# .gitignore. Usá-lo significava testar "seja lá o que for que foi dito
# à BOX da última vez", e não funcionava de todo num clone limpo.
ENTRADA = Path(__file__).with_name("teste_comando.wav")

SAIDA = Path(__file__).with_name("fallback_resposta.pcm")

# A BOX grava e reproduz a 16 kHz, mono, 16 bits.
TAXA = 16000
BYTES_POR_SEGUNDO = TAXA * 2


def ler_pcm(caminho):
    """
    Extrai o PCM do WAV pelo módulo wave, e não por um offset fixo.

    Um WAV não tem obrigatoriamente 44 bytes de cabeçalho — pode trazer
    chunks extra antes do 'data'. Assumir 44 funciona para este ficheiro
    e parte no seguinte.
    """
    try:
        with wave.open(str(caminho), "rb") as w:
            formato = (
                w.getnchannels(),
                w.getsampwidth(),
                w.getframerate(),
            )

            if formato != (1, 2, TAXA):
                print(
                    f"AVISO: {caminho.name} não é mono/16-bit/{TAXA} Hz — "
                    f"é {formato[0]} canal(is), "
                    f"{formato[1] * 8} bits, {formato[2]} Hz"
                )

            return w.readframes(w.getnframes())

    except (wave.Error, EOFError) as erro:
        print(f"FALHA: {caminho.name} não é um WAV válido — {erro}")
        print()
        print("Para o recriar a partir de uma gravação real:")
        print("    Copy-Item command.wav teste_comando.wav -Force")

        return None


def main():
    if not ENTRADA.exists():
        print(f"FALHA: não encontrei {ENTRADA.name}")
        print()
        print("Cria-o a partir de uma gravação real da BOX:")
        print("    Copy-Item command.wav teste_comando.wav")

        return 1

    pcm = ler_pcm(ENTRADA)

    if pcm is None:
        return 1

    print(
        f"Enviado : {len(pcm)} bytes "
        f"({len(pcm) / BYTES_POR_SEGUNDO:.2f} s de fala)"
    )

    try:
        resposta = requests.post(
            ENDPOINT,
            data=pcm,
            headers={
                "X-Response-Audio": "pcm16",
                "Content-Type": "application/octet-stream",
            },
            timeout=120,
        )

    except requests.RequestException as erro:
        print(f"FALHA: não consegui falar com o servidor — {erro}")
        print("       O app.py está a correr?")
        return 1

    print(f"HTTP    : {resposta.status_code}")

    if resposta.status_code != 200:
        print(f"FALHA: {resposta.text[:300]}")
        return 1

    audio = resposta.content

    print(
        f"Recebido: {len(audio)} bytes "
        f"({len(audio) / BYTES_POR_SEGUNDO:.2f} s de resposta)"
    )

    if not audio:
        print(
            "FALHA: zero bytes. É exactamente assim que o B2 se "
            "manifestava — a excepção morria dentro do gerador e o "
            "Flask fechava a resposta vazia."
        )
        return 1

    SAIDA.write_bytes(audio)

    print(f"Gravado : {SAIDA.name}")
    print()
    print("PASSA. Confirma no log do servidor que aparece '[LIVE] Tu: ...'")
    print("— é a linha que o B2 impedia de ser impressa.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
