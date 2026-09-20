<#
    Prepara la carpeta administrada de documentos y su acceso directo.

        preparar-documentos.ps1 -DataDir "%ProgramData%\EntreRamblas" [-CodeDir "%ProgramFiles%\EntreRamblas"]

    Se ejecuta ELEVADO (instalador o actualizador). Idempotente y NO destructivo:
    nunca borra ni mueve archivos.

      * %ProgramData%\EntreRamblas\Documentos con Facturas, Informes y Tickets.
      * LocalService (la cuenta del servicio) puede escribir; los usuarios del
        equipo pueden leer.
      * Acceso directo «Documentos Clavel y Azahar» en el Escritorio comun.

    El servicio de Windows no puede abrir el Explorador en la sesion del
    usuario: por eso la app ya no tiene botones «Abrir carpeta» y el acceso
    es este acceso directo.
#>
param(
    [Parameter(Mandatory = $true)][string]$DataDir,
    [string]$CodeDir = ''
)
$ErrorActionPreference = 'Stop'

$docs = Join-Path $DataDir 'Documentos'
foreach ($name in @('Facturas', 'Informes', 'Tickets')) {
    $sub = Join-Path $docs $name
    if (Test-Path -LiteralPath $sub -PathType Leaf) {
        throw "Hay un archivo donde deberia haber una carpeta: $sub. Renombralo y repite."
    }
    New-Item -ItemType Directory -Force -Path $sub | Out-Null
}

# S-1-5-19 = LocalService (modificar); S-1-5-32-545 = Usuarios (leer y ejecutar);
# S-1-5-32-544 = Administradores y S-1-5-18 = SYSTEM (control total).
& icacls $docs /grant '*S-1-5-19:(OI)(CI)M' '*S-1-5-32-545:(OI)(CI)RX' `
    '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron ajustar los permisos de la carpeta de documentos.' }

$lnk = Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Documentos Clavel y Azahar.lnk'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($lnk)
$link.TargetPath = $docs
$link.Description = 'Facturas, informes y tickets de Clavel y Azahar'
if ($CodeDir) {
    $icon = Join-Path $CodeDir 'instalador\entreramblas.ico'
    if (Test-Path -LiteralPath $icon) { $link.IconLocation = $icon }
}
$link.Save()
Write-Host "Documentos: $docs"
