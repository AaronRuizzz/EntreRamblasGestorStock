<#
    Orquesta la instalación después de que Inno Setup ha copiado los archivos.
    Se ejecuta ELEVADO (el instalador pide UAC).

        pasos-instalacion.ps1 -CodeDir "%ProgramFiles%\EntreRamblas" -DataDir "%ProgramData%\EntreRamblas"

    Idempotente y NO destructivo: conserva una base y unas copias que ya existan.
#>
param(
    [Parameter(Mandatory = $true)][string]$CodeDir,
    [Parameter(Mandatory = $true)][string]$DataDir,
    [ValidatePattern('^[a-z][a-z0-9_]{0,62}$')][string]$Database = 'entre_ramblas',
    [int]$PgPort = 5544,
    [string]$PgServiceName = 'EntreRamblasPostgres',
    [string]$OdooServiceName = 'EntreRamblasOdoo'
)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'La instalación necesita permisos de administrador.'
}

function Write-Paso { param([string]$T) Write-Host ''; Write-Host "== $T" -ForegroundColor Cyan }

$pgData   = Join-Path $DataDir 'pgdata'
$runtime  = $DataDir
$config   = Join-Path $DataDir 'odoo.local'
$python   = Join-Path $CodeDir 'venv\Scripts\python.exe'
$logDir   = Join-Path $DataDir 'instalacion'
New-Item -ItemType Directory -Force -Path $DataDir, $logDir | Out-Null
Start-Transcript -Path (Join-Path $logDir ("instalacion-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')) | Out-Null
try {

# ---------------------------------------------------------------- PostgreSQL bin
Write-Paso 'PostgreSQL (binarios)'
function Get-PgBin {
    $root = Join-Path $env:ProgramFiles 'PostgreSQL'
    if (-not (Test-Path $root)) { return $null }
    Get-ChildItem $root -Directory -EA SilentlyContinue |
        Where-Object { $_.Name -match '^\d+$' } | Sort-Object { [int]$_.Name } -Descending |
        ForEach-Object { $b = Join-Path $_.FullName 'bin'; if (Test-Path (Join-Path $b 'initdb.exe')) { return $b } }
}
$pgBin = Get-PgBin
if (-not $pgBin) {
    if (-not (Get-Command winget -EA SilentlyContinue)) { throw 'Instala PostgreSQL 18 y repite.' }
    & winget install -e --id PostgreSQL.PostgreSQL.18 --accept-package-agreements --accept-source-agreements
    $pgBin = Get-PgBin
    if (-not $pgBin) { throw 'PostgreSQL se instaló pero no se encuentra initdb.exe.' }
}

# --------------------------------------------------- Instancia PostgreSQL propia
Write-Paso "Instancia PostgreSQL dedicada (puerto $PgPort, solo local)"
$pwFile = Join-Path $DataDir 'pg-superpass.secret'
if (-not (Test-Path $pgData -PathType Container) -or -not (Test-Path (Join-Path $pgData 'PG_VERSION'))) {
    $abc = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create(); $buf = New-Object byte[] 1
    $sb = New-Object System.Text.StringBuilder
    while ($sb.Length -lt 40) { $rng.GetBytes($buf); if ($buf[0] -lt 224) { [void]$sb.Append($abc[$buf[0] % $abc.Length]) } }
    $superPass = $sb.ToString()
    Set-Content -LiteralPath $pwFile -Value $superPass -NoNewline -Encoding ascii
    icacls $pwFile /inheritance:r /grant:r "*S-1-5-18:F" "*S-1-5-32-544:F" | Out-Null
    $pwPass = Join-Path $env:TEMP ('erpw-' + [guid]::NewGuid().ToString('N') + '.txt')
    Set-Content -LiteralPath $pwPass -Value $superPass -NoNewline -Encoding ascii
    try {
        & (Join-Path $pgBin 'initdb.exe') -D $pgData -U postgres --encoding=UTF8 --locale=C `
            --auth-host=scram-sha-256 --auth-local=scram-sha-256 --pwfile=$pwPass
        if ($LASTEXITCODE -ne 0) { throw 'initdb falló.' }
    } finally { Remove-Item $pwPass -Force -EA SilentlyContinue }
    # Solo escucha en localhost.
    Add-Content -LiteralPath (Join-Path $pgData 'postgresql.conf') "`nlisten_addresses = '127.0.0.1'`nport = $PgPort`n"
}
if (-not (Get-Service -Name $PgServiceName -EA SilentlyContinue)) {
    & (Join-Path $pgBin 'pg_ctl.exe') register -N $PgServiceName -D $pgData -S auto -o "-p $PgPort"
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo registrar el servicio de PostgreSQL.' }
}
Start-Service -Name $PgServiceName
for ($i = 0; $i -lt 30 -and -not (Test-NetConnection 127.0.0.1 -Port $PgPort -InformationLevel Quiet); $i++) { Start-Sleep 1 }

# Rol de la aplicación (CREATEDB, no superusuario).
$superPass = (Get-Content -LiteralPath $pwFile -Raw)
$rolePwFile = Join-Path $DataDir 'db-password.secret'
if (-not (Test-Path $rolePwFile)) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create(); $buf = New-Object byte[] 1
    $sb = New-Object System.Text.StringBuilder
    while ($sb.Length -lt 40) { $rng.GetBytes($buf); if ($buf[0] -lt 224) { [void]$sb.Append('abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'[$buf[0] % 55]) } }
    Set-Content -LiteralPath $rolePwFile -Value $sb.ToString() -NoNewline -Encoding ascii
    icacls $rolePwFile /inheritance:r /grant:r "*S-1-5-18:F" "*S-1-5-32-544:F" | Out-Null
}
$rolePass = (Get-Content -LiteralPath $rolePwFile -Raw)
$env:PGPASSWORD = $superPass
try {
    $exists = & (Join-Path $pgBin 'psql.exe') -U postgres -h 127.0.0.1 -p $PgPort -d postgres -tAqc "SELECT 1 FROM pg_roles WHERE rolname='odoo'"
    if ($exists.Trim() -ne '1') {
        "SET client_min_messages=warning; CREATE ROLE odoo LOGIN CREATEDB PASSWORD '$($rolePass.Replace("'","''"))';" |
            & (Join-Path $pgBin 'psql.exe') -U postgres -h 127.0.0.1 -p $PgPort -d postgres -v ON_ERROR_STOP=1 -f -
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el rol de la aplicación.' }
    }
} finally { Remove-Item Env:\PGPASSWORD -EA SilentlyContinue }

# ------------------------------------------------------------ Config privada
Write-Paso 'Configuración privada'
if (-not (Test-Path $config)) {
    $env:MGS_DB_PASSWORD = $rolePass
    try {
        & $python (Join-Path $CodeDir 'tools\configure_runtime.py') --directory $DataDir `
            --db-user odoo --db-port $PgPort --pg-bin $pgBin
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la configuración privada.' }
    } finally { Remove-Item Env:\MGS_DB_PASSWORD -EA SilentlyContinue }
    # data_dir dentro de %ProgramData%, y locale de Windows.
    $txt = [IO.File]::ReadAllText($config)
    $txt = $txt -replace '(?m)^\s*data_dir\s*=.*$', ("data_dir = " + (Join-Path $DataDir 'data'))
    if ($txt -notmatch '(?m)^\s*db_template\s*=') { $txt += "`r`ndb_template = template1`r`n" }
    [IO.File]::WriteAllText($config, $txt, (New-Object Text.UTF8Encoding($false)))
}

# ------------------------------------------------------------------- Motor PDF
Write-Paso 'Motor PDF'
& (Join-Path $CodeDir 'install-pdf.ps1') -Config $config
$env:Path = (Join-Path $CodeDir 'tools\wkhtmltox\bin') + ';' + $env:Path
& (Join-Path $CodeDir 'tools\wkhtmltox\bin\wkhtmltopdf.exe') --version | Out-File (Join-Path $logDir 'pdf-version.txt')

# --------------------------------------------------------------- Base de datos
Write-Paso 'Base de datos (nueva, sin demo; se conserva si ya existe)'
Set-Location $CodeDir
& (Join-Path $CodeDir 'bootstrap.ps1') -Config $config -Database $Database

# --------------------------------------------------------------- Servicio Odoo
Write-Paso 'Servicio de Windows'
if (-not (Get-Service -Name $OdooServiceName -EA SilentlyContinue)) {
    & (Join-Path $CodeDir 'venv\Scripts\python.exe') (Join-Path $CodeDir 'tools\windows_service.py') install `
        --name $OdooServiceName --config $config --database $Database --postgres-service $PgServiceName
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo registrar el servicio de la aplicación.' }
}
Start-Service -Name $OdooServiceName

# ----------------------------------------------------------- Acceso directo
Write-Paso 'Acceso directo'
$lnk = Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Entre Ramblas.lnk'
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath = 'powershell.exe'
$sc.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $CodeDir 'instalador\abrir-app.ps1') + '"'
$sc.IconLocation = (Join-Path $CodeDir 'instalador\entreramblas.ico')
$sc.WindowStyle = 7
$sc.Save()

# ----------------------------------------------------- Informe de prueba PDF
Write-Paso 'Informe de prueba'
try {
    & (Join-Path $CodeDir 'venv\Scripts\python.exe') (Join-Path $CodeDir 'tools\check_report_pdf.py') 2>&1 |
        Out-File (Join-Path $logDir 'informe-prueba.txt')
} catch { Write-Warning "El informe de prueba no se pudo generar ahora: $_" }

Write-Host ''
Write-Host 'Instalación completada.' -ForegroundColor Green
Write-Host ("Primer acceso: " + (Join-Path $DataDir ($Database + '-activacion.txt')))

} finally { Stop-Transcript | Out-Null }
