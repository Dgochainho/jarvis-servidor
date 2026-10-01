"""
Resumo do registo de turnos.

    python ver_turnos.py                    resumo de tudo
    python ver_turnos.py 20                 só os últimos 20 turnos
    python ver_turnos.py --desde 2026-09-30 só a partir dessa data
    python ver_turnos.py --lista            lista turno a turno

O --desde existe porque a pergunta que aparece sempre é "isto melhorou
depois da alteração de ontem?", e um resumo que mistura antes e depois
não responde a isso. Misturar diluiu durante dois dias um problema que
tinha desaparecido.

Existe porque ter os dados e não os olhar dá no mesmo. Responde de uma vez
às perguntas que estavam em aberto:

    - O fallback HTTP é usado em campo?            (decisão D1)
    - A latência piorou desde a última medição?
    - Quantos turnos acabam em erro, e em quê?
    - Houve bloqueio no transporte?                (bug B4)
"""

import sys
from statistics import median

from turn_log import ler_turnos


def mediana(valores):
    limpos = [v for v in valores if v is not None]

    if not limpos:
        return None

    return median(limpos)


def formatar(valor, sufixo=" s"):
    if valor is None:
        return "—"

    return f"{valor:.2f}{sufixo}"


def resumo(turnos):
    total = len(turnos)

    if total == 0:
        print("Registo vazio. Ainda não há turnos.")
        return

    print(f"Turnos registados: {total}")
    print(f"Período: {turnos[0]['ts']}  ->  {turnos[-1]['ts']}")
    print()

    # -----------------------------------------------------------------
    # RESULTADOS
    # -----------------------------------------------------------------
    contagem = {}

    for turno in turnos:
        chave = turno.get("resultado", "?")
        contagem[chave] = contagem.get(chave, 0) + 1

    print("Resultado")

    for chave in sorted(contagem, key=lambda k: -contagem[k]):
        n = contagem[chave]
        print(f"  {chave:<12} {n:>4}   ({100 * n / total:.0f}%)")

    print()

    # -----------------------------------------------------------------
    # LATÊNCIA — separada por 1.º turno e seguintes
    # -----------------------------------------------------------------
    #
    # Separar isto não é cosmético: o 1.º turno paga a abertura da sessão
    # Gemini e os seguintes reutilizam-na. Misturá-los produz uma mediana
    # que não descreve nenhum dos dois casos, e esconderia uma regressão
    # na reutilização da sessão — que vale ~3 s por turno.
    primeiros = [
        t for t in turnos
        if t.get("turno") == 1 and not t.get("fallback")
    ]

    seguintes = [
        t for t in turnos
        if (t.get("turno") or 0) > 1 and not t.get("fallback")
    ]

    # `total` é o que o utilizador sente. `modelo` desconta o tempo passado
    # dentro das ferramentas, que acontece antes de o Gemini começar a
    # falar e que não é latência do modelo. Sem separar os dois, um turno
    # com "passa esta" e outro com "conta-me uma piada" não são
    # comparáveis — e nada no número o dizia.
    print("Latência até ao primeiro áudio (mediana)")
    print(f"  {'':<26} {'total':>8} {'modelo':>9}    n")

    for etiqueta, grupo in (
        ("1.º turno (abre sessão)", primeiros),
        ("follow-up (reutiliza)", seguintes),
    ):
        valores = [
            t.get("t_primeiro_audio")
            for t in grupo
            if t.get("t_primeiro_audio") is not None
        ]

        modelo = [
            t.get("t_modelo")
            for t in grupo
            if t.get("t_modelo") is not None
        ]

        # n conta as MEDIÇÕES, não os turnos: um turno cancelado ou com
        # erro nunca chegou a produzir áudio e não entra na conta. Contar
        # turnos aqui dava um n inflacionado que sugeria mais confiança
        # do que a mediana merece.
        print(
            f"  {etiqueta:<26} "
            f"{formatar(mediana(valores)):>8} "
            f"{formatar(mediana(modelo)):>9}    {len(valores)}"
        )

    com_ferramenta = [
        t.get("t_ferramentas")
        for t in turnos
        if t.get("t_ferramentas")
    ]

    if com_ferramenta:
        print(
            f"\n  Dos quais, dentro das ferramentas: "
            f"{formatar(mediana(com_ferramenta))} "
            f"(mediana de {len(com_ferramenta)} turnos)"
        )

    if len(turnos) < 10:
        print(
            f"\n  ⚠ Só {len(turnos)} turnos no registo. "
            "Medianas com n baixo não sustentam conclusões."
        )

    print()

    # -----------------------------------------------------------------
    # A CAUDA — o que a mediana esconde
    # -----------------------------------------------------------------
    #
    # Uma mediana de 1,10 s convive perfeitamente com um turno de 26 s.
    # Quem espera 26 segundos não se consola com a mediana, e um sistema
    # que falha assim de vez em quando é pior de usar do que um que seja
    # lento de forma previsível.
    #
    # Por isso a cauda tem secção própria, com a decomposição: um turno
    # lento por causa do Spotify e um turno lento por causa do Gemini são
    # problemas diferentes e têm correcções diferentes.
    LIMITE_LENTO = 5.0

    lentos = sorted(
        (
            t for t in turnos
            if (t.get("t_primeiro_audio") or 0) >= LIMITE_LENTO
        ),
        key=lambda t: -t["t_primeiro_audio"],
    )

    medidos = [
        t for t in turnos
        if t.get("t_primeiro_audio") is not None
    ]

    print(f"Turnos lentos (≥ {LIMITE_LENTO:.0f} s até ao primeiro áudio)")

    if not lentos:
        print("  nenhum")
    else:
        print(
            f"  {len(lentos)} de {len(medidos)} medidos "
            f"({100 * len(lentos) / len(medidos):.0f}%)"
        )
        print()
        print(
            f"  {'quando':<22} {'total':>7} {'ferram.':>8} "
            f"{'modelo':>7}  turno"
        )

        for t in lentos[:8]:
            print(
                f"  {t['ts'][:19]:<22} "
                f"{formatar(t.get('t_primeiro_audio')):>7} "
                f"{formatar(t.get('t_ferramentas')):>8} "
                f"{formatar(t.get('t_modelo')):>7}  "
                f"t{t.get('turno', '?')}"
            )

        print()
        print(
            "  Se 'modelo' é grande e 'ferram.' é pequeno, a demora foi\n"
            "  do Gemini ou da ligação a ele. Se for ao contrário, foi a\n"
            "  API do Spotify."
        )

    print()

    # -----------------------------------------------------------------
    # TURNOS FANTASMA — a Fase 3.2
    # -----------------------------------------------------------------
    #
    # Um turno que correu até ao fim mas em que o Gemini não transcreveu
    # nada é um turno que ninguém iniciou: o VAD disparou com ruído, ou
    # com a própria voz do Jarvis (não há AEC). Durante o follow-up o
    # WakeNet está desligado, por isso não há nada a filtrar isto.
    #
    # Até agora era uma preocupação teórica — F3 no inventário. Isto
    # transforma-a num número.
    def sem_fala(turno):
        if turno.get("resultado") != "done":
            return False

        if "ouvido_n" in turno:          # transcrições desligadas (D6)
            return turno["ouvido_n"] == 0

        return not (turno.get("ouvido") or "").strip()

    concluidos = [t for t in turnos if t.get("resultado") == "done"]
    fantasma = [t for t in concluidos if sem_fala(t)]

    # Fase 1.4: quantas conversas acabaram porque o utilizador disse que
    # acabou, em vez de expirarem com 30 s de microfone aberto. É a
    # contrapartida directa da secção acima.
    fechos = [t for t in turnos if t.get("fecho_por_voz")]

    if fechos:
        print("Fechos de conversa por voz")
        print(f"  {len(fechos)} conversa(s) terminada(s) a pedido")
        print()

    if concluidos:
        print("Turnos sem fala reconhecida")
        print(
            f"  {len(fantasma)} de {len(concluidos)} concluídos "
            f"({100 * len(fantasma) / len(concluidos):.0f}%)"
        )

        if fantasma:
            # Quanto tempo depois do turno anterior é que cada um abriu.
            #
            # É este número que distingue as hipóteses, e só aqui faz
            # sentido: na BOX, a linha "FOLLOW-UP DETETADO" dispara em
            # TODOS os follow-ups, incluindo os legítimos. Só o servidor
            # sabe quais é que ninguém iniciou, porque só ele vê a
            # transcrição.
            print()
            print(f"    {'quando':<22} {'após o anterior':>16}")

            for turno in fantasma[-6:]:
                print(
                    f"    {turno['ts'][:19]:<22} "
                    f"{formatar(turno.get('t_desde_anterior')):>16}"
                )

            atrasos = [
                t.get("t_desde_anterior")
                for t in fantasma
                if t.get("t_desde_anterior") is not None
            ]

            antigos = len(fantasma) - len(atrasos)

            if antigos:
                plural = "são anteriores" if antigos > 1 else "é anterior"
                print()
                print(
                    f"    ({antigos} {plural} a esta medição "
                    "e aparece(m) como —)"
                )

            if atrasos:
                m = mediana(atrasos)
                print()
                print(
                    f"    mediana: {formatar(m)}   "
                    f"(de {len(atrasos)} medido(s))"
                )

                if m is not None and m < 2.0:
                    print(
                        "    -> Logo a seguir à resposta. Compatível com a\n"
                        "       BOX ouvir-se a si própria (F2, sem AEC)."
                    )
                else:
                    print(
                        "    -> Vários segundos depois. NÃO é a cauda da\n"
                        "       própria voz; é som externo (F3)."
                    )

        print()

    # -----------------------------------------------------------------
    # FALLBACK — a decisão D1
    # -----------------------------------------------------------------
    fallbacks = [t for t in turnos if t.get("fallback")]

    com_sucesso = [
        t for t in fallbacks
        if t.get("resultado") == "done"
    ]

    print("Fallback HTTP")
    print(f"  usado             {len(fallbacks)} vez(es)")
    print(f"  com sucesso       {len(com_sucesso)}")

    if not fallbacks:
        print(
            "  -> Nunca usado. Se isto se mantiver ao fim de ~10 corridas\n"
            "     do guião, o D1 resolve-se removendo-o."
        )

    print()

    # -----------------------------------------------------------------
    # TRANSPORTE — o bug B4
    # -----------------------------------------------------------------
    suspeitos = [t for t in turnos if t.get("transporte_suspeito")]

    print("Transporte")
    print(
        f"  turnos em que a recepção demorou muito mais do que a fala: "
        f"{len(suspeitos)}"
    )

    for turno in suspeitos[-3:]:
        print(
            f"    {turno['ts']}  fala {formatar(turno.get('t_fala'))}"
            f"  recepção {formatar(turno.get('t_receber'))}"
        )

    if suspeitos:
        print("  -> É a assinatura do B4 (bloqueio no envio de PCM).")

    print()

    # -----------------------------------------------------------------
    # FERRAMENTAS
    # -----------------------------------------------------------------
    usos = {}

    for turno in turnos:
        for ferramenta in turno.get("ferramentas") or []:
            nome = ferramenta.get("nome", "?")
            acao = (ferramenta.get("args") or {}).get("action")
            chave = f"{nome}:{acao}" if acao else nome

            certo, errado = usos.get(chave, (0, 0))

            if ferramenta.get("ok"):
                usos[chave] = (certo + 1, errado)
            else:
                usos[chave] = (certo, errado + 1)

    if usos:
        print("Ferramentas")

        for chave in sorted(usos, key=lambda k: -sum(usos[k])):
            certo, errado = usos[chave]
            aviso = f"   {errado} falha(s)" if errado else ""
            print(f"  {chave:<28} {certo + errado:>4}{aviso}")

        print()

    # -----------------------------------------------------------------
    # ERROS
    # -----------------------------------------------------------------
    erros = [t for t in turnos if t.get("erro")]

    if erros:
        print(f"Erros ({len(erros)})")

        for turno in erros[-5:]:
            print(f"  {turno['ts']}  {turno['erro']}")

        print()


