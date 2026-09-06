# Motor nativo Odoo: paquete portátil oficial, fijado y verificado por SHA-256.
param([string]$Config = (Join-Path $PSScriptRoot 'odoo.local'))
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'No existe la configuración privada.' }
$runtimeTools = Join-Path (Split-Path (Resolve-Path -LiteralPath $Config).Path -Parent) 'tools'
$binary = Join-Path $runtimeTools 'wkhtmltox/bin/wkhtmltopdf.exe'
if (-not (Test-Path -LiteralPath $binary)) {
    New-Item -ItemType Directory -Path $runtimeTools -Force | Out-Null
    $archive = Join-Path $runtimeTools 'wkhtmltox-0.12.6-win64.7z'
    Invoke-WebRequest -Uri 'https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox-0.12.6-1.mxe-cross-win64.7z' -OutFile $archive
    $expectedHash = '6CE994C89D5F6018FA158E149A2DE8FBBBEB14D8FF5CB656C89893BC556E0557'
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) { throw 'El paquete PDF no coincide con la versión verificada.' }
    & tar -xf $archive -C $runtimeTools
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo extraer el motor PDF.' }
}
$version = & $binary --version
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^wkhtmltopdf 0\.12\.6 \(with patched qt\)$') {
    throw 'El motor PDF no es la versión esperada o no puede ejecutarse.'
}
Write-Output "Motor PDF listo: $version"
