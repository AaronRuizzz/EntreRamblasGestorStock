# Arranca Odoo 18 con la configuracion local (odoo.conf)
# Uso:  .\start-odoo.ps1              -> arranca el servidor (http://localhost:8069)
#       .\start-odoo.ps1 -Update mi_gestor_stock   -> actualiza un modulo y arranca
#       .\start-odoo.ps1 -Init otro_modulo         -> instala un modulo nuevo y arranca
param(
    [string]$Update = "",
    [string]$Init = "",
    [ValidatePattern('^[a-z][a-z0-9_]{0,62}$')][string]$Database = "mi_base_stock",
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
foreach ($line in Get-Content -LiteralPath $Config) {
    if ($line -match '^\s*db_host\s*=\s*([^;#]+)') { $configDbHost = $Matches[1].Trim() }
    if ($line -match '^\s*db_port\s*=\s*(\d+)') { $configDbPort = [int]$Matches[1] }
}

if (-not (Test-Path -LiteralPath $odooBin -PathType Leaf)) {
    throw "No se encuentra el código Odoo fijado por el proyecto en '$odooBin'."
}
$expectedRevision = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'odoo-revision.txt') -Raw).Trim()
$actualRevision = (& git -C (Join-Path $PSScriptRoot 'odoo') rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualRevision -ne $expectedRevision) { throw 'La revisión Odoo no coincide con odoo-revision.txt.' }

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
& $python @serverArgs @operationArgs
if ($LASTEXITCODE -ne 0) { throw "Odoo ha terminado con error ($LASTEXITCODE). No se inicia tras una actualización fallida." }
if ($NoStart) { return }

# Tras -u / -i (que terminan con --stop-after-init), arranca el servidor normal.
if ($Update -or $Init) {
    & $python @serverArgs
    if ($LASTEXITCODE -ne 0) { throw "Odoo ha terminado con error ($LASTEXITCODE)." }
}
