<#
    Objetivo del acceso directo del escritorio.

    Espera a que el servicio de la aplicación esté disponible y abre el
    programa en una ventana de Edge (modo aplicación, sin barra del navegador).
    Sin consolas: el acceso directo lo lanza con -WindowStyle Hidden.
#>
$ErrorActionPreference = 'SilentlyContinue'

$dataDir = Join-Path $env:ProgramData 'EntreRamblas'
$port = 8069
$config = Join-Path $dataDir 'odoo.local'
if (Test-Path -LiteralPath $config) {
    foreach ($line in Get-Content -LiteralPath $config) {
        if ($line -match '^\s*http_port\s*=\s*(\d+)') { $port = [int]$Matches[1] }
    }
}
$url = "http://127.0.0.1:$port/web/login"

# Arranca el servicio si estuviera parado (no requiere elevación para Start si
# el usuario tiene permiso; si no, simplemente esperamos a que arranque solo).
$svc = Get-Service -Name 'EntreRamblasOdoo' -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -ne 'Running') { Start-Service -Name 'EntreRamblasOdoo' -ErrorAction SilentlyContinue }

# Espera hasta 60 s a que responda.
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -ge 200) { $ok = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}

$edge = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe')
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

$profileDir = Join-Path $env:LOCALAPPDATA 'EntreRamblas\edge'
if ($edge) {
    Start-Process -FilePath $edge -ArgumentList @(
        "--app=$url", "--user-data-dir=`"$profileDir`"", '--no-first-run', '--no-default-browser-check'
    )
} else {
    Start-Process $url
}

if (-not $ok) {
    Start-Sleep -Seconds 1
    [System.Windows.Forms.MessageBox]::Show(
        'El programa está arrancando. Si no aparece en un minuto, reinicia el equipo.',
        'Entre Ramblas') | Out-Null
}
