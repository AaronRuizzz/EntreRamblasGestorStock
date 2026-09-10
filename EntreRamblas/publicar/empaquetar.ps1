<#
    Prepara una publicación por versión: pruebas, árbol de distribución,
    paquete .zip, manifiesto y (opcional) firma.

        .\publicar\empaquetar.ps1 -Salida ..\dist [-Firmar "D:\claves\firma-privada.pem"] [-SaltarPruebas]

    Un `git push` normal NO actualiza la tienda. Sólo se distribuyen las
    versiones que salen de aquí y se publican expresamente (ver PUBLICAR.md).
#>
param(
    [string]$Salida = (Join-Path $PSScriptRoot '..\..\dist'),
    [string]$Firmar,
    [switch]$SaltarPruebas
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repo
$python = Join-Path $repo 'venv\Scripts\python.exe'

# --- versión (del manifiesto del módulo) --------------------------------------
$version = (& $python -c "import ast,pathlib;print(ast.literal_eval(pathlib.Path('custom_addons/mi_gestor_stock/__manifest__.py').read_text('utf-8'))['version'])").Trim()
if ($version -notmatch '^\d+(\.\d+){2,4}$') { throw "Versión no válida: $version" }
Write-Host "Empaquetando versión $version" -ForegroundColor Cyan

# --- integridad del motor -----------------------------------------------------
$rev = (Get-Content 'odoo-revision.txt' -Raw).Trim()
if ((& git -C odoo rev-parse HEAD).Trim() -ne $rev) { throw 'La revisión de odoo/ no coincide con odoo-revision.txt.' }
& git -C odoo diff --quiet HEAD
if ($LASTEXITCODE -ne 0) { throw 'El checkout de odoo/ tiene cambios locales.' }

# --- pruebas ----------------------------------------------------------------
if (-not $SaltarPruebas) {
    & (Join-Path $repo 'test.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Las pruebas no pasan; no se publica.' }
}

# --- árbol de distribución --------------------------------------------------
$dist = (New-Item -ItemType Directory -Force -Path $Salida).FullName
$payload = Join-Path $dist 'payload'
if (Test-Path $payload) { Remove-Item $payload -Recurse -Force }
New-Item -ItemType Directory -Force -Path $payload | Out-Null

$incluir = @('custom_addons', 'tools', 'instalador', 'odoo', 'venv', 'odoo-revision.txt',
             'requirements-windows.lock', 'bootstrap.ps1', 'start-odoo.ps1', 'install-pdf.ps1',
             'preparar-equipo.ps1', 'restore-backup.ps1', 'reset-catalogo.ps1', 'service.ps1',
             'recuperar-acceso.ps1', 'diagnostico.ps1', 'test.ps1', 'odoo.conf')
foreach ($item in $incluir) {
    $src = Join-Path $repo $item
    if (-not (Test-Path $src)) { Write-Warning "No está: $item"; continue }
    if (Test-Path $src -PathType Container) {
        robocopy $src (Join-Path $payload $item) /E /NFL /NDL /NJH /NJS /NP `
            /XD '__pycache__' '.git' '.pytest_cache' '.odoo_data' 'sessions' 'filestore' `
            /XF '*.pyc' '*.log' '*.err' 'odoo.local' 'odoo.local.pending' '*.secret' | Out-Null
    } else {
        Copy-Item $src (Join-Path $payload $item) -Force
    }
}
# La clave PÚBLICA de verificación tiene que ir dentro.
if (-not (Test-Path (Join-Path $payload 'instalador\firma-publica.pem'))) {
    throw 'Falta instalador\firma-publica.pem (la clave pública de verificación). Genera las claves con generar-clave-firma.ps1 y copia la pública.'
}

# --- .zip -------------------------------------------------------------------
$zipName = "EntreRamblas-$version.zip"
$zipPath = Join-Path $dist $zipName
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $payload '*') -DestinationPath $zipPath -CompressionLevel Optimal
$sha = (Get-FileHash -Algorithm SHA256 $zipPath).Hash.ToLower()

# --- manifiesto -----------------------------------------------------------
$manifest = [ordered]@{
    version       = $version
    fecha         = (Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ')
    archivo       = $zipName
    sha256        = $sha
    incluye_motor = $true
    requisitos    = [ordered]@{ odoo_revision = $rev; python = '3.12'; so = 'windows' }
    notas         = @("Versión $version de Entre Ramblas - Gestor de stock.")
}
$manifestPath = Join-Path $dist 'manifest.json'
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding utf8

# --- firma --------------------------------------------------------------
if ($Firmar) {
    & $python tools\paquete_firma.py firmar --archivo $manifestPath --clave $Firmar
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo firmar el manifiesto.' }
    & $python tools\paquete_firma.py verificar --archivo $manifestPath --firma "$manifestPath.sig" `
        --clave (Join-Path $payload 'instalador\firma-publica.pem')
    if ($LASTEXITCODE -ne 0) { throw 'La firma generada no verifica con la clave pública incluida.' }
}

Write-Host ''
Write-Host 'Listo:' -ForegroundColor Green
Write-Host "  Paquete   : $zipPath ($sha)"
Write-Host "  Manifiesto: $manifestPath"
if ($Firmar) { Write-Host "  Firma     : $manifestPath.sig" }
Write-Host ''
Write-Host 'Siguiente: compila el instalador (instalador\README.md) y publica'
Write-Host 'manifest.json(.sig) y el .zip en el repositorio de releases (PUBLICAR.md).'
