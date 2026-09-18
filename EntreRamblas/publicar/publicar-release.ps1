#Requires -Version 7
<#
    Publica una versión de extremo a extremo, en el orden que importa:
    comprobar -> pruebas -> empaquetar -> firmar -> compilar instalador ->
    crear la release en GitHub y subir los assets -> comprobar que responden
    -> publicar manifest.json el ÚLTIMO.

    Ese orden no es arbitrario: hasta que el manifiesto no apunta a una
    release que YA existe y responde, ningún cliente debe poder verlo (así
    es como `tools/actualizador.py comprobar` decide si hay una versión
    nueva). Publicar el manifiesto antes que los assets dejaría, durante la
    ventana entre los dos pasos, un canal que promete una actualización que
    todavía no se puede descargar.

        .\publicar\publicar-release.ps1 -Firmar "D:\claves\firma-privada.pem"

    Requiere PowerShell 7, y en PATH: git, gh (autenticado como
    AaronRuizzz) e ISCC.exe (Inno Setup 6, o indícalo con -Iscc).

    Un `git push` normal al repo de desarrollo NO publica nada: solo esto
    (o los pasos manuales de PUBLICAR.md) lo hace.
#>
param(
    [Parameter(Mandatory = $true)][string]$Firmar,
    [string]$Salida = (Join-Path $PSScriptRoot '..\..\dist'),
    [string]$Iscc,
    [string]$ReleasesRepoDir,
    [string]$PythonBase,
    [switch]$SaltarPruebas
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repo
$python = Join-Path $repo 'venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "No hay entorno en venv\; prepáralo antes de publicar." }

$repoReleases = 'AaronRuizzz/EntreRamblasReleases'
$repoReleasesUrl = "https://github.com/$repoReleases"
$rawBase = "https://raw.githubusercontent.com/$repoReleases/main"

function Test-VersionIsNewer($candidato, $actual) {
    $c = $candidato -split '\.' | ForEach-Object { [int]$_ }
    $a = $actual -split '\.' | ForEach-Object { [int]$_ }
    for ($i = 0; $i -lt [Math]::Max($c.Count, $a.Count); $i++) {
        $cv = if ($i -lt $c.Count) { $c[$i] } else { 0 }
        $av = if ($i -lt $a.Count) { $a[$i] } else { 0 }
        if ($cv -ne $av) { return $cv -gt $av }
    }
    return $false
}

# --- 1. Árbol limpio y versión --------------------------------------------
Write-Host '1. Comprobando árbol git y versión...' -ForegroundColor Cyan
$sucio = git status --porcelain
if ($sucio) { throw "El árbol de trabajo no está limpio:`n$sucio`nCommitea o descarta los cambios antes de publicar." }

$version = (& $python -c "import ast,pathlib;print(ast.literal_eval(pathlib.Path('custom_addons/mi_gestor_stock/__manifest__.py').read_text('utf-8'))['version'])").Trim()
if ($version -notmatch '^\d+(\.\d+){2,4}$') { throw "Versión no válida: $version" }

try {
    $manifiestoPublicado = Invoke-RestMethod -Uri "$rawBase/manifest.json" -TimeoutSec 15 -ErrorAction Stop
    $versionPublicada = $manifiestoPublicado.version
    if ($versionPublicada -and -not (Test-VersionIsNewer $version $versionPublicada)) {
        throw "La versión $version no es mayor que la ya publicada ($versionPublicada). Sube el número en __manifest__.py."
    }
    Write-Host "   Versión publicada actualmente: $versionPublicada -> nueva: $version" -ForegroundColor DarkGray
} catch [System.Net.WebException], [Microsoft.PowerShell.Commands.HttpResponseException] {
    Write-Host "   No se encontró manifiesto publicado (probablemente el primer release): $version" -ForegroundColor DarkGray
}

# --- 2. gh autenticado como AaronRuizzz ------------------------------------
Write-Host '2. Comprobando sesión de GitHub CLI...' -ForegroundColor Cyan
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "No se encuentra 'gh' (GitHub CLI) en PATH. Instálalo (winget install GitHub.cli) antes de publicar."
}
$authStatus = & gh auth status 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    throw "gh no tiene ninguna sesión activa. Ejecuta 'gh auth login' como AaronRuizzz antes de publicar.`n$authStatus"
}
if ($authStatus -notmatch 'account\s+AaronRuizzz\b') {
    throw "gh está autenticado, pero no como AaronRuizzz:`n$authStatus`nEjecuta 'gh auth switch' (o 'gh auth login') con esa cuenta antes de publicar."
}
Write-Host '   Sesión de gh: AaronRuizzz' -ForegroundColor DarkGray

# --- 3. Empaquetar (pruebas + zip + manifest + firmas + version.iss) ------
Write-Host '3. Empaquetando (pruebas, zip, manifiesto, firmas)...' -ForegroundColor Cyan
# Splatting por HASHTABLE, no por array: un array de tokens sueltos
# ('-SaltarPruebas' como elemento de texto) no liga bien el switch en esta
# versión de PowerShell — el binder trata el primer elemento como valor
# posicional en vez de como nombre de parámetro. Con hashtable no falla.
$empaquetarArgs = @{ Salida = $Salida; Firmar = $Firmar }
if ($PythonBase) { $empaquetarArgs['PythonBase'] = $PythonBase }
if ($SaltarPruebas) { $empaquetarArgs['SaltarPruebas'] = $true }
& (Join-Path $repo 'publicar\empaquetar.ps1') @empaquetarArgs
if ($LASTEXITCODE -ne 0) { throw 'empaquetar.ps1 falló; revisa el mensaje de arriba.' }

