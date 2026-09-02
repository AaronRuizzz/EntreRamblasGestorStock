# Arranca Odoo 18 con la configuracion local (odoo.conf)
# Uso:  .\start-odoo.ps1              -> arranca el servidor (http://localhost:8069)
#       .\start-odoo.ps1 -Update mi_gestor_stock   -> actualiza un modulo y arranca
#       .\start-odoo.ps1 -Init otro_modulo         -> instala un modulo nuevo y arranca
param(
    [string]$Update = "",
    [string]$Init = "",
    [string]$Database = "mi_base_stock"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
$odooBin = Join-Path $PSScriptRoot "odoo\odoo-bin"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "No se encuentra el entorno virtual: $python"
}

$configDbHost = "localhost"
$configDbPort = 5432

if (-not (Test-Path -LiteralPath $odooBin -PathType Leaf)) {
    $globalOdoo = Get-ChildItem "C:\Program Files\Odoo*\server\odoo-bin" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($globalOdoo) {
        $odooBin = $globalOdoo.FullName
    } else {
        throw "No se encuentra odoo-bin en '$odooBin'. Descarga el código fuente de Odoo 18 en la carpeta 'odoo' del proyecto."
    }
}

if (-not (Test-NetConnection -ComputerName $configDbHost -Port $configDbPort -InformationLevel Quiet)) {
    throw "PostgreSQL no responde en $configDbHost`:$configDbPort. Inicia el servicio PostgreSQL y vuelve a ejecutar este script."
}

# Asegura que wkhtmltopdf este en el PATH de este proceso (para informes PDF)
$wk = "C:\Program Files\wkhtmltopdf\bin"
if ((Test-Path $wk) -and ($env:Path -notlike "*wkhtmltopdf*")) { $env:Path = "$wk;$env:Path" }

# -d <BD> es OBLIGATORIO en los comandos -i / -u: el dbfilter de odoo.conf solo
# afecta al enrutado HTTP, no al destino de los comandos CLI. Sin -d, Odoo arranca
# y se apaga sin tocar ninguna base de datos.
$args = @($odooBin, "-c", (Join-Path $PSScriptRoot "odoo.conf"), "-d", $Database)
if ($Update) { $args += @("-u", $Update, "--stop-after-init") }
if ($Init)   { $args += @("-i", $Init, "--stop-after-init") }
& $python @args

# Tras -u / -i (que terminan con --stop-after-init), arranca el servidor normal.
if ($Update -or $Init) {
    & $python @($odooBin, "-c", (Join-Path $PSScriptRoot "odoo.conf"))
}
