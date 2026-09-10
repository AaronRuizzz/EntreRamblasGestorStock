<#
    Genera la pareja de claves Ed25519 que firma las actualizaciones.
    Se hace UNA sola vez y SIN conexión.

        .\publicar\generar-clave-firma.ps1 -Directorio "D:\claves-entreramblas"

    Después:
      * mueve firma-privada.pem a un soporte seguro FUERA del repo y del PC de
        la tienda (una memoria USB guardada bajo llave, un gestor de secretos…);
      * copia firma-publica.pem a instalador\firma-publica.pem y haz commit de
        ESA (la pública) — es lo único que necesita el actualizador.
#>
param([Parameter(Mandatory = $true)][string]$Directorio)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot\..
$python = Join-Path (Get-Location) 'venv\Scripts\python.exe'
& $python tools\paquete_firma.py generar-claves --directorio $Directorio
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron generar las claves.' }
