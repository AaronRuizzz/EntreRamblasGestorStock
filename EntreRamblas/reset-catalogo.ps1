# Deja el catálogo a cero antes de una entrega. Conserva toda la configuración.
# El servidor Odoo debe estar PARADO.
param(
    # Vacio: se toma db_name de la configuracion (fuente unica del nombre de base).
    [ValidatePattern('^([a-z][a-z0-9_]{0,62})?$')][string]$Database = '',
    [string]$Config = (Join-Path $PSScriptRoot 'odoo.local'),
    [switch]$Yes
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "No se encuentra el entorno virtual: $python" }
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'No existe el archivo de configuración indicado.' }
if (-not $Database) {
    foreach ($line in Get-Content -LiteralPath $Config) {
        if ($line -match '^\s*db_name\s*=\s*([a-z][a-z0-9_]{0,62})') { $Database = $Matches[1] }
    }
}
if (-not $Database) { throw 'Indica -Database o añade db_name a la configuración.' }
$resetArgs = @((Join-Path $PSScriptRoot 'tools\reset_catalog.py'),
    '-c', (Resolve-Path -LiteralPath $Config).Path, '-d', $Database)
if ($Yes) { $resetArgs += '--yes' }
& $python @resetArgs
if ($LASTEXITCODE -ne 0) { throw "El vaciado no se ha completado (código $LASTEXITCODE)." }
