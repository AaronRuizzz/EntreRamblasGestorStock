# Traspaso a otra IA — gestor de stock Entre Ramblas

Fecha: 6 de septiembre de 2026. El usuario ha pedido detener el desarrollo,
documentar los pendientes y cerrar el goal para continuar con otra IA.
**Este cierre es administrativo: el proyecto NO está terminado ni listo para
producción. El último bloque añadido tiene una prueba fallida.**

## 1. Objetivo y decisiones que se deben conservar

Odoo 18 Community para una floristería, un PC Windows local. Stock por partidas,
caducidad, costes históricos, recepción, TPV, devoluciones, mermas, recuentos,
reposición, estadísticas, roles y copias recuperables. Interfaz en español y
periodos Europe/Madrid. Hardware acordado: Honeywell 1472g, lector PcCom,
Approx appPOS80AM, cajón CASH01 y SSD Corsair. Datáfono independiente: Odoo
registra tarjeta, no cobra/reembolsa por API. Sin ramos, encargos ni nube.

El usuario eligió Astra con razonamiento medio por los límites de su plan.
No necesita que se vuelva a negociar el plan. Continuar desde los archivos
actuales, conservando el trabajo y verificando las afirmaciones anteriores.

## 2. Rutas, entorno y protección de datos

- Raíz Git: `C:/Users/ruben/OneDrive/Escritorio/FoodGuard/gestorStockFloristeria/EntreRamblasGestorStock`.
- Runtime: subcarpeta `EntreRamblas` de esa raíz.
- Addon: `EntreRamblas/custom_addons/mi_gestor_stock`.
- Python: `EntreRamblas/venv/Scripts/python.exe`, Python 3.12.0.
- Odoo: `EntreRamblas/odoo`, checkout ignorado por Git, revisión fijada
  `167e83374756c4c38bc46eb96763dfbd8cb8de6f`.
- PostgreSQL 18: `C:/Program Files/PostgreSQL/18/bin`.
- Base principal `mi_base_stock` en puerto 5432: **no se ha actualizado ni borrado**.
  No actualizarla para probar estos cambios.
- Base de pruebas `mgs_validation`, clúster aislado en
  `EntreRamblas/.odoo_data/validation-postgres`, puerto 55432, usuario `mgs_test`.
  Autenticación trust restringida al localhost, solo para datos sintéticos.
- `.odoo_data` contiene logs, filestore y evidencias ignorados por Git.
- `odoo.conf` es una plantilla sin secretos. Conserva filtro `^mi_base_stock$`:
  al iniciar HTTP de pruebas hay que pasar explícitamente el filtro correcto.
- Configuración privada anterior en `odoo.local` ignorado. No copiar credenciales
  a documentación, Git o archivos de traspaso.
- Instalaciones privadas de ensayo bajo `$env:LOCALAPPDATA/EntreRamblasValidation`;
  algunas rutas se redirigen por el paquete MSIX de Codex. Localizar las rutas
  reales antes de usarlas. Bases de ensayo: `mgs_install_validation` y
  `mgs_install_validation_v2` en 55432.
- Hay muchos archivos modificados y nuevos **sin commit**. Son la implementación
  actual. No ejecutar reset/clean ni descartar los archivos sin seguimiento.
  No se han encontrado instrucciones AGENTS.md en las revisiones anteriores.

Documentación adicional: `IMPLEMENTACION.md` (cronología y evidencias),
`INSTALACION.md`, `INFORMES.md`, `RECUENTOS.md`, `DEVOLUCIONES.md`, `README.md`.
Las casillas iniciales de IMPLEMENTACION son un resumen histórico; los apartados
posteriores y las limitaciones de este traspaso prevalecen sobre un simple [X].

## 3. Punto exacto de interrupción: existencias iniciales, FALLANDO

Se han añadido, sin terminar:

- `models/mgs_opening_stock.py`: modelos persistentes `mgs.opening.stock` y línea.
- `views/mgs_opening_stock_views.xml`: formulario/lista y reglas de compañía.
- Menú Stock → Existencias iniciales; ACL para propietaria; imports y manifest.
- `tests/test_opening_stock.py`: dos pruebas, importadas en tests/__init__.py.