$dist = (Resolve-Path $Salida).Path
$manifestPath = Join-Path $dist 'manifest.json'
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$zipPath = Join-Path $dist $manifest.archivo
if (-not (Test-Path $zipPath)) { throw "No se encuentra el paquete esperado: $zipPath" }

# --- 4. Compilar el instalador ---------------------------------------------
Write-Host '4. Compilando el instalador...' -ForegroundColor Cyan
if (-not $Iscc) {
    # winget instala Inno Setup por usuario (%LocalAppData%\Programs) si la
    # sesión no está elevada, o en Program Files (x86) si lo está: se prueban
    # las dos ubicaciones habituales antes de rendirse.
    $candidatos = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe'
    )
    $Iscc = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Iscc -or -not (Test-Path $Iscc)) {
    throw "No se encuentra ISCC.exe. Instala Inno Setup 6 (winget install JRSoftware.InnoSetup) o indica -Iscc <ruta>."
}
& $Iscc (Join-Path $repo 'instalador\EntreRamblas-Setup.iss')
if ($LASTEXITCODE -ne 0) { throw 'La compilación del instalador falló.' }
$exePath = Join-Path $dist 'Gestor-Stock-Clavel-Y-Azahar-Setup.exe'
if (-not (Test-Path $exePath)) { throw "No se encuentra el instalador compilado: $exePath" }

# --- 5. Release en GitHub + assets -----------------------------------------
Write-Host '5. Creando la release en GitHub y subiendo los assets...' -ForegroundColor Cyan
$tag = "v$version"
& gh release create $tag $zipPath $exePath `
    --repo $repoReleases --title $version `
    --notes ("Gestor Stock Clavel Y Azahar $version.`n`n" + ($manifest.notas -join "`n"))
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo crear la release '$tag' en $repoReleases. " +
          "¿Existe ya el repositorio? (ver PUBLICAR.md, Fase 8 del plan de instalación)."
}

# --- 6. Verificar que los assets responden ----------------------------------
Write-Host '6. Verificando que los assets publicados responden...' -ForegroundColor Cyan
foreach ($url in @($manifest.download_url, "$repoReleasesUrl/releases/download/$tag/Gestor-Stock-Clavel-Y-Azahar-Setup.exe")) {
    $resp = Invoke-WebRequest -Uri $url -Method Head -MaximumRedirection 5 -ErrorAction Stop
    if ($resp.StatusCode -ne 200) { throw "El asset no responde 200: $url" }
    Write-Host "   OK: $url" -ForegroundColor DarkGray
}

# --- 7. Publicar manifest.json el ÚLTIMO -----------------------------------
Write-Host '7. Publicando manifest.json (el último paso)...' -ForegroundColor Cyan
if (-not $ReleasesRepoDir) { $ReleasesRepoDir = Join-Path $dist 'EntreRamblasReleases' }
if (Test-Path (Join-Path $ReleasesRepoDir '.git')) {
    git -C $ReleasesRepoDir fetch origin main
    git -C $ReleasesRepoDir checkout main
    git -C $ReleasesRepoDir reset --hard origin/main
} else {
    if (Test-Path $ReleasesRepoDir) { Remove-Item $ReleasesRepoDir -Recurse -Force }
    git clone "https://github.com/$repoReleases.git" $ReleasesRepoDir
    # No se confía en `init.defaultBranch` del equipo (aquí vale 'master'):
    # el primer commit de este repo tiene que llamarse 'main' sí o sí, o el
    # resto del script (y el actualizador, que lee de la rama 'main') no lo
    # encuentra. `checkout -B` la crea si no existe (repo recién clonado y
    # todavía sin ningún commit) o la deja tal cual si ya existía.
    git -C $ReleasesRepoDir checkout -B main
}
Copy-Item $manifestPath (Join-Path $ReleasesRepoDir 'manifest.json') -Force
Copy-Item "$manifestPath.sig" (Join-Path $ReleasesRepoDir 'manifest.json.sig') -Force
git -C $ReleasesRepoDir add manifest.json manifest.json.sig
$hayCambios = git -C $ReleasesRepoDir status --porcelain
if (-not $hayCambios) {
    Write-Host '   manifest.json ya estaba al día; nada que publicar.' -ForegroundColor DarkGray
} else {
    git -C $ReleasesRepoDir -c user.name='AaronRuizzz' -c user.email='aaron.r.m@um.es' `
        commit -m "Versión $version"
    git -C $ReleasesRepoDir push origin main
}

Write-Host ''
Write-Host "Publicado: Gestor Stock Clavel Y Azahar $version" -ForegroundColor Green
Write-Host "  Release  : $repoReleasesUrl/releases/tag/$tag"
Write-Host "  Paquete  : $($manifest.download_url)"
Write-Host "  Canal    : $rawBase/manifest.json"
