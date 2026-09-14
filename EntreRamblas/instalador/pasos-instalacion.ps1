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
    # -tAqc no devuelve filas si el rol no existe: $exists queda $null y .Trim()
    # lanzaba una excepción. Se comprueba primero el código de salida de psql y
    # luego si alguna línea es exactamente '1'.
    $exists = & (Join-Path $pgBin 'psql.exe') -U postgres -h 127.0.0.1 -p $PgPort -d postgres -tAqc "SELECT 1 FROM pg_roles WHERE rolname='odoo'"
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar los roles de PostgreSQL.' }
    $roleExists = @($exists) | Where-Object { $_ -and $_.Trim() -eq '1' }
    if (-not $roleExists) {
        "SET client_min_messages=warning; CREATE ROLE odoo LOGIN CREATEDB PASSWORD '$($rolePass.Replace("'","''"))';" |
            & (Join-Path $pgBin 'psql.exe') -U postgres -h 127.0.0.1 -p $PgPort -d postgres -v ON_ERROR_STOP=1 -f -
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el rol de la aplicación.' }
    }
} finally { Remove-Item Env:\PGPASSWORD -EA SilentlyContinue }

# ------------------------------------------------------------ Entorno Python
Write-Paso 'Entorno Python (propio del paquete, sin internet)'
$venvPython = Join-Path $CodeDir 'venv\Scripts\python.exe'
$vendoredPython = Join-Path $CodeDir 'python\python.exe'
$wheelDir = Join-Path $CodeDir 'wheels'
if (-not (Test-Path -LiteralPath $venvPython)) {
    if (-not (Test-Path -LiteralPath $vendoredPython)) {
        throw 'Falta el CPython del paquete en python\. Reconstruye el paquete con empaquetar.ps1.'
    }
    & $vendoredPython -m venv (Join-Path $CodeDir 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno virtual.' }
    $pipArgs = @('-m', 'pip', 'install', '--no-warn-script-location',
                 '-r', (Join-Path $CodeDir 'requirements-windows.lock'))
    if (Test-Path -LiteralPath $wheelDir) { $pipArgs += @('--no-index', '--find-links', $wheelDir) }
    & $venvPython @pipArgs
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias del paquete.' }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Hay dependencias incompatibles en el entorno.' }
}
& $venvPython (Join-Path $CodeDir 'tools\verificar_entorno.py')
if ($LASTEXITCODE -ne 0) {
    & $venvPython (Join-Path $CodeDir 'tools\verificar_entorno.py') --json | Out-File (Join-Path $logDir 'entorno.json')
    throw 'El entorno Python del paquete no es propio o está incompleto (revisa instalacion\entorno.json).'
}

# ------------------------------------------------------------ Config privada
Write-Paso 'Configuración privada'
if (-not (Test-Path $config)) {
    $env:MGS_DB_PASSWORD = $rolePass
    try {
        # --allow-existing: el instalador YA reservó $DataDir (pgdata, logs,
        # secretos). configure_runtime salta solo la guarda de "carpeta vacía";
        # sigue rechazando OneDrive, un odoo.local ya presente, y nunca
        # sobrescribe archivos.
        & $python (Join-Path $CodeDir 'tools\configure_runtime.py') --directory $DataDir `
            --db-user odoo --db-port $PgPort --pg-bin $pgBin --allow-existing
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
# El paquete ya trae wkhtmltopdf bajo tools\wkhtmltox: se usa ese (instalación
# sin internet). Solo si faltara se recurre a install-pdf.ps1 (descarga).
$pdfBin = Join-Path $CodeDir 'tools\wkhtmltox\bin\wkhtmltopdf.exe'
if (-not (Test-Path -LiteralPath $pdfBin)) {
    & (Join-Path $CodeDir 'install-pdf.ps1') -Config $config
    $pdfBin = Join-Path (Split-Path $config -Parent) 'tools\wkhtmltox\bin\wkhtmltopdf.exe'
}
if (-not (Test-Path -LiteralPath $pdfBin)) { throw 'No se encuentra el motor PDF (wkhtmltopdf).' }
$pdfBinDir = Split-Path $pdfBin -Parent
$env:Path = $pdfBinDir + ';' + $env:Path
& $pdfBin --version | Out-File (Join-Path $logDir 'pdf-version.txt')
if ($LASTEXITCODE -ne 0) { throw 'El motor PDF no se puede ejecutar en este equipo.' }

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

# ------------------------------------------------ Servicio actualizador (H9)
# Componente SEPARADO con privilegios (LocalSystem) para aplicar
# actualizaciones: el servicio de la app (arriba) corre como LocalService y
# no puede reemplazar su propio código/venv en Program Files. Arranque BAJO
# DEMANDA: nunca se inicia solo; solo lo arranca mgs.update.action_accept().
Write-Paso 'Servicio actualizador (bajo demanda)'
$updaterServiceName = 'EntreRamblasActualizador'
if (-not (Get-Service -Name $updaterServiceName -EA SilentlyContinue)) {
    & $venvPython (Join-Path $CodeDir 'tools\update_service.py') install `
        --config $config --database $Database --odoo-service $OdooServiceName `
        --postgres-service $PgServiceName
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo registrar el servicio actualizador.' }
}
# LocalService (la app) solo puede ARRANCARLO, no pararlo, reconfigurarlo ni
# borrarlo: se toma la lista de control de acceso actual del servicio y se le
# añade una entrada mínima para SOLO iniciar (RP) + consultar (CCLCRC), sin
# tocar los permisos de SYSTEM/Administradores ya presentes.
$sddlLines = & sc.exe sdshow $updaterServiceName
$currentSddl = ($sddlLines | Where-Object { $_ -match '^D:' } | Select-Object -First 1)
if ($currentSddl -and $currentSddl -notmatch 'S-1-5-19') {
    $newSddl = $currentSddl -replace '^(D:)', ('$1(A;;CCLCRPRC;;;S-1-5-19)')
    & sc.exe sdset $updaterServiceName $newSddl | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo limitar el permiso del servicio actualizador.' }
}

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
# Contra la base recién instalada, con los permisos reales (la propietaria) y el
# servidor ya en marcha. Si falla, la instalación falla: un PDF roto en el PC de
# la tienda no es aceptable.
& $venvPython (Join-Path $CodeDir 'tools\check_report_pdf.py') `
    --config $config --database $Database `
    --wkhtmltopdf-bin $pdfBinDir `
    --salida (Join-Path $logDir 'informe-prueba.pdf') 2>&1 |
    Tee-Object -FilePath (Join-Path $logDir 'informe-prueba.txt')
if ($LASTEXITCODE -ne 0) { throw 'El informe de prueba PDF no se generó correctamente. Revisa instalacion\informe-prueba.txt.' }

Write-Host ''
Write-Host 'Instalación completada.' -ForegroundColor Green
Write-Host ("Primer acceso: " + (Join-Path $DataDir ($Database + '-activacion.txt')))

} finally { Stop-Transcript | Out-Null }
