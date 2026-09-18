#Requires -Version 7
<#
    Prepara una publicación por versión: pruebas, runtime propio, árbol de
    distribución, paquete .zip, manifiesto firmado e integridad.json firmado.

        .\publicar\empaquetar.ps1 -Salida ..\dist [-Firmar "D:\claves\firma-privada.pem"] [-SaltarPruebas]

    Requiere PowerShell 7: PowerShell 5.1 no tiene `Get-Date -AsUTC` y su
    `Set-Content -Encoding utf8` escribe BOM, que rompe el lector del
    actualizador. Aun así, fecha y manifiesto se escriben de forma portable.

    Un `git push` normal NO actualiza la tienda. Sólo se distribuyen las
    versiones que salen de aquí y se publican expresamente (ver PUBLICAR.md).
#>
param(
    [string]$Salida = (Join-Path $PSScriptRoot '..\..\dist'),
    [string]$Firmar,
    [string]$PythonBase,
    [switch]$SaltarPruebas
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repo
$python = Join-Path $repo 'venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "No hay entorno en venv\; prepáralo antes de publicar." }

# --- versión (del manifiesto del módulo) --------------------------------------
$version = (& $python -c "import ast,pathlib;print(ast.literal_eval(pathlib.Path('custom_addons/mi_gestor_stock/__manifest__.py').read_text('utf-8'))['version'])").Trim()
if ($version -notmatch '^\d+(\.\d+){2,4}$') { throw "Versión no válida: $version" }
Write-Host "Empaquetando versión $version" -ForegroundColor Cyan

# --- integridad del motor (commit fijado) ------------------------------------
$rev = (Get-Content 'odoo-revision.txt' -Raw).Trim()
$engineReport = (& $python (Join-Path $repo 'tools/verificar_motor.py')) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "El motor de odoo/ no está íntegro; no se publica:`n$engineReport" }
Write-Host "Motor Odoo: $engineReport" -ForegroundColor DarkGray

# --- pruebas ----------------------------------------------------------------
if (-not $SaltarPruebas) {
    & (Join-Path $repo 'test.ps1') -Restore
    if ($LASTEXITCODE -ne 0) { throw 'Las pruebas no pasan; no se publica.' }
}

# --- árbol de distribución --------------------------------------------------
$dist = (New-Item -ItemType Directory -Force -Path $Salida).FullName
$payload = Join-Path $dist 'payload'
if (Test-Path $payload) { Remove-Item $payload -Recurse -Force }
New-Item -ItemType Directory -Force -Path $payload | Out-Null

# `venv` NO viaja: se construye en destino desde el CPython vendorizado.
$incluir = @('custom_addons', 'tools', 'instalador', 'odoo', 'odoo-revision.txt',
             'requirements-windows.lock', 'bootstrap.ps1', 'start-odoo.ps1', 'install-pdf.ps1',
             'preparar-equipo.ps1', 'restore-backup.ps1', 'reset-catalogo.ps1', 'service.ps1',
             'recuperar-acceso.ps1', 'diagnostico.ps1', 'test.ps1', 'odoo.conf')
foreach ($item in $incluir) {
    $src = Join-Path $repo $item
    if (-not (Test-Path $src)) { Write-Warning "No está: $item"; continue }
    if (Test-Path $src -PathType Container) {
        # 'tests': ni el motor Odoo ni mi_gestor_stock los necesitan para
        # arrancar en producción (Odoo solo importa el paquete `tests` de un
        # módulo en modo test, nunca en un arranque normal) — sin excluirlos
        # aquí, algunos ficheros de prueba de módulos nativos (rutas de
        # ejemplo con nombres largos, p. ej. account_edi_ubl_cii) superan el
        # límite clásico de 260 caracteres de Windows y el instalador falla
        # al comprimirlos con "no se puede encontrar la ruta especificada".
        robocopy $src (Join-Path $payload $item) /E /NFL /NDL /NJH /NJS /NP `
            /XD '__pycache__' '.git' '.pytest_cache' '.odoo_data' 'sessions' 'filestore' 'tests' `
            /XF '*.pyc' '*.log' '*.err' 'odoo.local' 'odoo.local.pending' '*.secret' | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy falló copiando $item" }
    } else {
        Copy-Item $src (Join-Path $payload $item) -Force
    }
}
if (-not (Test-Path (Join-Path $payload 'instalador\firma-publica.pem'))) {
    throw 'Falta instalador\firma-publica.pem. Genera las claves con generar-clave-firma.ps1 y copia la pública.'
}

# --- runtime Python propio (CPython base + ruedas offline) -------------------
Write-Host 'Runtime Python: copiando CPython base y descargando ruedas...' -ForegroundColor DarkGray
if (-not $PythonBase) {
    $PythonBase = (& $python -c "import sys;print(sys.base_prefix)").Trim()
}
if (-not (Test-Path (Join-Path $PythonBase 'python.exe'))) {
    throw "No se encuentra un CPython base en '$PythonBase'. Indica -PythonBase."
}
$pyVer = (& (Join-Path $PythonBase 'python.exe') -c "import sys;print('%d.%d'%sys.version_info[:2])").Trim()
if ($pyVer -ne '3.12') { throw "El CPython base es $pyVer; se requiere 3.12." }
$payloadPython = Join-Path $payload 'python'
# El CPython base completo, sin site-packages (las dependencias van en wheels\)
# ni Scripts\ (se recrean con el venv). Lib\venv y Lib\ensurepip SÍ viajan.
robocopy $PythonBase $payloadPython /E /NFL /NDL /NJH /NJS /NP `
    /XD '__pycache__' 'Lib\site-packages' /XF '*.pyc' | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'No se pudo copiar el CPython base.' }
New-Item -ItemType Directory -Force -Path (Join-Path $payload 'wheels') | Out-Null
# `pip wheel` (no `pip download --only-binary=:all:`): algunas dependencias
# del lock (p. ej. docopt, del que depende num2words) nunca han publicado
# rueda en PyPI, solo el paquete fuente — con --only-binary=:all: esa
# descarga falla siempre, para cualquier versión. `pip wheel` prefiere la
# rueda ya publicada cuando existe (la inmensa mayoría, ya vienen
# precompiladas para Windows) y, si no hay, la construye aquí mismo a
# partir del fuente: el resultado en wheels\ es siempre .whl puro, que es
# lo único que necesita la instalación sin conexión en la tienda.
& $python -m pip wheel --disable-pip-version-check `
    -r (Join-Path $repo 'requirements-windows.lock') -w (Join-Path $payload 'wheels')
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron preparar todas las ruedas del lock.' }

