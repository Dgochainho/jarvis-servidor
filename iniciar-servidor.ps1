# Arranca o Spotify Service da maneira correcta.
#
# .\iniciar-servidor.ps1
#
# ---------------------------------------------------------------------
# PORQUE É QUE ISTO EXISTE
#
# Medido em 2026-09-30: com a saída a ir para o terminal, o processo
# bloqueia à espera que a consola aceite o texto. Enquanto está
# bloqueado ninguém lê o WebSocket da BOX, a janela TCP enche, e o envio
# de PCM na BOX estoira o timeout de 5 s:
#
#     transport_ws: Error transport_poll_write(0)
#     VOICE: Envio PCM bloqueado durante 5028 ms
#     VOICE: Nao foi possivel concluir a interacao de voz
#
# Da BOX isto parece rede má. Não é. É o servidor a parar.
#
# Com a saída em ficheiro: zero falhas, e o bloqueio máximo do event
# loop passou de mais de 5 s para 1,6 s numa única ocorrência.
#
# O -u é obrigatório: sem ele o Python guarda a saída em buffer quando
# não está a escrever para um terminal, e o ficheiro fica minutos para
# trás.
# ---------------------------------------------------------------------

$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $pasta

$log = Join-Path $pasta "log-servidor.txt"

# Guarda o log anterior em vez de o deitar fora. Uma sessão de testes
# que se perde é uma sessão de testes que se repete.
if (Test-Path $log) {
    $carimbo = (Get-Item $log).LastWriteTime.ToString("yyyyMMdd-HHmmss")
    Move-Item $log (Join-Path $pasta "log-servidor-$carimbo.txt") -Force
}

Write-Host ""
Write-Host "Servidor a arrancar. A saída vai para:" -ForegroundColor Cyan
Write-Host "  $log"
Write-Host ""
Write-Host "Esta janela fica vazia de propósito. Para acompanhar," -ForegroundColor DarkGray
Write-Host "abre outro separador e corre:" -ForegroundColor DarkGray
Write-Host "  Get-Content log-servidor.txt -Wait -Tail 20" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Ctrl+C para parar." -ForegroundColor DarkGray
Write-Host ""

& python -u app.py *> $log
