# Implementación acordada — seguimiento

Modelo de trabajo: Astra, razonamiento medio. Odoo 18 Community, un PC Windows
local, datos actuales de prueba. No borrar la base de desarrollo. Hardware:
Honeywell 1472g, lector PcCom, Approx appPOS80AM, CASH01, SSD Corsair.
Datáfono independiente (registro manual de tarjeta). Sin ramos, encargos ni nube.

## Entregables y aceptación

- [X] Entorno reproducible: fijar revisión Odoo y dependencias; instalación y actualización comprobadas.
- [X] Recepción con proveedor, unidad, coste y partida automática; doble confirmación segura.
- [X] Caducidad por lote y asignación automática por caducidad/antigüedad, sin vender caducados o stock insuficiente.
- [X] Devoluciones vinculadas y reversión de costes; mermas trazables; recuentos y reposición sugerida.
- [X] TPV: efectivo, tarjeta y pagos mixtos; caja y aperturas manuales auditadas.
- [X] Hardware: autorización RPC, impresión separada de venta, errores inciertos y reimpresión explícita.
- [ ] Informes: coste histórico, ventas netas e impuestos, margen, mermas, filtros, PDF y CSV, Europe/Madrid.
- [ ]  Arranque automático Windows y datos fuera de carpetas sincronizadas.
- [ ] Copias locales cada 6 horas y cierre, réplica SSD, 30 días, avisos y restauración ensayada.
- [ ] Catálogo inicial, manual de tienda y recuperación; comprobación de requisitos de facturación antes de uso comercial.
- [ ] Jornada física completa con lectores, impresora y cajón. No sustituible por simulaciones.

## Evidencia inicial

2026-09-05: repositorio limpio; Python 3.12.0; Odoo 18.0 revisión
`167e83374756c4c38bc46eb96763dfbd8cb8de6f`; servicio PostgreSQL 18 activo.
El informe existente recalcula costes con standard_price actual. La recepción
sobrescribe caducidad por producto. No hay suite propia de pruebas al inicio.

## Validación

Usar una base separada `mgs_validation` para instalación y pruebas. Conservar
la base `mi_base_stock`. No declarar finalizado un apartado sin registrar
comandos/resultados y limitaciones. Las pruebas físicas quedan pendientes
hasta disponer de los equipos.

## Avance verificado (2026-09-05, primer bloque)

Implementados y comprobados en Odoo real:

- Recepción por lote nativo con coste inmutable, proveedor, caducidad y protección
  de doble confirmación. El escaneo no hereda la fecha de una partida anterior.
- Asignación automática en TPV, primero por caducidad y después por antigüedad;
  rechazo de stock insuficiente/caducado. Cada línea de venta enlaza sus movimientos.
- Devoluciones parciales vinculadas, límite de devolución y recuperación del coste
  y lote originales. Pendiente completar el flujo de devolución no recuperable en TPV.
- Mermas con motivo, partida, usuario, coste y protección frente a doble validación
  o cantidades superiores al stock disponible.
- Reposición sugerida excluyendo caducados. Objetivo configurable; a cero significa
  el doble del mínimo. No se generan compras.
- Informe con ventas sin impuestos, coste histórico de líneas TPV, aviso de costes
  antiguos ausentes, entradas de proveedor separadas de ajustes y stock actual por
  coste de partida. CSV de ventas y filtro de categoría. Periodos Europe/Madrid.

Validación: `cd EntreRamblas; .\test.ps1` terminó con **13 pruebas, 0 fallos y
0 errores**. Incluye recepción, FEFO, falta de stock, devoluciones múltiples,
mermas, reposición, costes históricos, CSV, render QWeb HTML y cambio horario.
La instalación inicial y las actualizaciones se han ejecutado en `mgs_validation`.
No se ha actualizado `mi_base_stock` ni conectado ningún dispositivo físico.

La instancia de pruebas usa PostgreSQL 18 en 127.0.0.1:55432, usuario `mgs_test`,
autenticación local de confianza y datos exclusivamente de prueba. `test.ps1`
la inicia y detiene si no estaba ya funcionando. No usarla como producción.

