<#
    Prepara un equipo nuevo (el PC de la tienda) para el Gestor de Stock.

    Encadena lo que INSTALACION.md describe por pasos: instala PostgreSQL y
    Python si faltan, crea el rol de base de datos, genera la configuración
    privada, descarga el código de Odoo y ejecuta bootstrap.ps1.

    Es idempotente y NO destructivo: conserva PostgreSQL, roles, configuración
    y bases de datos que ya existan, y se detiene con un mensaje claro cuando
    no puede continuar sin que decida una persona.

    Uso habitual, desde la carpeta EntreRamblas y con internet:

        .\preparar-equipo.ps1

    Aparecerán avisos de Control de Cuentas de Usuario (UAC) si hay que
    instalar PostgreSQL o Python. Para reutilizar una contraseña concreta del
    rol PostgreSQL, ponerla antes en la variable de entorno MGS_DB_PASSWORD y
    borrarla después.
#>
param(
    [ValidatePattern('^[a-z][a-z0-9_]{0,62}$')][string]$Database = 'entre_ramblas',
    [string]$RuntimeDirectory = (Join-Path $env:LOCALAPPDATA 'EntreRamblas'),
    [ValidatePattern('^[a-z][a-z0-9_]{0,62}$')][string]$DbUser = 'odoo',
    [int]$DbPort = 5432
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Write-Paso { param([string]$Texto) Write-Host ''; Write-Host ('== ' + $Texto) -ForegroundColor Cyan }

function New-ClaveAleatoria {
    param([int]$Longitud = 32)
    # Solo letras y dígitos: la clave viaja a odoo.local y a psql sin comillas
    # que escapar. Se descarta el sesgo del módulo al mapear byte -> carácter.
    $abc = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $limite = [math]::Floor(256 / $abc.Length) * $abc.Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buffer = New-Object byte[] 1
    $clave = New-Object System.Text.StringBuilder
    while ($clave.Length -lt $Longitud) {
        $rng.GetBytes($buffer)
        if ($buffer[0] -lt $limite) { [void]$clave.Append($abc[$buffer[0] % $abc.Length]) }
    }
    return $clave.ToString()
}

function Read-Clave {
    param([string]$Mensaje)
    $segura = Read-Host -Prompt $Mensaje -AsSecureString
    $puntero = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($puntero) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($puntero) }
}

function Get-PgBin {
    $raiz = Join-Path $env:ProgramFiles 'PostgreSQL'
    if (-not (Test-Path -LiteralPath $raiz)) { return $null }
    $versiones = Get-ChildItem -LiteralPath $raiz -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d+$' } | Sort-Object { [int]$_.Name } -Descending
    foreach ($v in $versiones) {
        $bin = Join-Path $v.FullName 'bin'
        if (Test-Path -LiteralPath (Join-Path $bin 'psql.exe')) { return $bin }
    }
    return $null
}

