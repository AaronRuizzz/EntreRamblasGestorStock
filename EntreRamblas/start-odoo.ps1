# Arranca Odoo 18 con la configuracion local (odoo.conf)
# Uso:  .\start-odoo.ps1              -> arranca el servidor (http://localhost:8069)
#       .\start-odoo.ps1 -Update mi_gestor_stock   -> actualiza un modulo y arranca
#       .\start-odoo.ps1 -Init otro_modulo         -> instala un modulo nuevo y arranca
param(
    [string]$Update = "",
    [string]$Init = ""
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
# Asegura que wkhtmltopdf este en el PATH de este proceso (para informes PDF)
$wk = "C:\Program Files\wkhtmltopdf\bin"
if ((Test-Path $wk) -and ($env:Path -notlike "*wkhtmltopdf*")) { $env:Path = "$wk;$env:Path" }

$py = ".\venv\Scripts\python.exe"
$args = @(".\odoo\odoo-bin", "-c", "odoo.conf")
if ($Update) { $args += @("-u", $Update) }
if ($Init)   { $args += @("-i", $Init) }
& $py @args