Intención: registrar stock de apertura con partidas automáticas y coste/caducidad,
como ajuste de inventario (origen inventory), sin compras ficticias. Exige revisión
por línea, cantidades positivas y costes finitos no negativos. Crea un lote por
línea, guarda enlace a movimiento, autor/fecha; segunda aplicación idempotente.
Rechaza productos con movimientos terminados o quants no nulos en la compañía.
Bloquea edición/borrado tras aplicar. Actualmente solo admite productos del
catálogo con tracking lot y mgs_auto_lots, no crea catálogo ni importa CSV.

Último comando desde runtime:

```powershell
.\test.ps1 -Tags /mi_gestor_stock:TestOpeningStock
```

Resultado real, log 2026-09-06 01:33:54 UTC:

```text
FAIL: TestOpeningStock.test_opening_is_inventory_and_idempotent
tests/test_opening_stock.py, line 24
self.assertEqual(self.product.qty_available, 8)
AssertionError: 0.0 != 8
1 failed, 0 error(s) of 2 tests
```

La instalación de XML/modelos sí terminó. El test de permisos/revisión pasó.
No se ha diagnosticado aún la causa del cero: inspeccionar movimientos, líneas,
quants y contexto de ubicación del producto; no cambiar la aserción sin demostrar
las existencias reales. La ubicación de ensayo es interna creada sin almacén:
también comprobar si qty_available está limitado por contexto de almacén. Es una
hipótesis, no un diagnóstico. No se han ejecutado aún las aserciones posteriores
de ese test, ni se ha probado el formulario en navegador.

Antes de cerrar este bloque: corregir el fallo, comprobar ajuste/coste/lotes,
caducidad Madrid, exclusión de compras en informe, dos aplicaciones y dos
aperturas distintas del mismo producto, permisos y compañía, rechazo de datos
inválidos, carreras con recepción/venta y persistencia en formulario. La exclusión
de productos con stock previo debe funcionar también bajo concurrencia; el
bloqueo actual de product_product no demuestra por sí solo que los otros flujos
usen el mismo bloqueo. Revisar esa coordinación.

## 4. Lo implementado y evidencia disponible

### Stock y TPV

- `mgs_reception.py`, `mgs_stock_lot.py`: recepción nativa, partida por línea,
  proveedor/fecha/coste congelados, protección de doble confirmación. Rechaza
  activar lotes cuando queda stock sin lote. No convertir datos viejos a ciegas.
- `mgs_pos_stock.py`: FEFO y después antigüedad, bloqueos de quant, rechazo de
  caducados/insuficientes, coste histórico, retornos originales parciales limitados.
  Movimientos en tiempo real. Venta de dependienta usando sudo interno controlado.
- `pos_validation.js`: comprobación de stock antes del cobro y al validar;
  confirmación de datáfono; resultado incierto conserva UUID y evita repetir cobro.
- `mgs_scrap.py`: baja nativa, motivo, lote, actor, costes y límites de disponible.
- `mgs_inventory_count.py`: foto de quants conocidos, cantidad/revisión explícitas,
  rechazo si cambia stock/reservas, ajuste solo de diferencias, cancelación auditada.
  No cuenta lotes nuevos nunca registrados, paquetes ni mercancía de terceros.
- Reposición sugerida configurable, excluye caducados; no genera compras.

### Devolución deteriorada: implementada y probada en UI

`mgs_damaged_return.py` añade campo por línea y merma ligada a cada movimiento
devuelto, en la misma transacción. Coste original incluso sin lote. Protección de
duplicación y bloqueo de cambio posterior de la marca. En TPV pregunta al validar
por cada línea negativa de stock si es recuperable o deteriorada.

Pruebas: varias partidas, devolución parcial, coste, reintentos, rollback ante
fallo de merma; prueba adicional con dependienta y producto sin lote.

UI 6/9, 01:30 UTC: venta sintética 6,05 €; retorno `Pedido 00012-002-0004`, paid,
qty -1, deteriorada=true, origen línea 217, coste -2,50 €. Merma única SP/00017,
done, motivo return, movimiento 1334, usuario 62, coste 2,50 €. Lote 157 pasó
cliente→stock→mermas en esa transacción. Rosa quedó en 22 unidades tras la venta
y devolución deteriorada. Ningún pago real ni hardware físico.

### Roles y hardware