function Invoke-Psql {
    param([string]$PgBin, [string]$Usuario, [string]$Clave, [string]$Sql)
    # Fallar es una respuesta válida aquí (se prueba una contraseña y, si no
    # vale, se pide otra). PowerShell convierte el stderr de un ejecutable
    # nativo en error terminante, así que hay que bajar la preferencia.
    $previo = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $env:PGPASSWORD = $Clave
    try {
        $salida = & (Join-Path $PgBin 'psql.exe') -U $Usuario -h 127.0.0.1 -p $DbPort `
            -d postgres -v ON_ERROR_STOP=1 -tAqc $Sql 2>$null
        return [pscustomobject]@{ Ok = ($LASTEXITCODE -eq 0); Salida = (($salida | Out-String).Trim()) }
    } finally {
        Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
        $ErrorActionPreference = $previo
    }
}

function Test-PythonSano {
    # El Python de la Microsoft Store se ejecuta en un contenedor que redirige
    # AppData\Local a una carpeta interna del paquete. Con él, data_dir, el
    # registro y el servicio de Windows apuntarían a rutas fantasma. Se
    # comprueba el síntoma directamente, no la ruta del ejecutable.
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { return $false }
    # Es un sondeo: puede fallar sin que eso aborte el script. Y las comillas
    # del código Python van simples, porque PowerShell se come las dobles al
    # construir la línea de órdenes de un ejecutable nativo.
    $previo = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $version = & py -3.12 -c "import sys; print(1 if sys.version_info[:2]==(3,12) else 0)" 2>$null
        if ($LASTEXITCODE -ne 0 -or $version -ne '1') { return $false }
        $local = & py -3.12 -c "import os; print(os.environ['LOCALAPPDATA'])" 2>$null
        if ($LASTEXITCODE -ne 0) { return $false }
        return ($local -eq $env:LOCALAPPDATA)
    } finally { $ErrorActionPreference = $previo }
}

# ---------------------------------------------------------------- comprobaciones
Write-Paso 'Comprobando el equipo'
foreach ($sync in @($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial)) {
    if ($sync -and $PSScriptRoot.StartsWith($sync, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'El proyecto está dentro de OneDrive. Muévelo a una carpeta local antes de instalar.'
    }
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Instala Git antes de continuar.' }
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw 'Falta winget (Instalador de aplicaciones). Instala PostgreSQL 18 y Python 3.12 a mano y repite.'
}
Write-Output 'Git y winget disponibles.'

# ------------------------------------------------------------------- PostgreSQL
Write-Paso 'PostgreSQL'
$pgBin = Get-PgBin
if (-not $pgBin) {
    Write-Output 'No hay PostgreSQL instalado. Instalando PostgreSQL 18 (acepta el aviso de UAC).'
    & winget install -e --id PostgreSQL.PostgreSQL.18 --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar PostgreSQL.' }
    $pgBin = Get-PgBin
    if (-not $pgBin) { throw 'PostgreSQL se instaló pero no se encuentra psql.exe. Revisa la instalación.' }
}
Write-Output ('Binarios de PostgreSQL: ' + $pgBin)
$servicio = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $servicio) { throw 'No hay servicio de PostgreSQL registrado. Revisa la instalación.' }
if ($servicio.Status -ne 'Running') { Start-Service -Name $servicio.Name }
if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port $DbPort -InformationLevel Quiet)) {
    throw ('PostgreSQL no responde en el puerto ' + $DbPort + '. Revisa el servicio ' + $servicio.Name + '.')
}
Write-Output ('Servicio ' + $servicio.Name + ' en marcha.')

# ----------------------------------------------------------------------- Python
Write-Paso 'Python 3.12'
if (Test-PythonSano) {
    Write-Output 'Ya hay un Python 3.12 utilizable.'
} else {
    Write-Output 'Falta un Python 3.12 fuera de la Microsoft Store. Instalando (acepta el aviso de UAC).'
    & winget install -e --id Python.Python.3.12 --scope machine --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar Python 3.12.' }
    if (-not (Test-PythonSano)) {
        throw 'Python 3.12 sigue sin ser utilizable. Cierra y vuelve a abrir PowerShell y repite el script.'
    }
    Write-Output 'Python 3.12 instalado.'
}

# --------------------------------------------------------- rol y configuración
$config = Join-Path $RuntimeDirectory 'odoo.local'
if (Test-Path -LiteralPath $config -PathType Leaf) {
    Write-Paso 'Configuración privada'
    Write-Output ('Ya existe y se conserva: ' + $config)
} else {
    Write-Paso ('Rol PostgreSQL "' + $DbUser + '"')
    # La contraseña del instalador solo sirve si PostgreSQL lo acabamos de
    # poner nosotros; en un equipo con PostgreSQL previo hay que pedirla.
    $superClave = 'postgres'
    if (-not (Invoke-Psql -PgBin $pgBin -Usuario 'postgres' -Clave $superClave -Sql 'SELECT 1').Ok) {
        $superClave = Read-Clave -Mensaje 'Contraseña del superusuario "postgres" de PostgreSQL'
        if (-not (Invoke-Psql -PgBin $pgBin -Usuario 'postgres' -Clave $superClave -Sql 'SELECT 1').Ok) {
            throw 'No se pudo conectar como superusuario. Comprueba la contraseña y repite el script.'
        }
    }
    $consulta = Invoke-Psql -PgBin $pgBin -Usuario 'postgres' -Clave $superClave `
        -Sql ("SELECT 1 FROM pg_roles WHERE rolname='" + $DbUser + "'")
    if (-not $consulta.Ok) { throw 'No se pudo consultar los roles de PostgreSQL.' }

    $claveRol = $env:MGS_DB_PASSWORD
    if ($consulta.Salida -eq '1') {
        # El rol ya existe: nunca se le cambia la contraseña por nuestra cuenta.
        Write-Output ('El rol "' + $DbUser + '" ya existe. No se modifica su contraseña.')
        if (-not $claveRol) { $claveRol = Read-Clave -Mensaje ('Contraseña actual del rol "' + $DbUser + '"') }
        if (-not (Invoke-Psql -PgBin $pgBin -Usuario $DbUser -Clave $claveRol -Sql 'SELECT 1').Ok) {
            throw ('El rol "' + $DbUser + '" existe pero esa contraseña no es válida. No se ha modificado nada.')
        }
        Write-Output 'Rol existente verificado.'
    } else {
        if (-not $claveRol) { $claveRol = New-ClaveAleatoria }
        $escapada = $claveRol.Replace("'", "''")
        $sql = @"
\set rolpw '$escapada'
CREATE ROLE $DbUser LOGIN CREATEDB PASSWORD :'rolpw';
"@
        # Por la entrada estándar: la contraseña no aparece en la línea de
        # órdenes y por tanto tampoco en la lista de procesos.
        $env:PGPASSWORD = $superClave
        try {
            $sql | & (Join-Path $pgBin 'psql.exe') -U postgres -h 127.0.0.1 -p $DbPort `
                -d postgres -v ON_ERROR_STOP=1 -f -
            $creado = ($LASTEXITCODE -eq 0)
        } finally { Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue }
        if (-not $creado) { throw ('No se pudo crear el rol "' + $DbUser + '".') }
        if (-not (Invoke-Psql -PgBin $pgBin -Usuario $DbUser -Clave $claveRol -Sql 'SELECT 1').Ok) {
            throw ('El rol "' + $DbUser + '" se creó pero no puede conectarse.')
        }
        Write-Output ('Rol "' + $DbUser + '" creado con permiso CREATEDB, sin ser superusuario.')
    }

    Write-Paso 'Configuración privada'
    $env:MGS_DB_PASSWORD = $claveRol
    try {
        & py -3.12 tools/configure_runtime.py --directory $RuntimeDirectory --db-user $DbUser `
            --db-port $DbPort --pg-bin $pgBin
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la configuración privada.' }
    } finally { Remove-Item Env:\MGS_DB_PASSWORD -ErrorAction SilentlyContinue }
}
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) { throw 'No se encuentra la configuración privada.' }

# ------------------------------------------------------------ locale en Windows
Write-Paso 'Ajuste de locale para Windows'
$texto = [System.IO.File]::ReadAllText($config)
if ($texto -match '(?m)^\s*db_template\s*=') {
    Write-Output 'db_template ya está fijado en la configuración.'
} else {
    # Odoo, al partir de template0, crea la base con LC_COLLATE 'C' y deja
    # LC_CTYPE con el locale del cluster. PostgreSQL en Windows rechaza las
    # conexiones a una base con esos dos valores distintos, así que la base
    # nacería inservible. template1 hereda el locale del cluster y coinciden.
    if (-not $texto.EndsWith("`n")) { $texto += "`r`n" }
    $texto += "db_template = template1`r`n"
    [System.IO.File]::WriteAllText($config, $texto, (New-Object System.Text.UTF8Encoding($false)))
    Write-Output 'Añadido db_template = template1.'
}

# ------------------------------------------------------------- código de Odoo
Write-Paso 'Código de Odoo'
$revision = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'odoo-revision.txt') -Raw).Trim()
$fuente = Join-Path $PSScriptRoot 'odoo'
if (Test-Path -LiteralPath (Join-Path $fuente 'odoo-bin')) {
    Write-Output 'Ya está descargado; bootstrap.ps1 verificará la revisión.'
} else {
    if (Test-Path -LiteralPath $fuente) {
        # Solo se descarta una descarga a medias: carpeta sin odoo-bin y sin
        # ningún commit. Un checkout de verdad nunca cumple las dos cosas.
        & git -C $fuente rev-parse --verify HEAD 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { throw 'La carpeta odoo existe y tiene contenido. Revísala a mano antes de continuar.' }
        Write-Output 'Se descarta una descarga anterior incompleta.'
        Remove-Item -LiteralPath $fuente -Recurse -Force
    }
    & git init $fuente | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar la carpeta de Odoo.' }
    & git -C $fuente remote add origin https://github.com/odoo/odoo.git
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo configurar el origen de Odoo.' }
    # Ajustes locales a este repositorio (no globales): la descarga es grande y
    # con conexiones domésticas se corta a media transferencia.
    & git -C $fuente config http.postBuffer 1048576000
    & git -C $fuente config http.lowSpeedLimit 1000
    & git -C $fuente config http.lowSpeedTime 300
    & git -C $fuente config core.compression 0
    $descargado = $false
    foreach ($intento in 1..5) {
        Write-Output ('Descargando Odoo (intento ' + $intento + ' de 5). Son varios cientos de MB.')
        & git -C $fuente fetch --depth 1 --no-tags origin $revision
        if ($LASTEXITCODE -eq 0) { $descargado = $true; break }
        Start-Sleep -Seconds 8
    }
    if (-not $descargado) { throw 'No se pudo descargar el código de Odoo. Comprueba la conexión y repite el script.' }
    & git -C $fuente checkout --detach FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo seleccionar la revisión de Odoo.' }
}

