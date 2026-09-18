<#
    Objetivo del acceso directo del escritorio.

    Espera a que el servicio de la aplicación esté disponible y abre el
    programa en una ventana de Edge (modo aplicación, sin barra del navegador).
    Sin consolas: el acceso directo lo lanza con -WindowStyle Hidden.
#>
$ErrorActionPreference = 'SilentlyContinue'

# Necesario para los MessageBox de más abajo: en PowerShell 5.1 este
# ensamblado no está cargado por defecto (hallazgo de la revisión de
# correcciones de ventas) y la llamada podía fallar en silencio, sin que se
# viera ningún aviso cuando algo iba mal.
Add-Type -AssemblyName System.Windows.Forms

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
    [System.Windows.Forms.MessageBox]::Show(
        'No se ha encontrado Microsoft Edge instalado. Se abrirá con el navegador ' +
        'predeterminado; contacta con soporte si esto no es lo esperado.',
        'Gestor Stock Clavel Y Azahar') | Out-Null
    Start-Process $url
}

if (-not $ok) {
    Start-Sleep -Seconds 1
    # $svc puede estar desactualizado si Start-Service lo arrancó más
    # arriba: ServiceController no refresca Status solo, hay que volver a
    # consultarlo para no decir "no ha arrancado" de un servicio que sí lo
    # hizo (pero que, por lo que sea, no responde todavía por HTTP).
    $svc = Get-Service -Name 'EntreRamblasOdoo' -ErrorAction SilentlyContinue
    if (-not $svc) {
        [System.Windows.Forms.MessageBox]::Show(
            'El servicio de la aplicación no está instalado o no se encuentra. ' +
            'Reinicia el equipo; si el problema continúa, contacta con soporte.',
            'Gestor Stock Clavel Y Azahar') | Out-Null
    } elseif ($svc.Status -ne 'Running') {
        [System.Windows.Forms.MessageBox]::Show(
            'El servicio de la aplicación no ha arrancado. Reinicia el equipo; ' +
            'si el problema continúa, contacta con soporte.',
            'Gestor Stock Clavel Y Azahar') | Out-Null
    } else {
        [System.Windows.Forms.MessageBox]::Show(
            'El programa está arrancando. Si no aparece en un minuto, reinicia el equipo.',
            'Gestor Stock Clavel Y Azahar') | Out-Null
    }
}