# --- integridad.json (mapa hashes) + firma ---------------------------------
& $python (Join-Path $repo 'tools/generar_integridad.py') --root $payload `
    --salida (Join-Path $payload 'integridad.json')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar integridad.json.' }
if ($Firmar) {
    & $python (Join-Path $repo 'tools/paquete_firma.py') firmar `
        --archivo (Join-Path $payload 'integridad.json') --clave $Firmar
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo firmar integridad.json.' }
    & $python (Join-Path $repo 'tools/paquete_firma.py') verificar `
        --archivo (Join-Path $payload 'integridad.json') --firma (Join-Path $payload 'integridad.json.sig') `
        --clave (Join-Path $payload 'instalador\firma-publica.pem')
    if ($LASTEXITCODE -ne 0) { throw 'integridad.json.sig no verifica con la clave pública incluida.' }
}

# --- .zip (ZipFile, no Compress-Archive: árbol grande, sin límite de 2 GB) ---
$zipName = "Gestor-Stock-Clavel-Y-Azahar-$version.zip"
$zipPath = Join-Path $dist $zipName
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $payload, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $false)
$sha = (Get-FileHash -Algorithm SHA256 $zipPath).Hash.ToLower()
$zipBytes = (Get-Item $zipPath).Length
$treeBytes = (Get-ChildItem $payload -Recurse -File | Measure-Object -Sum Length).Sum

# --- URL de descarga (predecible: convención tag=v<version>, mismo nombre
# de archivo) ---------------------------------------------------------------
# El .zip NO se comitea al repo de releases (supera el límite de 100 MiB de
# GitHub para archivos normales): se sube como *release asset* (hasta 2 GiB).
# La URL es calculable de antemano; publicar-release.ps1 solo tiene que subir
# el asset con este mismo nombre exacto bajo este mismo tag.
$repoReleases = 'AaronRuizzz/EntreRamblasReleases'
$downloadUrl = "https://github.com/$repoReleases/releases/download/v$version/$zipName"

# --- manifiesto (fecha y UTF-8 sin BOM portables) --------------------------
$manifest = [ordered]@{
    version          = $version
    fecha            = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
    archivo          = $zipName
    download_url     = $downloadUrl
    sha256           = $sha
    tamano           = $zipBytes
    tamano_instalado = $treeBytes
    incluye_motor    = $true
    unidad_version   = @('odoo', 'custom_addons', 'tools', 'instalador', 'python',
                         'wheels', 'requirements-windows.lock', 'odoo-revision.txt',
                         'integridad.json', 'integridad.json.sig')
    requisitos       = [ordered]@{ odoo_revision = $rev; python = '3.12'; so = 'windows' }
    notas            = @("Versión $version de Gestor Stock Clavel Y Azahar.")
}
$manifestPath = Join-Path $dist 'manifest.json'
$json = $manifest | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($manifestPath, $json, (New-Object System.Text.UTF8Encoding($false)))

# El manifiesto se lee con el MISMO lector de la aplicación: sin BOM.
& $python (Join-Path $repo 'tools/check_manifest_encoding.py') --archivo $manifestPath
if ($LASTEXITCODE -ne 0) { throw 'El manifiesto no lo lee el actualizador (¿BOM?).' }

# --- firma del manifiesto -------------------------------------------------
if ($Firmar) {
    & $python (Join-Path $repo 'tools/paquete_firma.py') firmar --archivo $manifestPath --clave $Firmar
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo firmar el manifiesto.' }
    & $python (Join-Path $repo 'tools/paquete_firma.py') verificar --archivo $manifestPath --firma "$manifestPath.sig" `
        --clave (Join-Path $payload 'instalador\firma-publica.pem')
    if ($LASTEXITCODE -ne 0) { throw 'La firma generada no verifica con la clave pública incluida.' }
}

# --- versión del instalador (Inno) ---------------------------------------
$issVersion = Join-Path $dist 'version.iss'
[System.IO.File]::WriteAllText($issVersion, "#define AppVersion `"$version`"`r`n",
    (New-Object System.Text.UTF8Encoding($false)))

Write-Host ''
Write-Host 'Listo:' -ForegroundColor Green
Write-Host "  Paquete   : $zipPath ($sha)"
Write-Host "  Descarga  : $downloadUrl"
Write-Host "  Manifiesto: $manifestPath"
if ($Firmar) { Write-Host "  Firmas    : $manifestPath.sig  +  payload\integridad.json.sig" }
Write-Host ''
Write-Host 'Siguiente: .\publicar\publicar-release.ps1 compila el instalador, crea la'
Write-Host 'release en GitHub con este .zip como asset, y publica manifest.json el'
Write-Host 'último (ver PUBLICAR.md). Este script ya ha dejado todo listo para eso.'