## Trabajo siguiente (el objetivo completo sigue pendiente)

1. Completar aceptación visual de ambos roles y revisar el cierre de caja.
2. TPV: comprobación de existencias antes del cobro, pagos y cierre de caja;
   devolución deteriorada; impresión con estado incierto sin duplicación y aperturas auditadas.
3. Completar aceptación de estadísticas con casos amplios y exportaciones;
   el PDF real y las métricas principales ya están implementados (ver avance).
4. Recuentos, navegación y verificación visual en navegador (los parches JS aún
   requieren esta comprobación, aparte de las pruebas Python).
5. Preparar y ensayar el servicio Windows. Completar instalación en equipo nuevo
   con descarga del código y creación del entorno virtual desde cero.
6. Completar configuración de SSD físico y aceptación de avisos. Manual y carga
   inicial. Comprobar facturación aplicable.
7. Instalación limpia final, actualización ensayada y jornada con hardware real.

No activar partidas en un producto que todavía tenga existencias sin lote: la
recepción lo rechaza expresamente. Los datos actuales son de prueba; preparar
la base de producción limpia acordada, sin borrar por defecto la de desarrollo.

## Avance verificado (2026-09-05, segundo bloque)

- Roles Propietaria y Dependienta con controles de servidor sobre costes,
  catálogo, ajustes, recepción, informes y configuración. Venta y merma de la
  dependienta ejecutan solo los movimientos internos autorizados.
- Comprobación de existencias antes del cobro y de la confirmación. Ante pérdida
  de conexión se conserva el UUID de la venta para recuperar su resultado.
- Confirmación explícita de tarjeta externa. Impresión y cajón usan solicitudes
  persistentes: se confirma el estado «enviando» antes de tocar el transporte.
  Un envío incierto no se repite automáticamente; reimpresión explícita y
  aperturas manuales con motivo quedan registradas por usuario.
- Eliminadas las credenciales de administrador fijadas en el módulo. Aún falta
  sanear los lanzadores/configuración y preparar el alta segura de producción.
- Inicio con acceso Vender y opciones según rol; corregidas tildes de menús.

Validación: `EntreRamblas/test.ps1` terminó a las 15:30 UTC con **19 pruebas,
0 fallos, 0 errores**, más la prueba de conexiones PostgreSQL independientes
`tools/check_hardware_outbox.py`. Esta comprueba envío después del commit,
reintentos y reinicio sin repetir solicitudes inciertas.

Prueba real de navegador en `mgs_validation`, puerto 8075, con datos sintéticos:
apertura de caja de 100 €, venta de 6,05 € en efectivo y venta mixta de 14,52 €
(5 € efectivo + 9,52 € tarjeta). Ambas ventas quedan pagadas, con movimientos
de stock terminados, partida automática y coste histórico. Cada una genera una
solicitud de ticket y otra de cajón en estado enviado. El transporte escribe
exclusivamente `.odoo_data/ui-printer.bin`; esto no acredita funcionamiento de
la impresora o cajón físicos. No se ha modificado `mi_base_stock`.

## Avance verificado (2026-09-05, copias y recuperación)

- Copia local de SQL y adjuntos bajo la misma instantánea PostgreSQL exportada.
  ZIP comprobado antes de sustituir el archivo permanente y huella SHA-256.
- Réplica separada a carpeta SSD existente, comprobación SHA-256, error visible
  y reintento automático. Retención de 30 días limitada a archivos propios de
  las carpetas configuradas; una ruta ajena no se elimina.
- Copia cada 6 horas y después del commit del cierre. Si falla o se interrumpe,
  el cierre conserva una marca pendiente para reintentar. Aviso de copias en
  inicio para propietaria. No se confunde fallo SSD con pérdida de copia local.
- Recuperación a base nueva, nunca reemplaza la original. Verifica SHA-256,
  estructura y CRC, rechaza rutas inseguras, y ejecuta SQL con ON_ERROR_STOP.
  La base recuperada deja tareas e impresión automática desactivadas y trabajos
  de hardware pendientes como inciertos para revisarlos antes de usarlos.

