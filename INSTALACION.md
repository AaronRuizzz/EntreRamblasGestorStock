# Instalación y recuperación

Estado de la entrega y pruebas: [IMPLEMENTACION.md](IMPLEMENTACION.md).
Esta guía sustituye los comandos históricos del README. La puesta en servicio
de la tienda sigue pendiente de completar la aceptación allí indicada.

## Preparar un equipo

Requisitos: Windows, Python 3.12, Git y PostgreSQL. La validación usa PostgreSQL
18. El rol PostgreSQL de la aplicación debe tener contraseña propia y permiso
CREATEDB para instalar/recuperar, sin ser superusuario. Los ensayos aislados en
puerto 55432 usan otro rol y no son la configuración de producción.

Clonar el proyecto en una carpeta local fuera de OneDrive. Ejecutar los comandos
desde `EntreRamblas`. El instalador descarga la revisión exacta de
`odoo-revision.txt` si falta Odoo, y aplica `requirements-windows.lock`.
Conserva el checkout si ya existe: si su revisión difiere, se detiene.

Crear primero la configuración privada. Si se reutiliza un archivo existente:

```powershell
py -3.12 tools/configure_runtime.py --directory "$env:LOCALAPPDATA/EntreRamblas" --source odoo.local --db-user odoo --db-port 5432
```

En un equipo nuevo, establecer temporalmente `MGS_DB_PASSWORD` con la contraseña
del rol PostgreSQL y omitir `--source`. La contraseña no se pasa como argumento.
Borrar después esa variable del entorno. Se puede indicar `--pg-bin` si hay
varias instalaciones de PostgreSQL. No se crea ni modifica el rol PostgreSQL.

La herramienta requiere una carpeta nueva o vacía, la protege con permisos para
el usuario actual, SYSTEM y administradores, y crea `odoo.local`. Los datos y
el registro quedan dentro de esa carpeta. No sobrescribe archivos existentes.

```powershell
.\bootstrap.ps1 -Config "$env:LOCALAPPDATA/EntreRamblas/odoo.local" -Database entre_ramblas
.\start-odoo.ps1 -Config "$env:LOCALAPPDATA/EntreRamblas/odoo.local" -Database entre_ramblas
```

El servidor escucha solo en `127.0.0.1:8069`. La instalación no abre HTTP hasta
completarse. Genera el usuario inicial `propietaria` y una contraseña aleatoria
en `entre_ramblas-first-access.secret`, junto a la configuración. Guardar ese
acceso de forma privada y cambiar la contraseña desde las preferencias.
No se incluyen contraseñas en Git ni se cambian cuentas de bases existentes.

Antes de abrir caja: completar identidad y correo de la propietaria, datos
reales de la empresa, configuración contable/fiscal aplicable, métodos de pago,
impresora, SSD y usuario de dependienta. No se inventan estos datos al instalar.
La impresión automática queda desactivada hasta configurar los dispositivos.

Si falla la instalación, `odoo.local.pending` bloquea el arranque. Conservar el
registro para diagnóstico. No borrar ese marcador para saltarse un fallo: el
alta inicial y el módulo deben estar completados. El instalador no borra bases.

## Actualizar

Con el servidor parado y una copia verificada:

```powershell
.\start-odoo.ps1 -Config "$env:LOCALAPPDATA/EntreRamblas/odoo.local" -Database entre_ramblas -Update mi_gestor_stock
```

Una actualización fallida impide el arranque posterior. La base seleccionada y
su filtro se mantienen al arrancar. No se cambia la revisión Odoo implícitamente.

## Recuperar una copia

Conservar juntos el `.zip` y su `.zip.sha256`. La recuperación requiere el código
y entorno de este proyecto; el ZIP contiene base y adjuntos, no los ejecutables.
Usar una base nueva:

```powershell
.\restore-backup.ps1 -Config "$env:LOCALAPPDATA/EntreRamblas/odoo.local" -Archivo 'E:/CopiasEntreRamblas/copia.zip' -Database entre_ramblas_recuperada
```

La herramienta rechaza sobrescribir una base o filestore existente y verifica
la integridad antes de crear el destino. `-AllowLegacy` acepta expresamente una
copia antigua sin SHA-256, pero mantiene las comprobaciones ZIP y de estructura.

La base recuperada tiene tareas automáticas e impresión automática desactivadas.
Los trabajos pendientes de impresora/cajón se marcan inciertos. Comprobar
existencias, ventas recientes, adjuntos, usuarios, métodos de pago y dispositivos;
configurar la carpeta de copias y el SSD y reactivar las tareas pertinentes antes
de usarla. Conservar la base original hasta completar esta revisión.

