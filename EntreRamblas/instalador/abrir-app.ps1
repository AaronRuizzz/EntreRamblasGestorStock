<#
    Objetivo del acceso directo del escritorio.

    Espera a que el servicio de la aplicación esté disponible y abre el
    programa en una ventana de Edge (modo aplicación, sin barra del navegador).
    Sin consolas: el acceso directo lo lanza con -WindowStyle Hidden.

    Al entrar, si hay publicada una versión firmada más nueva, se instala
    ANTES de abrir la ventana (ACTUALIZACIONES.md, «Al entrar al programa»).
    La app decide al momento (/mgs/actualizacion/al-entrar) y la instala el
    servicio EntreRamblasActualizador; aquí solo se espera, con una ventana
    que lo explica, leyendo <data_dir>\actualizador\estado.json.

    Guardado en UTF-8 CON BOM: powershell.exe 5.1 lee un .ps1 sin BOM como
    ANSI y los acentos de los avisos salían rotos.
#>
$ErrorActionPreference = 'SilentlyContinue'

# Necesario para los MessageBox de más abajo: en PowerShell 5.1 este
# ensamblado no está cargado por defecto (hallazgo de la revisión de
# correcciones de ventas) y la llamada podía fallar en silencio, sin que se
# viera ningún aviso cuando algo iba mal.
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$appTitle = 'Gestor Stock Clavel Y Azahar'
$dataDir = Join-Path $env:ProgramData 'EntreRamblas'
$runtimeDir = Join-Path $dataDir 'data'
$port = 8069
$config = Join-Path $dataDir 'odoo.local'
if (Test-Path -LiteralPath $config) {
    foreach ($line in Get-Content -LiteralPath $config) {
        if ($line -match '^\s*http_port\s*=\s*(\d+)') { $port = [int]$Matches[1] }
        if ($line -match '^\s*data_dir\s*=\s*(.+?)\s*$') { $runtimeDir = $Matches[1] }
    }
}
$url = "http://127.0.0.1:$port/web/login"
$updateDir = Join-Path $runtimeDir 'actualizador'

function Test-App {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        return ($r.StatusCode -ge 200)
    } catch { return $false }
}

