<#
    Recuperación local del acceso: reinicia el primer acceso de la propietaria
    con un código de activación nuevo (para cuando se han perdido la contraseña
    Y la clave de recuperación).

    Hay que ejecutarlo como ADMINISTRADOR de Windows. No hay contraseña maestra
    compartida; cada uso queda registrado dentro del programa.

    Uso:
        .\recuperar-acceso.ps1 -Config "<ruta a odoo.local>" -Database <base>
        .\recuperar-acceso.ps1 -Config "<ruta a odoo.local>" -Database <base> -Admin
#>
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [ValidatePattern('^[a-z][a-z0-9_]{0,62}$')][string]$Database = 'entre_ramblas',
    [switch]$Admin
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$identity = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Abre PowerShell como administrador y vuelve a ejecutar este script.'
}
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'No existe el archivo de configuración indicado.' }

$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "No se encuentra el entorno virtual: $python" }

$operation = if ($Admin) { 'admin' } else { 'activar' }
& $python (Join-Path $PSScriptRoot 'tools\recuperar_acceso.py') $operation --config $Config --database $Database
if ($LASTEXITCODE -ne 0) { throw 'La recuperación no se completó.' }
