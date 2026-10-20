import colorsys
import io
import struct
import time

import requests
from PIL import Image


# Fase 8.a — presença mínima para uma cor poder ser o realce.
#
# É o único número inventado deste módulo, e é um primeiro palpite: existe
# para um pixel perdido de néon não ser eleito cor da divisão. Quem quiser
# a cor mais viva da capa sem condição nenhuma tem-na em `mais_viva`, com o
# peso ao lado para ver o que ela representa.
#
# Rever quando houver capas reais que cheguem para julgar. A Fase 4 já
# custou um documento inteiro por se ter escolhido um limiar com dois casos.
PRESENCA_MINIMA_REALCE = 0.05


class CoverService:

    def __init__(self):
        self.cached_url = None
        self.cached_size = None
        self.cached_rgb565 = None

        # A paleta tem cache própria, só por URL: não depende do tamanho
        # para que a capa foi redimensionada.
        self.cached_paleta_url = None
        self.cached_paleta = None

        # Medido em 2026-09-23: 40 KB do CDN demoravam 1,31 s, o que dá
        # 31 KB/s — lento de mais para ser transferência. O suspeito é o
        # custo de abrir ligação: cada requests.get() avulso faz TCP e TLS
        # de raiz com o i.scdn.co.
        #
        # Uma Session reutiliza essa ligação entre capas. Previsão: a
        # primeira capa depois do arranque continua lenta, as seguintes
        # ficam bastante mais rápidas. Se não for isso que acontece, a
        # hipótese está errada e o tempo é mesmo transferência.
        self._session = requests.Session()


    def get_rgb565(
        self,
        image_url,
        width=120,
        height=120,
    ):
        if not image_url:
            return None

        requested_size = (
            width,
            height,
        )

        # Se for a mesma capa e o mesmo tamanho,
        # reutilizamos o resultado.
        if (
            image_url == self.cached_url
            and requested_size == self.cached_size
            and self.cached_rgb565 is not None
        ):
            return self.cached_rgb565


        # As duas metades deste método custam, juntas, entre 1,1 e 1,9 s.
        # Ainda não sabemos qual delas domina — e optimizar sem saber foi
        # o erro que já se cometeu uma vez nesta investigação.
        download_started = time.perf_counter()

        response = self._session.get(
            image_url,
            timeout=10,
        )

        response.raise_for_status()

        download_seconds = (
            time.perf_counter() - download_started
        )

        convert_started = time.perf_counter()

        image = Image.open(
            io.BytesIO(
                response.content
            )
        )

        # Confirma qual das versões do Spotify foi de facto descarregada.
        # O selector em spotify_client escolhe a mais pequena que chegue
        # para 120 px; isto verifica que escolheu mesmo.
        source_width, source_height = image.size

        image = image.convert("RGB")

        image = image.resize(
            requested_size,
            Image.Resampling.LANCZOS,
        )


        rgb565_data = bytearray()


        for red, green, blue in image.getdata():

            rgb565 = (
                ((red & 0xF8) << 8)
                |
                ((green & 0xFC) << 3)
                |
                (blue >> 3)
            )

            # ESP32 é little-endian.
            rgb565_data.extend(
                struct.pack(
                    "<H",
                    rgb565
                )
            )


        result = bytes(
            rgb565_data
        )

        convert_seconds = (
            time.perf_counter() - convert_started
        )

        # Fase 8.a — a paleta sai de borla daqui, porque a imagem já está
        # descodificada e redimensionada.
        #
        # Deliberadamente DEPOIS de `convert_seconds` ser fechado: este
        # trabalho não entra em nenhuma das duas medições, que são
        # comparáveis com as de Setembro e assim continuam.
        self.cached_paleta = self._extrair_paleta(image)
        self.cached_paleta_url = image_url

        print(
            f"[PERF]   -> download CDN:   {download_seconds:.2f} s "
            f"({len(response.content)} bytes, "
            f"{source_width}x{source_height} px)"
        )
        print(
            f"[PERF]   -> PIL + RGB565:   {convert_seconds:.2f} s"
        )


        self.cached_url = image_url
        self.cached_size = requested_size
        self.cached_rgb565 = result


        return result


    # -----------------------------------------------------------------
    # Fase 8.a — paleta de cor
    # -----------------------------------------------------------------

    @staticmethod
    def _vivacidade(rgb):
        """
        Quão "a cor" uma cor é: saturação vezes valor, em HSV.

        Um cinzento dá 0 por não ter saturação; um castanho escuro dá
        pouco por não ter valor; um encarnado vivo dá perto de 1.
        """
        vermelho, verde, azul = [canal / 255.0 for canal in rgb]

        _, saturacao, valor = colorsys.rgb_to_hsv(
            vermelho,
            verde,
            azul,
        )

        return saturacao * valor


    def _extrair_paleta(self, imagem, cores=8):
        """
        Paleta a partir de uma imagem PIL já em RGB.

        Não toma decisões estéticas. Devolve o que lá está e deixa quem
        acende os LEDs escolher:

        - `dominante`  — a cor mais comum. Numa capa preta é preto, e isso
                         é a verdade sobre a capa, não um defeito.
        - `realce`     — a mais viva de entre as que têm presença real.
        - `mais_viva`  — a mais viva da paleta, sem condição, com o peso
                         ao lado para se ver o que representa.
        """
        pequena = imagem.resize(
            (64, 64),
            Image.Resampling.BILINEAR,
        )

        quantizada = pequena.quantize(
            colors=cores,
            method=Image.Quantize.MEDIANCUT,
        )

        tabela = quantizada.getpalette() or []
        contagens = quantizada.getcolors() or []

        total = sum(
            contagem for contagem, _ in contagens
        ) or 1

        entradas = []

        for contagem, indice in contagens:

            rgb = [
                tabela[indice * 3 + desvio]
                for desvio in range(3)
            ]

            entradas.append({
                "hex": "#%02x%02x%02x" % tuple(rgb),
                "rgb": rgb,
                "peso": round(contagem / total, 4),
                "vivacidade": round(self._vivacidade(rgb), 4),
            })

        entradas.sort(
            key=lambda entrada: entrada["peso"],
            reverse=True,
        )

        if not entradas:
            return None

        com_presenca = [
            entrada
            for entrada in entradas
            if entrada["peso"] >= PRESENCA_MINIMA_REALCE
        ]

        realce = max(
            com_presenca or entradas,
            key=lambda entrada: entrada["vivacidade"],
        )

        mais_viva = max(
            entradas,
            key=lambda entrada: entrada["vivacidade"],
        )

        return {
            "dominante": entradas[0],
            "realce": realce,
            "mais_viva": mais_viva,
            "paleta": entradas,
        }


    def get_paleta(self, image_url):
        """
        Paleta da capa, com cache por URL.

        Normalmente já está calculada: o `get_rgb565` calcula-a de borla
        quando a BOX pede a capa. Só descarrega aqui se este caminho
        correr primeiro — e a Session é a mesma, portanto reaproveita a
        ligação ao CDN.
        """
        if not image_url:
            return None

        if (
            image_url == self.cached_paleta_url
            and self.cached_paleta is not None
        ):
            return self.cached_paleta

        response = self._session.get(
            image_url,
            timeout=10,
        )

        response.raise_for_status()

        imagem = Image.open(
            io.BytesIO(
                response.content
            )
        ).convert("RGB")

        self.cached_paleta = self._extrair_paleta(imagem)
        self.cached_paleta_url = image_url

        return self.cached_paleta
