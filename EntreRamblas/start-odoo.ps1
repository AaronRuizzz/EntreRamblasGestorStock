# Arranca Odoo 18 con la configuracion local (odoo.conf)
# Uso:  .\start-odoo.ps1              -> arranca el servidor (http://localhost:8069)
#       .\start-odoo.ps1 -Update mi_gestor_stock   -> actualiza un modulo y arranca
#       .\start-odoo.ps1 -Init otro_modulo         -> instala un modulo nuevo y arranca
param(
    [string]$Update = "",
    [string]$Init = "",
    # Vacio: se toma db_name de la configuracion (fuente unica del nombre de
    # base, puerto y rutas). Solo si la configuracion no lo trae se usa el
    # valor por defecto historico del equipo de desarrollo.
    [ValidatePattern('^([a-z][a-z0-9_]{0,62})?$')][string]$Database = "",
    [string]$Config = (Join-Path $PSScriptRoot 'odoo.local'),
    [switch]$NoStart
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
$odooBin = Join-Path $PSScriptRoot "odoo\odoo-bin"
if ($Update -and $Init) { throw 'Usa una sola operación: Update o Init.' }
if ($NoStart -and -not ($Update -or $Init)) { throw 'NoStart requiere Update o Init.' }
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'No existe el archivo de configuración.' }
$Config = (Resolve-Path -LiteralPath $Config).Path
if (Test-Path -LiteralPath ($Config + '.pending')) { throw 'La instalación está incompleta. Consulta el registro antes de arrancar.' }

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "No se encuentra el entorno virtual: $python"
}

$configDbHost = "localhost"
$configDbPort = 5432
$configDbName = ""
foreach ($line in Get-Content -LiteralPath $Config) {
    if ($line -match '^\s*db_host\s*=\s*([^;#]+)') { $configDbHost = $Matches[1].Trim() }
    if ($line -match '^\s*db_port\s*=\s*(\d+)') { $configDbPort = [int]$Matches[1] }
    if ($line -match '^\s*db_name\s*=\s*([a-z][a-z0-9_]{0,62})') { $configDbName = $Matches[1] }
}
# El nombre de base sale de la configuracion; el parametro solo lo fuerza a mano.
if (-not $Database) { $Database = $configDbName }
if (-not $Database) { $Database = 'mi_base_stock' }  # ultimo recurso (equipo de desarrollo)

if (-not (Test-Path -LiteralPath $odooBin -PathType Leaf)) {
    throw "No se encuentra el código Odoo fijado por el proyecto en '$odooBin'."
}
# Integridad del motor Odoo: el commit fijado (odoo-revision.txt) y, más allá
# del identificador, que ningún fichero versionado del motor se haya modificado
# o añadido (un parche a mano sobre odoo/ rompería la igualdad entre equipos
# sin cambiar el commit). La ausencia de documentación, empaquetado o ficheros
# de datos de pruebas NO bloquea: no cambia cómo se ejecuta Odoo. Detalle y
# criterio en tools/verificar_motor.py.
$engineReport = (& $python (Join-Path $PSScriptRoot 'tools/verificar_motor.py')) -join "`n"
switch ($LASTEXITCODE) {
    0 { if ($engineReport) { Write-Output "Motor Odoo: $engineReport" } }
    2 { throw "El motor Odoo no está en la revisión fijada por el proyecto ($engineReport). Restáuralo desde un checkout limpio (odoo-revision.txt)." }
    3 { throw "El motor Odoo tiene ficheros versionados modificados o faltan ficheros de ejecución:`n$engineReport`nRestáuralo desde un checkout limpio antes de arrancar." }
    4 { throw "No se pudo verificar la integridad del motor Odoo: $engineReport" }
    default { throw "Verificación del motor Odoo: código $LASTEXITCODE. $engineReport" }
}

if (-not (Test-NetConnection -ComputerName $configDbHost -Port $configDbPort -InformationLevel Quiet)) {
    throw "PostgreSQL no responde en $configDbHost`:$configDbPort. Inicia el servicio PostgreSQL y vuelve a ejecutar este script."
}

# Asegura que wkhtmltopdf este en el PATH de este proceso (para informes PDF)
$wk = "C:\Program Files\wkhtmltopdf\bin"
$privateWk = Join-Path (Split-Path $Config -Parent) 'tools/wkhtmltox/bin'
if (Test-Path -LiteralPath (Join-Path $privateWk 'wkhtmltopdf.exe')) { $wk = $privateWk }
if (Test-Path -LiteralPath (Join-Path $wk 'wkhtmltopdf.exe')) { $env:Path = "$wk;$env:Path" }

# -d <BD> es OBLIGATORIO en los comandos -i / -u: el dbfilter de odoo.conf solo
# afecta al enrutado HTTP, no al destino de los comandos CLI. Sin -d, Odoo arranca
# y se apaga sin tocar ninguna base de datos.
$serverArgs = @($odooBin, '-c', $Config, '-d', $Database, '--db-filter', "^$Database`$")
$operationArgs = @()
if ($Update) { $operationArgs += @('-u', $Update, '--stop-after-init', '--no-http') }
if ($Init)   { $operationArgs += @('-i', $Init, '--stop-after-init', '--no-http') }
# Arranque normal (sin -Update/-Init): Odoo NO migra un módulo aunque el código
# haya cambiado. Se detecta aquí y se ejecuta la actualización controlada ANTES
# de servir. Si falla (p. ej. una sesión de caja abierta impide migrar la
# caja), se aborta: no se sirve una instalación a medio normalizar.
if (-not ($Update -or $Init)) {
    $pending = (& $python (Join-Path $PSScriptRoot 'tools/check_pending_upgrade.py') `
        --config $Config --database $Database).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprobar si hay una actualización pendiente.' }
    if ($pending -eq 'upgrade') {
        Write-Output 'El código es más nuevo que la base. Aplicando la actualización controlada...'
        & $python @serverArgs -u mi_gestor_stock --stop-after-init --no-http
        if ($LASTEXITCODE -ne 0) {
            throw 'La actualización ha fallado. No se arranca sobre una base a medio migrar. Revisa el registro; si hay una sesión de caja abierta, ciérrala y vuelve a arrancar.'
        }
    }
}

& $python @serverArgs @operationArgs
if ($LASTEXITCODE -ne 0) { throw "Odoo ha terminado con error ($LASTEXITCODE). No se inicia tras una actualización fallida." }
if ($NoStart) { return }

# Tras -u / -i (que terminan con --stop-after-init), arranca el servidor normal.
if ($Update -or $Init) {
    & $python @serverArgs
    if ($LASTEXITCODE -ne 0) { throw "Odoo ha terminado con error ($LASTEXITCODE)." }
}