# ----------------------------------------------------------------- instalación
Write-Paso 'Instalación'
if (Test-Path -LiteralPath ($config + '.pending')) {
    throw 'Hay una instalación anterior incompleta. Revisa odoo.log y consulta INSTALACION.md; no se borra sola.'
}
# bootstrap.ps1 aborta lanzando una excepción, que detiene también a este script.
& (Join-Path $PSScriptRoot 'bootstrap.ps1') -Config $config -Database $Database

# ----------------------------------------------------------------- verificación
Write-Paso 'Comprobación final'
$usuarioConfig = $DbUser
$claveConfig = $null
foreach ($linea in Get-Content -LiteralPath $config) {
    if ($linea -match '^\s*db_user\s*=\s*(.+?)\s*$') { $usuarioConfig = $Matches[1] }
    if ($linea -match '^\s*db_password\s*=\s*(.+?)\s*$') { $claveConfig = $Matches[1] }
}
if ($claveConfig) {
    # Si collate y ctype no coinciden, la base existe pero no admite conexiones
    # en Windows. Mejor detectarlo aquí que el día de abrir la tienda.
    $locale = Invoke-Psql -PgBin $pgBin -Usuario $usuarioConfig -Clave $claveConfig `
        -Sql ("SELECT datcollate=datctype FROM pg_database WHERE datname='" + $Database + "'")
    if ($locale.Ok -and $locale.Salida -eq 'f') {
        throw ('La base "' + $Database + '" tiene collate y ctype distintos y no funcionará en Windows. Revisa db_template.')
    }
}
$activacion = Join-Path $RuntimeDirectory ($Database + '-activacion.txt')
Write-Output ''
Write-Output 'Equipo preparado.'
Write-Output ''
Write-Output ('  Configuración : ' + $config)
Write-Output ('  Base de datos : ' + $Database)
if (Test-Path -LiteralPath $activacion -PathType Leaf) {
    Write-Output ('  Primer acceso: ' + $activacion + ' (código de activación de un solo uso)')
} else {
    Write-Output '  Primer acceso: la base ya existía; se conservan sus usuarios.'
}
Write-Output ''
Write-Output 'Arrancar:'
Write-Output ('  .\start-odoo.ps1 -Config "' + $config + '" -Database ' + $Database)
Write-Output ''
Write-Output 'Primer acceso: en la pantalla de acceso, escribir el código de activación'
Write-Output 'del archivo de arriba, elegir la contraseña (12+ caracteres) y guardar la'
Write-Output 'clave de recuperación que aparece. Después, completar los datos fiscales de'
Write-Output 'la empresa, los métodos de pago, la impresora y el cajón, y la carpeta de'
Write-Output 'copias en el SSD externo (instalador\README.md, "Configurar la copia en'
Write-Output 'el SSD externo").'