- Propietaria y dependienta; costes/catalogación/informes/configuración protegidos
  en servidor, no solo ocultos por UI. Ver mgs_permissions/mgs_security.
- `mgs_hardware_job.py`, `pos_hardware.js`: trabajos duraderos tras commit,
  pending/sending/sent/uncertain, no reenvío automático de resultado incierto,
  reimpresión explícita y apertura manual con motivo. Prueba de dos conexiones
  demuestra que no se imprime antes del commit; reinicio/reintento ensayados.
- Ventas UI previas: efectivo 6,05 € y mixto 14,52 € (5 efectivo + 9,52 tarjeta).
- Dispositivos simulados en `.odoo_data/ui-printer.bin`. Ningún ensayo físico.

### Informes

- `mgs_monthly_report.py` y QWeb: ventas netas/impuestos, coste histórico, margen,
  merma y margen después de merma, tickets/media, días Madrid, categoría,
  cobros por fecha de pago, crédito de cliente separado, stock actual valorado.
- CSV de ventas y nuevo ZIP de resumen/ventas/días/mermas/stock/cobros. Omite
  cobros con categoría (no atribuir pagos mixtos arbitrariamente), protege fórmulas.
  Tests abren ZIP y leen valores reales. Falta probar clic/descarga ZIP en navegador.
- PDF nativo dos páginas A4 renderizado e inspeccionado; se corrigió título
  huérfano. Evidencia `.odoo_data/output/pdf/informe-validacion.pdf`, sintética.
  Falta muestra con muchas mermas, textos largos y varias páginas.
- `install-pdf.ps1`: wkhtmltopdf 0.12.6 patched Qt portátil, descarga oficial con
  SHA fijado; integrado en instalación/arranque. test.ps1 no pone su ruta en PATH,
  por eso el log de tests puede avisar que no encuentra wkhtmltopdf. Ese aviso
  no sustituye la prueba específica real de PDF.

### Instalación, servicio y copias

- Bootstrap fija core/dependencias, Python/pip check, reserva DB vacía, preserva
  existentes, marca instalación pendiente, configuración privada fuera de OneDrive,
  ACL Windows, contraseña inicial aleatoria. Probado dos veces reutilizando
  checkout y venv existentes. Falta instalación desde máquina vacía realmente.
- `service.ps1`, tools/windows_service.py/service_process.py/service_worker.py:
  LocalService, automático retrasado, dependencia PG, rutas explícitas, recuperación
  y parada por pipe. Supervisor real arrancó HTTP8077 y paró código 0/puerto libre.
  **No se registró servicio SCM**: usuario no elevado. Falta instalar con elevación,
  verificar permisos efectivos, reinicio, apagado y recuperación por fallo.
- Copia SQL+filestore coherente, ZIP+SHA, réplica SSD, retención 30 días, cierre
  de sesión marca backup pendiente tras commit, reintentos por cron y avisos.
  Restore ensayado en DB nueva; no sobrescribe existentes, verifica archivo,
  desactiva cron/hardware en restaurada. Varias restauraciones reales sintéticas
  pasaron. Falta SSD físico, desconexión/reconexión, espacio insuficiente y aceptación
  temporal del calendario/cierre. Ver scripts check_backup_restore/backup_archive.

## 5. Orden recomendado de trabajo pendiente

1. Corregir y completar apertura de stock (sección 3); ejecutar suite completa.
2. Completar catálogo inicial: obtener listado real de productos/códigos/unidades,
   precios/costes/categorías/IVA y partidas existentes. Preparar plantilla/importación
   con validación previa, duplicados y tratamiento de ceros. No inventar catálogo
   real ni cargar datos de demostración en producción. Aclarar impuestos con dueña.
3. Probar UI de apertura y descarga ZIP; completar PDF largo y pruebas de ambos
   roles, retorno recuperable/deteriorado mixto por líneas y cierre de caja.
4. Auditar cambios completos y concurrencia, transacciones, RPC, compañías y
   reintentos. Los tests actuales no prueban todos los caminos de Odoo nativo.
   Revisar especialmente posibilidad de modificar/borrar trazas desde rutas RPC
   alternativas y que datos POS personalizados sobrevivan a recarga/offline.
5. Instalación realmente limpia con descarga y nuevo venv; actualizar DB aislada
   representativa y volver a probar restauración. No usar mi_base_stock sin un
   plan concreto de migración y copia previa autorizada.