function Wait-App([int]$seconds) {
    for ($i = 0; $i -lt $seconds; $i++) {
        if (Test-App) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Read-UpdateState {
    try {
        $raw = Get-Content -LiteralPath (Join-Path $updateDir 'estado.json') -Raw -Encoding UTF8
        if ($raw) { return ($raw | ConvertFrom-Json) }
    } catch { }
    return $null
}

# Ventana «Actualizando...» mientras el servicio aplicador trabaja. Devuelve
# ok | fallo | aplazada | sin-instalar | tiempo | saltado.
function Wait-Update([string]$version) {
    [System.Windows.Forms.Application]::EnableVisualStyles()
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $appTitle
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true
    $form.ClientSize = New-Object System.Drawing.Size(460, 185)
    $form.Font = New-Object System.Drawing.Font('Segoe UI', 10)

    $title = New-Object System.Windows.Forms.Label
    $title.Text = "Actualizando el programa a la versión $version"
    $title.Font = New-Object System.Drawing.Font('Segoe UI', 11, [System.Drawing.FontStyle]::Bold)
    $title.SetBounds(20, 15, 420, 25)
    $detail = New-Object System.Windows.Forms.Label
    $detail.Text = 'Comprobando...'
    $detail.SetBounds(20, 45, 420, 40)
    $bar = New-Object System.Windows.Forms.ProgressBar
    $bar.Style = 'Marquee'
    $bar.SetBounds(20, 90, 420, 18)
    $note = New-Object System.Windows.Forms.Label
    $note.Text = 'No apagues el equipo. El programa se abrirá solo al terminar.'
    $note.SetBounds(20, 115, 420, 22)
    $skip = New-Object System.Windows.Forms.Button
    $skip.Text = 'Abrir sin esperar'
    $skip.SetBounds(300, 143, 140, 30)
    $form.Controls.AddRange(@($title, $detail, $bar, $note, $skip))

    $script:updResult = 'tiempo'
    $script:updStart = Get-Date
    $script:updIdleSince = $null
    $script:updDoneSince = $null

    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = 2000
    $timer.Add_Tick({
        $st = Read-UpdateState
        $fase = ''; $paso = ''; $msg = ''
        if ($st) { $fase = [string]$st.fase; $paso = [string]$st.paso; $msg = [string]$st.mensaje }

        $detail.Text = switch ($fase) {
            'disponible' { 'Descargando la actualización...' }
            'preparado'  { 'Preparando la instalación...' }
            'aplicando'  {
                switch ($paso) {
                    'mantenimiento' { 'Esperando a que terminen las operaciones en curso...' }
                    'copia'         { 'Haciendo una copia de seguridad...' }
                    'instalando'    { 'Instalando la nueva versión...' }
                    'migrando'      { 'Actualizando los datos...' }
                    'comprobando'   { 'Comprobando que todo funciona...' }
                    default         { 'Instalando...' }
                }
            }
            'hecho'      { 'Actualización instalada. Abriendo el programa...' }
            'fallo'      { 'Recuperando la versión anterior...' }
            default      { 'Comprobando...' }
        }

        # ¿Sigue habiendo alguien trabajando en la actualización?
        $busy = ($fase -eq 'aplicando') -or (Test-Path -LiteralPath (Join-Path $updateDir 'auto.lock'))
        $svc = Get-Service -Name 'EntreRamblasActualizador' -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -ne 'Stopped') { $busy = $true }

        $done = $null
        if ($fase -eq 'hecho' -or $fase -eq 'al-dia') { $done = 'ok' }
        elseif ($fase -eq 'fallo') { $done = 'fallo' }
        elseif ($fase -eq 'preparado' -and $msg -like 'Aplazada*') { $done = 'aplazada' }
        elseif ($busy) { $script:updIdleSince = $null }
        elseif (-not $script:updIdleSince) { $script:updIdleSince = Get-Date }
        elseif (((Get-Date) - $script:updIdleSince).TotalSeconds -gt 60) { $done = 'sin-instalar' }

        if ($done) {
            # Terminada (o revertida): se abre cuando la app vuelve a
            # responder; si no vuelve en 3 minutos, se deja de esperar y el
            # final del script avisa de que el servicio no arranca.
            if (-not $script:updDoneSince) { $script:updDoneSince = Get-Date }
            if ((Test-App) -or ((Get-Date) - $script:updDoneSince).TotalMinutes -gt 3) {
                $script:updResult = $done
                $timer.Stop(); $form.Close()
            }
        } elseif (((Get-Date) - $script:updStart).TotalMinutes -gt 45) {
            $script:updResult = 'tiempo'
            $timer.Stop(); $form.Close()
        }
    })
    $skip.Add_Click({ $script:updResult = 'saltado'; $timer.Stop(); $form.Close() })
    $form.Add_Shown({ $form.Activate(); $timer.Start() })
    [void]$form.ShowDialog()
    $timer.Dispose(); $form.Dispose()
    return $script:updResult
}

# Arranca el servicio si estuviera parado (no requiere elevación para Start si
# el usuario tiene permiso; si no, simplemente esperamos a que arranque solo).
$svc = Get-Service -Name 'EntreRamblasOdoo' -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -ne 'Running') { Start-Service -Name 'EntreRamblasOdoo' -ErrorAction SilentlyContinue }

# Espera hasta 60 s a que responda.
$ok = Wait-App 60

# Al entrar: ¿hay una versión nueva publicada? Si la app no tiene todavía
# esta ruta (versión anterior) o no contesta, se abre como siempre.
$update = $null
if ($ok) {
    try {
        $answer = Invoke-RestMethod -Uri "http://127.0.0.1:$port/mgs/actualizacion/al-entrar" `
            -Method Post -TimeoutSec 75
        if ($answer -and $answer.actualizando) { $update = Wait-Update ([string]$answer.version) }
    } catch { }
    if ($update) { $ok = Wait-App 120 }
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
        $appTitle) | Out-Null
    Start-Process $url
}

if ($ok -and $update -eq 'fallo') {
    [System.Windows.Forms.MessageBox]::Show(
        'No se ha podido instalar la actualización. Se ha recuperado la versión ' +
        'anterior y puedes trabajar con normalidad.',
        $appTitle) | Out-Null
} elseif ($ok -and $update -eq 'aplazada') {
    [System.Windows.Forms.MessageBox]::Show(
        'Hay una caja abierta o una venta sin terminar. La actualización se ' +
        'instalará sola en cuanto se cierre la caja.',
        $appTitle) | Out-Null
} elseif ($ok -and ($update -eq 'tiempo' -or $update -eq 'saltado')) {
    [System.Windows.Forms.MessageBox]::Show(
        'La actualización sigue en marcha. Si el programa se cierra un momento, ' +
        'vuelve a abrirlo en unos minutos.',
        $appTitle) | Out-Null
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
            $appTitle) | Out-Null
    } elseif ($svc.Status -ne 'Running') {
        [System.Windows.Forms.MessageBox]::Show(
            'El servicio de la aplicación no ha arrancado. Reinicia el equipo; ' +
            'si el problema continúa, contacta con soporte.',
            $appTitle) | Out-Null
    } else {
        [System.Windows.Forms.MessageBox]::Show(
            'El programa está arrancando. Si no aparece en un minuto, reinicia el equipo.',
            $appTitle) | Out-Null
    }
}
