# Instala la revisión fijada, dependencias bloqueadas y una base nueva sin demo.
# Conserva cualquier base existente. Requiere PostgreSQL y configuración privada.
param(
    [ValidatePattern('^[a-z][a-z0-9_]{0,62}$')][string]$Database = 'entre_ramblas',
    [string]$Config = (Join-Path $PSScriptRoot 'odoo.local')
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'Prepara la configuración privada e indícala con -Config.' }
$Config = (Resolve-Path -LiteralPath $Config).Path
$revision = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'odoo-revision.txt') -Raw).Trim()
if ($revision -notmatch '^[a-f0-9]{40}$') { throw 'Revisión Odoo no válida.' }
$source = Join-Path $PSScriptRoot 'odoo'
$odooBin = Join-Path $source 'odoo-bin'
if (-not (Test-Path -LiteralPath $source)) {
    & git init $source
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar el código Odoo.' }
    & git -C $source remote add origin https://github.com/odoo/odoo.git
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo configurar el origen Odoo.' }
    & git -C $source fetch --depth 1 origin $revision
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo descargar la revisión Odoo fijada.' }
    & git -C $source checkout --detach FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo seleccionar la revisión Odoo.' }
}
if (-not (Test-Path -LiteralPath $odooBin)) { throw 'La carpeta Odoo existe pero está incompleta. Revísala antes de continuar.' }
$actual = (& git -C $source rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actual -ne $revision) { throw 'La revisión Odoo no coincide. No se modifica el checkout existente.' }
$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    & py -3.12 -m venv (Join-Path $PSScriptRoot 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Instala Python 3.12 antes de continuar.' }
}
& $python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'El entorno requiere Python 3.12.' }
& $python -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements-windows.lock')
if ($LASTEXITCODE -ne 0) { throw 'No se han instalado las dependencias fijadas.' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Hay dependencias incompatibles.' }
$state = & $python tools/install_database.py exists --config $Config --database $Database
if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprobar PostgreSQL. Revisa la configuración privada.' }
if ($state -contains 'exists') {
    if (Test-Path -LiteralPath ($Config + '.pending')) { throw 'Existe una instalación incompleta. No se borra ni se reinicia automáticamente.' }
    Write-Output "La base '$Database' existe y se conserva. Para actualizar usa start-odoo.ps1 -Config <archivo> -Database $Database -Update mi_gestor_stock."
    return
}
if ($state -notcontains 'new') { throw 'Respuesta inesperada al comprobar la base.' }
& (Join-Path $PSScriptRoot 'install-pdf.ps1') -Config $Config
$env:Path = (Join-Path (Split-Path $Config -Parent) 'tools/wkhtmltox/bin') + ';' + $env:Path
if (Test-Path -LiteralPath ($Config + '.pending')) { throw 'Ya hay una instalación pendiente con esta configuración.' }
[System.IO.File]::WriteAllText($Config + '.pending', $Database)
& $python tools/install_database.py reserve --config $Config --database $Database
if ($LASTEXITCODE -ne 0) { throw 'No se pudo reservar una base nueva. No se instala sobre un destino existente.' }
& $python $odooBin -c $Config -d $Database -i mi_gestor_stock --without-demo=all --stop-after-init --no-http
if ($LASTEXITCODE -ne 0) { throw 'La instalación ha fallado. Se conserva el marcador pendiente; no arranques esta base.' }
& $python tools/install_database.py provision --config $Config --database $Database
if ($LASTEXITCODE -ne 0) { throw 'El alta inicial no se completó. Se mantiene bloqueado el arranque.' }

# Fuente unica del nombre de base: se fija en la configuracion para que
# start-odoo.ps1 (y las demas herramientas) no necesiten repetirlo.
$configText = [System.IO.File]::ReadAllText($Config)
if ($configText -notmatch '(?m)^\s*db_name\s*=') {
    if (-not $configText.EndsWith("`n")) { $configText += "`r`n" }
    $configText += "db_name = $Database`r`n"
    [System.IO.File]::WriteAllText($Config, $configText, (New-Object System.Text.UTF8Encoding($false)))
}

Write-Output "Instalación completada. Arranque: start-odoo.ps1 -Config <archivo>"