6. Servicio real Windows en consola elevada y datos fuera de OneDrive, reinicio,
   preapagado, recuperación, permisos LocalService e impresora por cuenta servicio.
7. Conectar SSD y verificar programación 6 horas/cierre, réplica, retención,
   avisos y restauración desde SSD en DB distinta. Registrar rutas/volúmenes reales.
8. Manual general de tienda y recuperación integrando los manuales parciales:
   apertura, recepción, venta, tarjeta externa, errores, devolución, merma,
   recuento, cierre, backup/restauración y mantenimiento.
9. Comprobar requisitos de facturación españoles vigentes en fuentes oficiales
   AEAT/BOE y según régimen de la tienda. No está investigado ni demostrado aquí.
   Odoo Community + l10n_es no prueba por sí solo cumplimiento comercial; confirmar
   facturas simplificadas/rectificativas, numeración, impuestos y requisitos SIF
   aplicables/plazos actuales antes de producción. No inventar fechas legales.
10. Jornada física: lectores HID (Enter/prefijos/sufijos), Bluetooth/reconexión,
    impresora 80mm/etiquetas/acentos/cortes, cajón, datáfono manual, pago mixto,
    merma/retorno/recuento/cierre, desconexiones, reinicio y restauración.
    Registrar evidencia real; simulaciones no satisfacen este punto.
11. Actualizar checklist según evidencias, revisar secretos/diffs, preparar commits
    sin incluir runtime privado, y entregar estado final sin proclamar controles
    físicos/fiscales completos si no se han realizado.

## 6. Comandos y pruebas para retomar

Desde `EntreRamblas` (PowerShell):

```powershell
.\test.ps1 -Tags /mi_gestor_stock:TestOpeningStock
.\test.ps1
.\test.ps1 -Restore
```

test.ps1 gestiona PG aislado si no está arrancado, ejecuta archivo backup (3 tests),
actualiza/ejecuta tests Odoo y prueba transaccional de hardware. El restore es
opcional. Logs acumulados en `.odoo_data/mgs-validation.log`: mirar la última
ejecución, no una línea verde antigua.

Última suite COMPLETA verde: 29 pruebas a las 01:25 UTC, antes de apertura.
Después pasó una prueba adicional dirigida de devolución con dependienta.
La suite actual incluye además dos tests de apertura: **no está verde**.

HTTP de pruebas (sin cron; no usar como producción):

```powershell
.\venv\Scripts\python.exe odoo/odoo-bin -c odoo.conf --db_host=127.0.0.1 --db_port=55432 --db_user=mgs_test -d mgs_validation --db-filter=^mgs_validation$ --http-interface=127.0.0.1 --http-port=8075 --max-cron-threads=0 --logfile=.odoo_data/ui-validation.log
```

Login: `http://127.0.0.1:8075/web/login?db=mgs_validation`.
TPV sintético: `http://127.0.0.1:8075/pos/ui?config_id=12`.
Usuarios sintéticos propietaria/dependienta y contraseñas están en
`.odoo_data/ui-validation.json`; no copiarlas a Git. prepare_ui_validation.py
regenera contraseñas y datos: leer antes de ejecutarlo; no hacerlo solo para
consultar credenciales existentes. Después de un cambio de Python reiniciar el
servidor de prueba; después de campos/vistas actualizar addon y recargar assets.

Herramientas adicionales: tools/check_report_pdf.py, check_service_worker.py,
check_backup_restore.py, check_hardware_outbox.py. Leer sus rutas/puertos antes
de ejecutar. Pueden depender del HTTP de pruebas o del runtime privado anterior.

## 7. Condiciones del traspaso

No se deja un servidor HTTP de pruebas intencionadamente en ejecución. El último
servidor 8075 se detuvo tras la aceptación de devolución; el test fallido terminó
con apagado normal. PostgreSQL aislado puede seguir escuchando en 55432:
comprobar procesos/puertos, no asumir que una sesión antigua sigue viva.
No detener el PostgreSQL principal. No se ha hecho despliegue final ni commit.

El usuario continuará con otra IA por disponibilidad de tokens. No iniciar nuevas
iteraciones automáticas en este goal. La siguiente IA debe retomar el alcance
completo y usar este documento como mapa, no como sustituto de inspección del código.
