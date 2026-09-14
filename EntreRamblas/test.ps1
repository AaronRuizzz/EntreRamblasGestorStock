# Instancia PostgreSQL de pruebas separada. No modifica mi_base_stock ni el servicio Windows.
param([string]$Tags = '/mi_gestor_stock', [switch]$Restore)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pgBin = 'C:\Program Files\PostgreSQL\18\bin'
$cluster = Join-Path $PSScriptRoot '.odoo_data\validation-postgres'
$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path "$pgBin\pg_ctl.exe")) { throw 'Se requiere PostgreSQL 18 para las pruebas.' }
if (-not (Test-Path "$cluster\PG_VERSION")) {
    & "$pgBin\initdb.exe" -D $cluster -U mgs_test --encoding=UTF8 --locale=C --auth=trust
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la instancia de pruebas.' }
}
& "$pgBin\pg_ctl.exe" -D $cluster status *> $null
$startedHere = $LASTEXITCODE -ne 0
if ($startedHere) {
    & "$pgBin\pg_ctl.exe" -D $cluster -l '.odoo_data\validation-postgres.log' -o '-p 55432 -h 127.0.0.1' start
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar PostgreSQL de pruebas.' }
}
try {
    & $python tools/check_encoding.py
    if ($LASTEXITCODE -ne 0) { throw 'Hay texto mal codificado (mojibake) en el addon.' }
    & $python tools/test_backup_archive.py
    if ($LASTEXITCODE -ne 0) { throw 'Ha fallado la validación de archivos de copia.' }
    & $python tools/prepare_validation.py
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar la base de pruebas.' }
    # Instalación sobre una base REALMENTE vacía: la suite reutiliza
    # mgs_validation y no detectaba que una vista se cargara antes que su
    # acción de informe. Crea y borra una base nueva cada vez.
    & $python tools/check_fresh_install.py --db-host 127.0.0.1 --db-port 55432 --db-user mgs_test
    if ($LASTEXITCODE -ne 0) { throw 'La instalación limpia sobre base vacía ha fallado. Revisa .odoo_data\fresh-install.log.' }
    # --db-filter: la plantilla odoo.conf filtra por ^mi_base_stock$; sin
    # sobrescribirlo, las pruebas HttpCase caen en el selector de bases.
    & $python odoo/odoo-bin -c odoo.conf --db_host=127.0.0.1 --db_port=55432 --db_user=mgs_test `
        -d mgs_validation --db-filter=^mgs_validation$ -i mi_gestor_stock -u mi_gestor_stock --without-demo=all `
        --stop-after-init --test-enable --test-tags $Tags --http-interface=127.0.0.1 --http-port=8075 `
        --logfile=.odoo_data/mgs-validation.log
    if ($LASTEXITCODE -ne 0) { throw 'Las pruebas han fallado. Consulta .odoo_data\mgs-validation.log.' }
    Get-Content .odoo_data/mgs-validation.log -Tail 8
    & $python tools/check_hardware_outbox.py
    if ($LASTEXITCODE -ne 0) { throw 'Ha fallado la prueba transaccional de hardware.' }
    if ($Restore) {
        & $python tools/check_backup_restore.py
        if ($LASTEXITCODE -ne 0) { throw 'Ha fallado la restauración de prueba.' }
    }
} finally {
    if ($startedHere) { & "$pgBin\pg_ctl.exe" -D $cluster -m fast stop }
}