Validación: **23 pruebas Odoo, 0 fallos y 0 errores** (15:47 UTC), prueba
transaccional de hardware y **3 pruebas de archivo** (corrupción, rutas y copias
antiguas). Restauración real con el nuevo recuperador a las 15:46 UTC: coinciden
productos, ventas, movimientos, lotes y contenido del adjunto de prueba. La base
temporal recuperada se eliminó; se conserva la copia como evidencia bajo
`EntreRamblas/.odoo_data/backup-validation/`. Ejecutar `test.ps1 -Restore` para
repetir todo el ensayo en el PostgreSQL aislado de puerto 55432.

Pendiente: verificar el SSD físico, el cierre completo con dinero real, los
avisos en pantalla después del último bloque, y la instalación fuera de OneDrive.
La recuperación no instala el programa ni sus dependencias; requiere el código
y entorno compatibles. Los lanzadores de arranque/bootstrap todavía necesitan
la revisión prevista; no usar este avance como instalación final de producción.

Lanzador `start-odoo.ps1`: conserva `-d` y el filtro exacto al arrancar después
de actualizar, detiene el arranque ante error, acepta `-Config`, lee host/puerto
PostgreSQL del archivo y comprueba la revisión Odoo. Sintaxis PowerShell validada;
pendiente ensayo del instalador y arranque Windows completo. No se ha ejecutado
el lanzador contra la base de desarrollo.

## Avance verificado (2026-09-05, instalador)

- `bootstrap.ps1` aplica revisión exacta Odoo y dependencias fijadas, comprueba
  Python 3.12 y `pip check`, reserva una base nueva atómicamente y no borra bases.
- Alta inicial sin HTTP, contraseña aleatoria y marcador pendiente que impide
  arrancar una instalación fallida. El alta no modifica cuentas de bases existentes.
- `tools/configure_runtime.py` prepara configuración privada, datos fuera de
  OneDrive y permisos Windows para usuario, SYSTEM y administradores. Genera
  contraseña maestra y fija rutas absolutas y escucha local.
- Secretos retirados de `odoo.conf` y de una referencia histórica del README.
  La configuración previa se conserva en `EntreRamblas/odoo.local`, ignorada por
  Git. No se han rotado credenciales de la base de desarrollo ni reescrito Git.
- Guía actual en `INSTALACION.md`. Los lanzadores admiten `-Config`; el arranque
  mantiene la base elegida y se detiene ante fallos de actualización.

Evidencia: dos bases nuevas `mgs_install_validation` y
`mgs_install_validation_v2` instaladas en PostgreSQL aislado 55432. La segunda
incluye la reserva atómica. Datos/configuración bajo LocalAppData, fuera de
OneDrive. Arranque real mediante `start-odoo.ps1` en 8076 y autenticación HTTP
correcta con el acceso aleatorio. Segunda ejecución del instalador conserva
la base. Comprobación del rechazo de arranque con `.pending`, permisos ACL
del archivo privado, sintaxis PowerShell y compilación Python correctos.

La suite vuelve a pasar a las 16:02 UTC: **23 pruebas Odoo, 0 fallos y 0 errores**,
3 pruebas de archivo y prueba transaccional de hardware. El ensayo reutilizó el
checkout y venv disponibles (versiones fijadas comprobadas); aún no demuestra
la descarga y creación del venv en un equipo vacío. El servidor de validación
8076 se ha detenido al terminar. PostgreSQL aislado sigue disponible para los
siguientes ensayos. No se ha actualizado `mi_base_stock`.

Pendientes principales: servicio Windows; PDF real; completar estadísticas,
recuentos y devolución deteriorada; manual/catálogo/fiscalidad y jornada física.

## Avance verificado (2026-09-05, estadísticas y PDF)

- Informe con ventas antes/después de devoluciones, tickets con venta/devolución,
  ticket medio con impuestos, ventas diarias Europe/Madrid, mermas por producto,
  partida y motivo a coste histórico, y margen después de mermas.
- Cobros por fecha de pago y método; salidas separan cambio/reembolso de entradas.
  Cuentas de cliente se identifican como no cobradas. El filtro de categoría
  omite cobros para no inventar una distribución de pagos mixtos.