## Pruebas del proyecto

```powershell
.\test.ps1
.\test.ps1 -Restore
```

Usan PostgreSQL aislado en puerto 55432, base `mgs_validation`, transporte de
hardware simulado y datos de prueba. `-Restore` añade copia y recuperación reales
a una base temporal. No sustituyen la jornada de aceptación con los equipos.

Pendiente: aceptación del servicio desde Windows y procedimiento final de
activación en la tienda. No considerar el arranque manual como aceptación del
servicio automático.

## Servicio Windows

El código está preparado; el ensayo de registro real requiere privilegios de
administrador y sigue pendiente. Se ha probado el mismo supervisor arrancando
Odoo, respondiendo HTTP y deteniéndolo limpiamente por su canal privado.

Usar una instalación fuera de OneDrive y una configuración sin `dev_mode`, con
`workers = 0` y `http_interface = 127.0.0.1`. Detener primero el arranque manual.
En PowerShell **como administrador**, consultar el nombre real de PostgreSQL:

```powershell
Get-Service *postgres*
.\service.ps1 -Action install -Config "$env:LOCALAPPDATA/EntreRamblas/odoo.local" -Database entre_ramblas -PostgreSQLService postgresql-x64-18
.\service.ps1 -Action start
.\service.ps1 -Action status
```

Sustituir `postgresql-x64-18` si el nombre mostrado es distinto. La configuración
y base quedan fijadas al instalar. No se cambia un servicio existente por pasar
otro `-Config` a `start`. El instalador no reemplaza servicios ya registrados.

Arranca automáticamente con retraso y depende del servicio PostgreSQL. Usa la
cuenta limitada LocalService: se le concede lectura/ejecución sobre el código,
Python y Git, y modificación sobre la carpeta privada del runtime. No se guarda
una contraseña de cuenta Windows. Las impresoras deben estar accesibles para
esa cuenta; la instalación por usuario de una impresora aún necesita aceptación
física. No se comparte el servidor HTTP por la red.

Ante una salida inesperada, Windows tiene configurados dos reintentos (120 y 180
segundos); después se detiene. Revisar `odoo.log`, `service-process.log` y el visor
de eventos antes de reiniciar manualmente. La parada puede tardar alrededor de
un minuto por el bucle interno de Odoo; a los 100 segundos el supervisor registra
el fallo y fuerza la terminación. Esto último requiere revisar la última operación.
El tiempo de reintento permite terminar a un proceso cuyo supervisor haya caído.
Se solicita un aviso previo al apagado de Windows con margen de 120 segundos;
su comportamiento real debe verificarse en la aceptación del servicio.

```powershell
.\service.ps1 -Action stop
.\service.ps1 -Action status
```

Esperar a que aparezca «Detenido» antes de actualizar. Después de actualizar,
arrancar el servicio; no dejar simultáneamente el lanzador manual. Para retirar
el servicio detenido: `service.ps1 -Action remove`. Los datos no se borran y los
permisos concedidos a LocalService se conservan.

Actualizar sin arrancar una segunda instancia manual:

```powershell
.\start-odoo.ps1 -Config "$env:LOCALAPPDATA/EntreRamblas/odoo.local" -Database entre_ramblas -Update mi_gestor_stock -NoStart
.\service.ps1 -Action start
```

Aceptación pendiente en consola elevada: registrar, arrancar, autenticarse,
detener sin forzar, reiniciar Windows y comprobar el arranque automático;
simular fallo controlado del proceso y comprobar los reintentos. No realizar
el ensayo de fallo durante una venta o copia real.

## Motor de informes PDF

Las instalaciones nuevas descargan y comprueban el motor portátil wkhtmltopdf
0.12.6 con Qt parcheado. Para añadirlo a una instalación existente:

```powershell
.\install-pdf.ps1 -Config "$env:LOCALAPPDATA/EntreRamblas/odoo.local"
```

Se guarda junto a la configuración, bajo `tools/wkhtmltox`, y el lanzador lo
añade al PATH de Odoo. Reiniciar Odoo después de instalarlo. El instalador fija
el paquete Windows x64 de la [descarga oficial](https://wkhtmltopdf.org/downloads)
y comprueba su SHA-256 antes de extraerlo. La necesidad de la versión con Qt
parcheado está descrita en la [guía de Odoo](https://github.com/odoo/odoo/wiki/Wkhtmltopdf).
El motor se usa para plantillas internas del informe, no para convertir HTML
aportado libremente por usuarios.
