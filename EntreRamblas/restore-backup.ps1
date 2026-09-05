# ============================================================
#  restore-backup.ps1  ·  Entre Ramblas · Clavel & Azahar
# ============================================================
#  Restaura una copia de seguridad del Gestor de Stock: deja la
#  base de datos y el filestore exactamente como estaban cuando
#  se hizo la copia (productos, stock, ventas, usuarios y la
#  configuracion de los dispositivos).
#
#  Uso:
#    .\restore-backup.ps1                      -> restaura la copia mas reciente
#    .\restore-backup.ps1 -Archivo C:\ruta\copia.zip
#    .\restore-backup.ps1 -Lista               -> solo enumera las copias
#
#  El servidor tiene que estar PARADO: no se puede restaurar una
#  base de datos que esta en uso.
# ============================================================
param(
    [string]$Archivo = "",
    [string]$Database = "mi_base_stock",
    [switch]$Lista
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "No se encuentra el entorno virtual: $python  (ejecuta .\bootstrap.ps1)"
}

# ---- Carpeta de copias -----------------------------------------------------
# Por defecto, la que usa el modulo: <data_dir>\backups (ver odoo.conf).
$carpeta = Join-Path $PSScriptRoot ".odoo_data\backups"
if (-not (Test-Path -LiteralPath $carpeta)) {
    if (-not $Archivo) {
        throw "No hay ninguna carpeta de copias en '$carpeta'. Indica el archivo con -Archivo."
    }
}

if ($Lista -or -not $Archivo) {
    $copias = @()
    if (Test-Path -LiteralPath $carpeta) {
        $copias = Get-ChildItem -LiteralPath $carpeta -Filter *.zip |
                  Sort-Object LastWriteTime -Descending
    }
    if ($Lista) {
        if (-not $copias) { Write-Host "No hay copias en $carpeta" -ForegroundColor Yellow; return }
        Write-Host "Copias disponibles en $carpeta :" -ForegroundColor Cyan
        $copias | ForEach-Object {
            "{0,-40} {1,10:N1} MB  {2}" -f $_.Name, ($_.Length / 1MB), $_.LastWriteTime
        }
        return
    }
    if (-not $copias) { throw "No hay ninguna copia en '$carpeta'." }
    $Archivo = $copias[0].FullName
    Write-Host "Copia mas reciente: $Archivo" -ForegroundColor Cyan
}

if (-not (Test-Path -LiteralPath $Archivo -PathType Leaf)) {
    throw "No existe el archivo '$Archivo'."
}

# ---- Comprobaciones previas ------------------------------------------------
if (Test-NetConnection -ComputerName localhost -Port 8069 -InformationLevel Quiet) {
    throw "Odoo sigue escuchando en el puerto 8069. Cierra el servidor antes de restaurar."
}
if (-not (Test-NetConnection -ComputerName localhost -Port 5432 -InformationLevel Quiet)) {
    throw "PostgreSQL no responde en localhost:5432. Arranca el servicio 'postgresql-x64-16'."
}

Write-Host ""
Write-Host "Se va a REEMPLAZAR la base de datos '$Database' por el contenido de:" -ForegroundColor Yellow
Write-Host "  $Archivo"
Write-Host "Todo lo que se haya hecho despues de esa copia se perdera." -ForegroundColor Yellow
$respuesta = Read-Host "Escribe SI para continuar"
if ($respuesta -ne "SI") { Write-Host "Cancelado."; return }

& $python (Join-Path $PSScriptRoot "tools\restore_backup.py") $Archivo -d $Database --force
if ($LASTEXITCODE -ne 0) { throw "La restauracion ha fallado (codigo $LASTEXITCODE)." }

Write-Host ""
Write-Host "Restauracion completada. Arranca el servidor con:  .\start-odoo.ps1" -ForegroundColor Green