def listar(turnos):
    for turno in turnos:
        marca = "HTTP" if turno.get("fallback") else "WS"

        detalhe = ""

        # Só decompõe quando há alguma coisa para decompor. Numa linha
        # de 1,0 s a decomposição é ruído; numa de 17 s é a resposta.
        if (turno.get("t_ferramentas") or 0) > 0.05:
            detalhe = (
                f"  (ferram. {formatar(turno['t_ferramentas'])}"
                f" + modelo {formatar(turno.get('t_modelo'))})"
            )

        print(
            f"{turno['ts']}  [{marca}] "
            f"{turno.get('conversa', ''):<8} "
            f"t{turno.get('turno', '?')}  "
            f"{turno.get('resultado', '?'):<10} "
            f"1.º áudio {formatar(turno.get('t_primeiro_audio'))}"
            f"{detalhe}"
        )

        if turno.get("ouvido"):
            print(f"    tu:     {turno['ouvido']}")

        if turno.get("dito"):
            print(f"    jarvis: {turno['dito']}")

        for ferramenta in turno.get("ferramentas") or []:
            estado = "ok" if ferramenta.get("ok") else "FALHOU"
            print(
                f"    tool:   {ferramenta.get('nome')}"
                f"({ferramenta.get('args')}) -> {estado}"
            )

        if turno.get("erro"):
            print(f"    erro:   {turno['erro']}")


def main():
    argumentos = sys.argv[1:]

    modo_lista = "--lista" in argumentos
    argumentos = [a for a in argumentos if a != "--lista"]

    desde = None

    if "--desde" in argumentos:
        i = argumentos.index("--desde")

        if i + 1 >= len(argumentos):
            print("Falta a data. Exemplo: --desde 2026-09-30")
            return 1

        desde = argumentos[i + 1]
        del argumentos[i:i + 2]

    turnos = ler_turnos()

    if desde:
        antes = len(turnos)
        turnos = [t for t in turnos if t.get("ts", "") >= desde]

        print(
            f"A partir de {desde}: {len(turnos)} turnos "
            f"({antes - len(turnos)} anteriores ignorados)"
        )
        print()

    if argumentos:
        try:
            turnos = turnos[-int(argumentos[0]):]

        except ValueError:
            print(f"Argumento não numérico: {argumentos[0]}")
            return 1

    if modo_lista:
        listar(turnos)
    else:
        resumo(turnos)

    return 0


if __name__ == "__main__":
    sys.exit(main())
