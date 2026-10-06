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

# Isto não afecta a tua consola, só a execução deste script.
#
# Existe por causa de 2026-10-04. O arranque rebentava com:
#
#     & python -u app.py *> $log
#     NativeCommandError: WARNING: This is a development server...
#
# O que o PowerShell estava a chamar "erro" era o aviso normal do Flask,
# escrito no stderr. Quando o stderr de um programa nativo é redirigido,
# o PowerShell embrulha cada linha num ErrorRecord — e com o
# $ErrorActionPreference em "Stop" (vem do perfil, não daqui) o primeiro
# ErrorRecord mata o script, e com ele o servidor.
$ErrorActionPreference = "Continue"

# O Python no Windows escreve para um ficheiro na codificação da região
# (cp1252), e não em UTF-8. Duas consequências, ambas já vistas:
#
#   - no log, "Sessão" aparece como "Sess?o" e "acções" como "ac??es";
#   - a 2026-10-04 uma transcrição com caracteres devanágari rebentou um
#     turno inteiro com UnicodeEncodeError, porque simplesmente não há
#     maneira de os escrever em cp1252.
#
# O segundo caso é o que interessa: não era cosmético, era uma falha.
# Com isto, o Python escreve UTF-8 e deixa de haver caracteres que o
# matem. O cmd.exe herda esta variável.
$env:PYTHONIOENCODING = "utf-8"

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
Write-Host "  Get-Content log-servidor.txt -Wait -Tail 20 -Encoding UTF8" -ForegroundColor DarkGray
Write-Host "  (numa janela NOVA -- uma que ja estivesse aberta continua" -ForegroundColor DarkGray
Write-Host "   a descodificar o ficheiro antigo e mostra lixo)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Ctrl+C para parar." -ForegroundColor DarkGray
Write-Host ""

# Quem faz a redirecção é o cmd.exe, não o PowerShell.
#
# A linha de cima já evita que o aviso do Flask mate o script, mas
# enquanto for o PowerShell a tratar do stderr continuam a ir para o
# ficheiro linhas de ErrorRecord embrulhadas em ruído — com o texto
# original partido em pedaços e um "NativeCommandError" pelo meio. Isso
# estraga o log, e o log é o nosso único instrumento.
#
# Com o cmd.exe a juntar os dois fluxos (2>&1), o PowerShell nunca lhes
# toca: o ficheiro fica com o que o Python escreveu, por ordem e nada
# mais. O Ctrl+C continua a funcionar.
& cmd.exe /c "python -u app.py > ""$log"" 2>&1"