- Stock valorado y cantidades del informe limitados a quants propios de la
  compañía. Las compras suman cantidades en unidades de producto.
- Motor oficial portátil wkhtmltopdf 0.12.6 (patched Qt), SHA-256 fijado en
  `install-pdf.ps1`, incluido en instalaciones nuevas y reconocido por el arranque.

Validación a las 16:15 UTC: **24 pruebas Odoo, 0 fallos y 0 errores**, más las
pruebas de archivo/hardware. Cubre coste de merma después de cambiar el coste
actual, devoluciones, media y fechas de cobro distintas de la venta. Comprobación
adicional del crédito de cliente excluido del neto cobrado en prueba dirigida.

PDF nativo generado por Odoo con base `mgs_validation`: dos páginas A4 revisadas
visualmente como PNG con Poppler. Corregido un título huérfano al pasar de página.
Evidencia: `EntreRamblas/.odoo_data/output/pdf/informe-validacion.pdf`, con datos
sintéticos de efectivo y pago mixto, margen, cobros, detalle diario y existencias.
La muestra no incluye una tabla larga de mermas: falta ampliar esa aceptación.
Se ha comprobado instalación del motor en el runtime privado de validación.

Siguientes bloques: servicio Windows; recuentos y devolución deteriorada;
exportación estadística completa, manual/catálogo/fiscalidad y prueba física.

## Avance verificado (2026-09-05, supervisor Windows)

- `service.ps1` y `tools/windows_service.py`: registro nativo con LocalService,
  arranque automático retrasado, dependencia PostgreSQL, rutas explícitas, dos
  reintentos ante fallo y aviso previo al apagado. No reemplaza servicios existentes.
- `tools/service_process.py` valida configuración y revisión; ejecuta Odoo sin
  ventana. `tools/service_worker.py` recibe la parada por un pipe privado y usa
  el apagado normal del ThreadedServer fijado. EOF solicita parar si cae el
  supervisor. Se permite hasta 100 segundos antes de forzar y registrar el fallo.
- `start-odoo.ps1 -Update mi_gestor_stock -NoStart` actualiza sin crear una
  instancia manual que compita con el servicio. Procedimiento en `INSTALACION.md`.

Evidencia: `tools/check_service_worker.py` arrancó Odoo real con
`mgs_install_validation_v2` en 8077, obtuvo HTTP 200, pidió parada y obtuvo código
0 con el puerto liberado. `odoo.log` registra apagado a las 16:31 UTC y cierre
de conexiones PostgreSQL. No se usó terminación forzada. El mismo código de
supervisión es el que utilizará el servicio. La actualización con `-NoStart`
terminó correctamente y dejó 8077 libre. Compilación Python, importación pywin32,
sintaxis PowerShell y diff sin errores.

La identidad actual **no está elevada** (WindowsPrincipal.IsInRole Administrador
devuelve False). No se ha registrado ni arrancado un servicio SCM. Quedan sin
verificar: permisos efectivos de LocalService en ejecución, registro SCM,
reinicio Windows, controles de preapagado y política de recuperación real.
Estas comprobaciones requieren una consola elevada y no se dan por completadas
por el ensayo del proceso. Hay trabajo independiente pendiente de inventario,
exportaciones y manual, por lo que el objetivo global sigue activo.

## Avance verificado (2026-09-05, recuento físico)

- Recuentos de partidas conocidas por ubicación, disponibles para la propietaria.
  Conservan cantidades consultadas, contadas, reservas, motivo, autor y fecha.
- Revisión explícita de todas las líneas; bloqueo de ajustes si cambian los
  quants consultados, aparecen cantidades inválidas o se invaden reservas.
- Ajustes nativos vinculados al recuento, aplicación idempotente y cancelación
  auditada sin modificar existencias. Los recuentos iniciados no se eliminan.
- El formulario permite guardar cantidades mediante comandos One2many sin
  permitir modificar las cantidades originales ni fabricar líneas por RPC.
- Procedimiento operativo en `RECUENTOS.md`.

