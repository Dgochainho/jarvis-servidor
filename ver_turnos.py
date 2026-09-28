"""
Resumo do registo de turnos.

    python ver_turnos.py              resumo de tudo
    python ver_turnos.py 20           só os últimos 20 turnos
    python ver_turnos.py --lista      lista turno a turno

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

        for turno in fantasma[-3:]:
            resposta = (turno.get("dito") or "")[:60]
            print(f"    {turno['ts']}  jarvis: {resposta}")

        if fantasma:
            print(
                "  -> O VAD abriu um turno sem ninguém falar. "
                "É a Fase 3.2."
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

        print(
            f"{turno['ts']}  [{marca}] "
            f"{turno.get('conversa', ''):<8} "
            f"t{turno.get('turno', '?')}  "
            f"{turno.get('resultado', '?'):<10} "
            f"1.º áudio {formatar(turno.get('t_primeiro_audio'))}"
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

    turnos = ler_turnos()

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
