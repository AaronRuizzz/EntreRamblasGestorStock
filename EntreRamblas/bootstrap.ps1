# ============================================================
#  bootstrap.ps1  ·  Entre Ramblas · Clavel & Azahar (Odoo 18)
# ============================================================
#  Deja el equipo listo para trabajar A PARTIR DEL REPOSITORIO:
#
#    1. Crea el entorno virtual (venv) si no existe e instala las
#       dependencias de Odoo.
#    2. Comprueba que el codigo fuente de Odoo 18 esta en .\odoo\.
#    3. Crea la base de datos `mi_base_stock` DESDE CERO (sin datos
#       demo) e instala el modulo `mi_gestor_stock`, que arrastra
#       todas las apps del proyecto (Inventario, TPV, Contactos,
#       localizacion espanola) y aplica marca, idioma y estilos.
#
#  La base de datos NO se versiona en git: es un producto derivado
#  del modulo. Cualquiera que clone el repo ejecuta este script una
#  vez y obtiene EXACTAMENTE el mismo Odoo.
#
#  Uso:
#    .\bootstrap.ps1            -> crea la BD si no existe
#    .\bootstrap.ps1 -Reset     -> BORRA la BD y la vuelve a crear
#    .\bootstrap.ps1 -Database otra_bd
#
#  Requisitos previos (una sola vez, ver README §3):
#    - Python 3.12  ·  PostgreSQL 16 con rol  odoo / odoo  (CREATEDB)
#    - wkhtmltopdf en "C:\Program Files\wkhtmltopdf\bin"
# ============================================================
param(
    [switch]$Reset,
    [string]$Database = "mi_base_stock"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python  = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
$odooBin = Join-Path $PSScriptRoot "odoo\odoo-bin"
$odooReq = Join-Path $PSScriptRoot "odoo\requirements.txt"

# ---- 1. Codigo fuente de Odoo -------------------------------------------------
if (-not (Test-Path -LiteralPath $odooBin -PathType Leaf)) {
    Write-Host "No se encuentra el codigo fuente de Odoo 18 en '.\odoo\'." -ForegroundColor Yellow
    Write-Host "Clonalo (necesita internet, una sola vez):" -ForegroundColor Yellow
    Write-Host "  git clone --depth 1 --branch 18.0 https://github.com/odoo/odoo.git odoo" -ForegroundColor Cyan
    throw "Falta .\odoo\"
}

# ---- 2. Entorno virtual + dependencias --------------------------------------
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Host "Creando entorno virtual en .\venv ..." -ForegroundColor Cyan
    py -3.12 -m venv venv
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { python -m venv venv }
    & $python -m pip install --upgrade pip wheel
    # gevent y python-ldap no traen wheel para Windows y no hacen falta en local
    (Get-Content $odooReq) |
        Where-Object { $_ -notmatch '^\s*(gevent|python-ldap)' } |
        Set-Content (Join-Path $env:TEMP "odoo-req-win.txt") -Encoding utf8
    & $python -m pip install -r (Join-Path $env:TEMP "odoo-req-win.txt")
    & $python -m pip install libsass  # compilador SCSS que usa Odoo
} else {
    Write-Host "venv ya existe -> se reutiliza." -ForegroundColor DarkGray
}

# ---- 3. PostgreSQL ----------------------------------------------------------
if (-not (Test-NetConnection -ComputerName localhost -Port 5432 -InformationLevel Quiet)) {
    throw "PostgreSQL no responde en localhost:5432. Arranca el servicio 'postgresql-x64-16'."
}
$env:PGPASSWORD = "odoo"
$psql = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
        Select-Object -Last 1
function DbExists {
    if ($psql) {
        return ((& $psql.FullName -U odoo -h localhost -d postgres -tAc `
            "SELECT 1 FROM pg_database WHERE datname='$Database'") -eq "1")
    }
    return $false
}

# ---- 4. Reset opcional ----------------------------------------------------
if ($Reset -and (DbExists)) {
    Write-Host "Borrando base de datos '$Database' ..." -ForegroundColor Yellow
    & $psql.FullName -U odoo -h localhost -d postgres -c `
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$Database'" | Out-Null
    & $psql.FullName -U odoo -h localhost -d postgres -c "DROP DATABASE `"$Database`"" | Out-Null
    $fs = Join-Path $PSScriptRoot ".odoo_data\filestore\$Database"
    if (Test-Path $fs) { Remove-Item -Recurse -Force $fs }
}

if (DbExists) {
    Write-Host "La base de datos '$Database' ya existe." -ForegroundColor Green
    Write-Host "  - Para RECREARLA desde cero:      .\bootstrap.ps1 -Reset"
    Write-Host "  - Para aplicar cambios del modulo: .\start-odoo.ps1 -Update mi_gestor_stock"
    return
}

# ---- 5. Crear la BD e instalar el modulo -----------------------------------
$wk = "C:\Program Files\wkhtmltopdf\bin"
if ((Test-Path $wk) -and ($env:Path -notlike "*wkhtmltopdf*")) { $env:Path = "$wk;$env:Path" }

Write-Host "Creando '$Database' e instalando mi_gestor_stock (sin datos demo)..." -ForegroundColor Cyan
& $python $odooBin -c (Join-Path $PSScriptRoot "odoo.conf") `
    -d $Database -i mi_gestor_stock --without-demo=all --stop-after-init

Write-Host ""
Write-Host "Listo. Arranca el servidor con:  .\start-odoo.ps1" -ForegroundColor Green
Write-Host "  URL: http://localhost:8069   BD: $Database"