La suite completa pasó a las 16:49 UTC: **27 pruebas Odoo, 0 fallos y 0 errores**,
más archivo y hardware. Después de los últimos ajustes de guardado, cancelación
y exclusión de diferencias cero, las 3 pruebas dirigidas de recuento pasaron
a las 16:57 UTC. No se ha repetido todavía la suite completa tras esos ajustes.

Prueba en navegador sobre `mgs_validation`: REC/00004, cuatro partidas revisadas,
reducción de una rosa de 9 a 8 y aplicación correcta desde el formulario. Esa
versión generó también tres movimientos nativos de cantidad cero; se conservan
como evidencia histórica. La versión posterior, cubierta por prueba automática,
excluye dichos movimientos. No se ha actualizado `mi_base_stock`.

Pendientes: carga inicial de catálogo/stock, devolución deteriorada, exportación
estadística completa, ampliar aceptación del PDF, manual general y comprobaciones
fiscales. También siguen pendientes el servicio SCM con elevación, el reinicio
Windows y la aceptación con los dispositivos físicos de la tienda.

## Avance verificado (2026-09-06, exportación de estadísticas)

Nuevo botón de exportación ZIP de CSV en el asistente de informes. Incluye
resumen con periodo, moneda y categoría, ventas por producto y día, mermas,
stock actual y cobros separados del crédito de cliente. Con categoría se omiten
los cobros. UTF-8 con BOM, protección de fórmulas en textos y LEEME con criterios
de interpretación. Procedimiento en `INFORMES.md`.

`EntreRamblas/test.ps1` completado a las 01:21 UTC: **27 pruebas Odoo, 0 fallos y
0 errores**, 3 pruebas de archivo y prueba transaccional de hardware. Las pruebas
de informes comprueban el ZIP real, importan sus CSV, verifican coste histórico,
margen después de merma, stock, ventas diarias, omisión por categoría, nombres
con fórmulas y separación de crédito/cobros. Incluye también la versión final
de recuentos de la fase anterior. No se ha probado todavía el clic de descarga
del nuevo botón en navegador. No se ha actualizado la base principal.

## Avance verificado (2026-09-06, devolución deteriorada)

- Campo por línea de devolución y selector en Validar del TPV: recuperable o
  deteriorada. La selección se conserva al reintentar una venta de resultado
  incierto; no se vuelve a preguntar si ya está pagada/confirmada.
- Las deterioradas generan el retorno original y una merma por movimiento
  devuelto, con motivo devolución no recuperable, enlace al movimiento, usuario
  y coste histórico. Todo ocurre en la misma transacción; no queda stock vendible
  adicional. El reintento no duplica la merma.
- Se rechaza marcar una venta positiva/no vinculada como devolución deteriorada
  y cambiar la marca después de generar movimientos. Compatible con partidas
  automáticas y productos sin seguimiento; seguimiento manual/serie no cubierto.

Suite completa a las 01:25 UTC: **29 pruebas, 0 fallos y 0 errores**. Nuevas
pruebas verifican devolución parcial de varios lotes, coste, reintentos, límite
restante y rollback al fallar merma. Una prueba adicional dirigida pasó después:
dependienta, producto sin lote, coste actual modificado y autoría de la merma.
Archivo/hardware también pasan. Falta aceptación del selector y persistencia del
campo en navegador antes de dar por cerrado este flujo. Base principal intacta.

### Aceptación en navegador (2026-09-06, 01:30 UTC)

En `mgs_validation`, cuenta sintética propietaria, TPV 12: venta de una rosa a
6,05 € y devolución vinculada completa. El selector aparece en Validar; se eligió
deteriorada. El TPV finalizó y pasó al siguiente pedido. Consulta SQL confirmó
`Pedido 00012-002-0004`, estado paid, cantidad -1, marca deteriorada verdadera,
línea original 217 y coste -2,50 €. Una única merma SP/00017, estado done,
motivo return, cantidad 1, movimiento devuelto 1334 y autor 62, coste 2,50 €.
Procedimiento de tienda en `DEVOLUCIONES.md`. Impresión simulada en archivo;
ningún pago real ni cambio en la base principal.
