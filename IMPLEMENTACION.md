# Implementación acordada — seguimiento

Modelo de trabajo: Astra, razonamiento medio. Odoo 18 Community, un PC Windows
local, datos actuales de prueba. No borrar la base de desarrollo. Hardware:
Honeywell 1472g, lector PcCom, Approx appPOS80AM, CASH01, SSD Corsair.
Datáfono independiente (registro manual de tarjeta). Sin ramos, encargos ni nube.

> ⚠️ **2026-09-09.** El módulo se ha recortado: fuera Compras, Partidas (vista),
> Recuento físico, Reposición, Bajas de caducados, Recetas de ramo, Tarifas de
> campaña y Existencias iniciales. Las casillas marcadas y los avances fechados de
> este documento que se refieran a esas funciones son históricos. Detalle al
> principio de [TRASPASO_IA.md](TRASPASO_IA.md); diagnóstico fiscal en
> [FACTURACION.md](FACTURACION.md) §2bis.

## Entregables y aceptación

- [X] Entorno reproducible: fijar revisión Odoo y dependencias; instalación y actualización comprobadas.
- [X] Recepción con proveedor, unidad, coste y partida automática; doble confirmación segura.
- [X] Caducidad por lote y asignación automática por caducidad/antigüedad, sin vender caducados o stock insuficiente.
- [X] Devoluciones vinculadas y reversión de costes; mermas trazables; recuentos y reposición sugerida.
- [X] TPV: efectivo, tarjeta y pagos mixtos; caja y aperturas manuales auditadas.
- [X] Hardware: autorización RPC, impresión separada de venta, errores inciertos y reimpresión explícita.
- [X] Informes: coste histórico, ventas netas e impuestos, margen, mermas, filtros, PDF y CSV, Europe/Madrid.
      PDF de dos y de ocho páginas y descarga del ZIP comprobados en navegador.
- [ ] Arranque automático Windows y datos fuera de carpetas sincronizadas.
      **Falta registrar el servicio con consola elevada**: el supervisor arranca y
      para bien, pero nunca se ha instalado en el SCM.
- [ ] Copias locales cada 6 horas y cierre, réplica SSD, 30 días, avisos y restauración ensayada.
      **Falta el SSD físico**: desconexión, reconexión, espacio insuficiente y
      restauración desde el disco externo.
- [X] Catálogo inicial (asistente de alta con comprobación previa) y manual de tienda
      y recuperación (`MANUAL_TIENDA.md`, `APERTURA.md`).
- [ ] Requisitos de facturación comprobados en AEAT/BOE (`FACTURACION.md`), pero
      **el programa no es un SIF conforme al RD 1007/2023** y quedan decisiones de
      régimen, IVA por artículo y numeración para la gestoría.
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

## Avance verificado (2026-09-06, existencias iniciales corregidas)

El bloque que quedó fallando en el traspaso está corregido y verde. El fallo
`AssertionError: 0.0 != 8` escondía **dos** defectos distintos:

1. **Duplicación real de existencias.** `action_apply` confirmaba el movimiento y
   después añadía a mano una `stock.move.line` con el lote, pero `_action_confirm`
   ya había generado su propia línea sin lote. Cada apertura dejaba el doble de
   stock: quants medidos en el diagnóstico, 8 sin lote + 5 + 3 con lote = 16 en
   una apertura de 8. Ahora se usa el ajuste de inventario nativo
   (`stock.quant` en `inventory_mode` + `_apply_inventory()`), el mismo camino que
   el recuento físico: un movimiento `is_inventory` con **una** línea y su partida.
2. **La aserción medía cero por la ubicación de la prueba.** `qty_available` solo
   suma quants que cuelgan de la ubicación vista de un almacén
   (`product._get_domain_locations`); la ubicación de prueba se creó sin padre y
   quedaba fuera. La prueba usa ahora una ubicación bajo `WH/Stock` y el modelo
   **rechaza** ubicaciones internas fuera del almacén, que guardarían existencias
   que el informe ve y el panel/TPV no.

Defecto adicional encontrado al corregir: una línea **sin fecha de caducidad**
nacía caducada, porque `product_expiry` calcula una caducidad desde hoy cuando el
campo no viaja en el `create`. Ahora se pasa explícitamente.

La caducidad de la prueba usaba el año 2080: pytz no tiene transiciones tan lejos
y devuelve horario de invierno, así que la aserción original (`21:59:59`) no podía
cumplirse. Las pruebas usan ahora fechas cercanas y comprueban **los dos** horarios
de Madrid: verano `21:59:59` UTC e invierno `22:59:59` UTC.

Concurrencia (era una duda explícita del traspaso): la apertura tomaba un candado
sobre `product_product` que **ningún otro flujo tomaba**. La recepción toma ahora
el mismo candado, en el mismo orden. `tools/check_opening_concurrency.py` lo
demuestra con dos conexiones reales y `lock_timeout`, en los tres cruces
(recepción→apertura, apertura→recepción y apertura→apertura), y no deja rastro.
Integrado en `test.ps1`.

### Aceptación en navegador (2026-09-06, 13:28 UTC)

`mgs_validation`, cuenta sintética propietaria. Apertura 45 sobre `WH/Stock`:
12 unidades a 1,80 € con caducidad 31/12/2027. Tras aplicar: estado Aplicado,
autor «Prueba owner» y fecha registrados, formulario en solo lectura y botón
Aplicar oculto. En base: `qty_available` 12 (no 24), partida `INI-45-65`,
caducidad `2027-12-31 22:59:59` UTC = fin del día de Madrid en invierno, un único
movimiento `is_inventory` desde ajuste de inventario a `WH/Stock` con una línea y
coste 1,80 € congelado, quant único de 12 con su partida. Sin errores de consola.

## Avance verificado (2026-09-06, alta de catálogo)

Nuevo asistente **Stock → Alta de catálogo** (`mgs.catalog.import`): plantilla CSV
descargable, comprobación completa antes de crear nada y alta en bloque. Si una
fila está mal **no se importa ninguna**. Detecta nombres y códigos repetidos
dentro de la hoja y contra el catálogo, importes no numéricos o negativos, IVA
fuera de 0/4/10/21 y categorías o unidades inexistentes. Ceros y categorías
nuevas exigen confirmación explícita por casilla. El código puede ir vacío: se
genera un EAN-13 interno imprimible. Los productos se crean como los crea la
recepción (almacenable, TPV, partidas automáticas, caducidad).

El IVA **no se elige por defecto**: se exige por fila, porque el tipo aplicable lo
decide la dueña con su gestoría (ver `FACTURACION.md`).

Aceptación en navegador (13:39 UTC): hoja con 6 filas y errores buscados —
código repetido, nombre repetido, precio a cero e IVA 7 — señalados uno a uno y
sin crear nada; hoja corregida de 4 filas importada con categorías nuevas
anunciadas antes de crearlas. En base: códigos internos `2800000000035/42/59`
generados, `Docenas` resuelto a la unidad correcta, impuestos `10% G` y `21% G`,
todos con partidas automáticas y caducidad. Procedimiento en `APERTURA.md`.

## Avance verificado (2026-09-06, informes y facturación)

- **ZIP de estadísticas descargado desde el navegador** (era un pendiente
  explícito): respuesta 200, `application/zip`, `content-disposition` de
  descarga y los seis CSV dentro (resumen, ventas, ventas diarias, mermas, stock
  actual, cobros).
- **PDF largo**: `tools/check_report_pdf_long.py` monta un mes sintético de 45
  productos con nombres largos y mermas, dentro de una transacción que no se
  confirma. Resultado: **8 páginas**, 46 mermas, 48 filas de stock, sin páginas en
  blanco, nombres largos completos y cabecera de tabla repetida en cada página.
  Evidencia en `.odoo_data/output/pdf/informe-validacion-largo.pdf`.
- **Facturación** (`FACTURACION.md`): consultadas AEAT y BOE. Los plazos SIF /
  VERI\*FACTU **de usuario** se ampliaron por el RDL 15/2025 a **1-1-2027**
  (Impuesto sobre Sociedades) y **1-7-2027** (resto). El programa **no es hoy un
  SIF conforme**: no encadena huellas, no firma, no lleva registro de eventos ni
  imprime QR. La factura electrónica B2B del RD 238/2026 **no afecta** a las
  ventas a consumidor final ni a las simplificadas de minorista. _(Corregido el
  10-09-2026: el plazo de **productores/comercializadores** de software es el
  **29-07-2025** y no se amplió; si el programa se considera comercializado a la
  tienda, ese es el que aplica. Ver `FACTURACION.md` §2.)_
- Dos huecos del ticket frente al artículo 7 del RD 1619/2012, corregidos: ahora
  imprime el **tipo impositivo** (`IVA 21%`) en vez del nombre interno de l10n_es
  (`21% G`), y las devoluciones remiten al ticket rectificado. Con prueba.

Suite completa tras estos bloques, por `test.ps1`: **45 pruebas Odoo, 0 fallos y
0 errores**, más archivo de copia, transacción de hardware y concurrencia de
apertura. Base principal `mi_base_stock` intacta.

## Avance verificado (2026-09-06, devolución mixta y cierre de caja en TPV)

Últimas aceptaciones de navegador que faltaban del flujo de tienda, en
`mgs_validation`, TPV 12, cuenta sintética propietaria. Sin dinero real ni
hardware físico: impresión simulada en archivo.

**Venta** `TPV prueba floristería/0004`, 26,62 € en efectivo: dos líneas de rosa
y una de jarrón.

**Devolución mixta por líneas** sobre ese mismo ticket, −20,57 €: el TPV preguntó
**una vez por cada línea** («Estado de la devolución: Rosa roja · prueba» y
después «Jarrón · prueba»). Se eligió **recuperable** para la rosa y
**deteriorada** para el jarrón, en la misma devolución.

Comprobado en base:

- Pedido de devolución vinculado al original (`refunded_order_id`), línea 308
  rosa con `mgs_damaged_return` falso y línea 309 jarrón con la marca verdadera.
- Albarán `WH/POS/00006`: los **dos** productos vuelven de cliente a `WH/Stock`
  con su partida original (0000157 y 0000159) y su coste histórico (2,50 € y
  6,00 €), no el coste actual.
- Una **única** merma `SP/00111` del jarrón: 1 unidad, motivo `return`, estado
  done, partida 0000159, autor «Prueba owner». La rosa **no** genera merma.
- Existencias: rosa 22 → vende 2 → 20 → devuelve 1 → **21**. Jarrón 24 → vende 1
  → 23 → devuelve 1 → 24 → merma 1 → **23**. La deteriorada no queda vendible.

**Cierre de caja** de la sesión `POS/00001`: esperado 117,10 € (100 de apertura +
17,10 de cobros), contado 117,10 €, **diferencia 0,00 €**, tarjeta 9,52 € sin
diferencia, nota de cierre guardada, sesión en estado `closed` a las 11:57:43 UTC
y sesión nueva creada a continuación. `mgs_backup_pending` quedó en falso, que es
lo correcto: en esta base `backup_enabled` está desactivado, y la marca solo se
pone cuando las copias están configuradas (cubierto por
`test_close_marks_backup_pending_until_success`).

Se borraron de la base de validación los dos productos y ubicaciones que dejó un
intento fallido de la prueba de concurrencia. Las aperturas ya aplicadas **no** se
pudieron borrar, que es exactamente la protección que se pedía.

## Avance verificado (2026-09-07, ramos a medida y bodas con alquiler)

Ampliación de alcance pedida por el usuario: la tienda hace **boda y día a día**,
así que la pantalla de vender tenía que cubrir desde un ramo momentáneo hasta una
boda con sus muebles. Esto **deroga** la decisión anterior «sin ramos ni encargos»
del traspaso, que queda anulada.

Se acordaron tres cosas antes de construir nada, porque cada respuesta llevaba a
un trabajo distinto: los muebles **se alquilan o se venden según el artículo**, el
ramo **descuenta cada flor** y las bodas van por **presupuesto → señal → entrega →
cobro**.

### Ramo a medida en el TPV (`models/mgs_bouquet.py`)

El producto de la composición **no es almacenable**: no mueve stock por sí mismo.
Lo que mueve stock son sus componentes, cada uno con su `stock.move` enlazado a la
**misma** línea del TPV (`mgs_pos_line_id`). Con eso, todo lo que ya existía
funciona sin tocarlo: reserva FEFO por caducidad y antigüedad, coste histórico
congelado por partida, y `_compute_total_cost`, que suma los movimientos de la
línea sin importar de qué producto son. El ticket enseña una línea; el almacén
descuenta cada tallo.

El navegador manda el contenido como JSON en `mgs_bouquet_spec`. El servidor lo
valida con **el mismo parser** en la comprobación previa al cobro y al crear la
línea, para que lo que pasa el control sea exactamente lo que se puede grabar: un
ramo inválido falla **antes** de cobrar, no después.

Defecto que habría pasado desapercibido: sin ampliar `mgs_check_stock`, se
comprobaba el stock del producto «Ramo» —que no tiene ninguno— y se podía cobrar
un ramo sin flores suficientes.

**9 pruebas**: descuento por tallo con una sola línea de ticket, FEFO repartiendo
entre dos partidas, varios ramos iguales multiplicando material, comprobación de
stock contra las flores, seis formas de contenido inválido rechazadas antes de
cobrar, producto normal que no puede llevar materiales, composición que no puede
tener existencias propias, contenido congelado tras cobrar y flor caducada
rechazada.

### Bodas y alquiler (`models/mgs_event.py`)

Recorrido `draft → confirmed → delivered → returned → done`, con cancelación.
Dos ideas que sostienen el diseño:

- **Reservar no es entregar.** Aceptar un presupuesto compromete el material para
  esas fechas pero no mueve una sola unidad. Por eso la disponibilidad no se puede
  mirar con `qty_available`: se cuenta la flota entera (tienda + lo que está fuera)
  y se le resta lo comprometido en fechas que **se solapan**.
- **Lo alquilado sigue siendo nuestro.** Sale a una ubicación de **tránsito**, no a
  «cliente»: no está en la tienda (no se puede vender) pero no se ha vendido. Lo
  que vuelve entero regresa al almacén; lo roto se da de baja como merma con motivo
  *rotura* y su coste real; lo que no vuelve se queda a la vista para reclamarlo.

Confirmar toma el **mismo candado sobre `product_product`** que recepción y
apertura: sin él, dos bodas confirmadas a la vez podrían prometer el mismo arco.

Los cobros (señal y final) se registran en el propio evento y **no pasan por la
caja del TPV**: mezclarlos con el arqueo del día daría cifras que no cuadran,
porque una señal de marzo es dinero de marzo. En el informe mensual van en su
**propio apartado** por fecha de evento; el material roto sí aparece en las mermas.

**16 pruebas**, incluidas: el mismo arco no va a dos bodas solapadas, el solape se
mira en todo el rango y no solo el día, la entrega separa venta de alquiler, la
devolución parcial con roto genera merma, no se puede devolver más de lo que salió,
no se cierra con material fuera ni con dinero pendiente, y el informe no cuenta dos
veces.

### Fallo encontrado en navegador y corregido

Anotar la devolución desde el formulario **no funcionaba**: la pantalla guarda el
evento entero con un comando sobre `line_ids`, y el `write` del evento lo rechazaba
por no estar en borrador. Las pruebas no lo veían porque escribían directamente
sobre la línea, que es otra ruta. Corregido admitiendo únicamente comandos de
actualización sobre las casillas de devolución de líneas existentes —mismo patrón
que el recuento físico— y **con una prueba que usa la ruta del formulario**, para
que no vuelva a escaparse.

### Aceptación en navegador (2026-09-07)

`BODA/2026/0034`, arco de alquiler con fianza de 60 €, evento 12/06/2027 y
devolución 14/06/2027. El `onchange` marcó «se alquila» y trajo el precio y la
fianza solos. Tras entregar: movimiento `WH/Stock → Alquiler en curso`. Se anotó
una unidad rota y tras registrar la devolución: movimiento de vuelta, merma
`SP/00120` en estado done con motivo `breakage` y su partida, arco de 2 a **1** en
tienda y flota **1**, estado «Material devuelto» y aviso de pendiente retirado.

Suite completa por `test.ps1`: **70 pruebas Odoo, 0 fallos y 0 errores**, exit 0.

### Aceptación del ramo en el TPV real (2026-09-07)

`TPV prueba floristería/0005`: se montó un ramo con 7 rosas y 2 gerberas desde la
pantalla táctil. El precio sugerido salió solo (7×5 + 2×3,50 = **42 €**) y se
cobró a **48 €** para incluir el montaje. Comprobado en base: el ticket lleva
**una sola línea** («Ramo a medida», 48 €), el contenido quedó guardado
(7 rosas + 2 gerberas), el almacén repartió los tallos entre **dos partidas por
FEFO** —6 del lote 0000157, que caduca antes, y 1 del 0000158— más 2 gerberas del
lote INI-45-65, y el **coste de la línea es 21,10 €**, el real de las flores, no
el precio de venta. Existencias: rosa 21→14, gerbera 12→10.

## Avance verificado (2026-09-07, compras, consumo, caducados, recetas, previsión y tarifas)

Seis bloques más, cerrados en la misma tanda tras ramos y bodas. Cada uno resuelve
un hueco distinto que dejó abierto lo anterior: saber qué falta por llegar, cuánta
flor se gasta de verdad, qué hacer con lo caducado, repetir un ramo sin tener que
recordarlo, cuánto pedir para una fecha señalada y cobrar distinto en campaña sin
tocar la ficha del producto a mano.

### Pedidos a proveedor (`models/mgs_purchase.py`)

Deliberadamente **sin** el módulo nativo `purchase`/`purchase_stock`: sus
albaranes de entrada nacen por rutas de almacén, sin pasar por
`mgs.reception.action_confirm`, que es el único sitio donde una partida congela
`mgs_unit_cost` / `mgs_supplier_id` / `mgs_cost_recorded`. Con el módulo nativo
esos lotes llegarían sin coste histórico y el margen del informe mensual
empezaría a mentir en silencio — además de traer su propio menú raíz, facturas
de proveedor y un flujo completo que aquí sobra. Un pedido no mueve stock por sí
mismo: eso solo pasa al recibirlo de verdad por `mgs.reception`, como siempre.

**11 pruebas.**

### Consumo real de flor (`models/mgs_consumption.py`)

Vista SQL de solo lectura sobre `stock.move.line`, que es donde ya está todo
unificado con su coste histórico congelado — una rosa suelta, una rosa de un ramo
y una rosa de un centro de un evento son, todas, líneas de movimiento. Filtrar por
`location_dest_id.usage = 'customer'` basta para quedarse solo con lo que de
verdad ha salido de la tienda: fuera mermas, devoluciones y el material de
alquiler que vuelve. Al ser una vista sobre otras tablas, `search()` fuerza
`flush_all()` antes de preguntar, para no perderse una escritura de la misma
transacción que todavía no se ha volcado.

**5 pruebas.**

### Baja asistida de caducados (`models/mgs_expiry.py`)

El automatismo detecta, la persona confirma: `stock.scrap.do_scrap()` es
irreversible y un PC de tienda puede llevar días sin abrirse, así que un cron que
diera de baja por su cuenta sería peligroso. El cron de `mgs_stock_alert.py` solo
genera o refresca una **propuesta** por tienda —siempre la misma mientras siga
abierta— con el coste que se va a perder a la vista antes de confirmar; confirmar
vuelve a comprobar que el stock no ha cambiado desde que se generó, mismo patrón
que el recuento físico.

**8 pruebas.**

### Recetas de ramo (`models/mgs_bouquet.py`)

Un punto de partida guardado, no un candado: la dependienta sigue pudiendo sumar,
quitar y cambiar el precio antes de cobrar. `spec_json` se valida con el mismo
parser que usa el cobro (`_mgs_parse_components`), así que una receta guardada
nunca puede contener algo que el TPV luego rechace. En un evento, una composición
sin receta no se puede añadir a la línea: se rechaza antes de guardar, para no
perder la merma de flor en silencio.

**3 pruebas** (`test_recipe_validates_against_the_same_parser_as_checkout`,
`test_only_the_owner_manages_recipes`, `test_recipe_spec_json_updates_when_lines_change`).

### Previsión de compra (`models/mgs_purchase_forecast.py`)

«Cuánto pedir para San Valentín» dejó de ser una corazonada. Mira el mismo
periodo de años anteriores usando el consumo real hasta la flor (no unidades de
«Ramo a medida» vendidas, que no dicen nada de cuántos tallos hicieron falta),
propone el máximo histórico con un margen de seguridad y resta lo que ya hay en
tienda sin caducar. Es una propuesta: «Crear pedido» solo rellena un
`mgs.purchase.order` en borrador, que se revisa y confirma como cualquier otro.

**9 pruebas.**

### Tarifas de campaña (`models/mgs_pricelist_campaign.py`)

Se apoya en `product.pricelist` nativo, ya soportado por el TPV de serie: el
asistente es solo una capa simple encima para que la propietaria nunca vea el
formulario nativo con sus cuatro modos de cálculo ni la base recursiva de otra
tarifa. Comprobado que no interfiere con lo que ya existe: el margen sigue
mirando el coste histórico de la partida, nunca el precio de venta; el ramo a
medida conserva su precio manual (`pos_store.js` marca `price_type: "manual"` en
cuanto la línea trae un `price_unit` propio); y el ticket fiscal recalcula el IVA
desde los subtotales reales de cada línea, tarifa o descuento aparte.

**7 pruebas.**

### Pendiente de esta tanda

**121 pruebas Odoo en verde** por `test.ps1` al cerrar los seis bloques. Queda
pendiente la **aceptación en navegador** de los seis flujos (no solo las pruebas
automáticas): es una sesión de pantalla con la propietaria delante, y no se ha
hecho todavía — ver `TRASPASO_IA.md`.

## Avance verificado (2026-09-10, entrega final: acceso, igualdad, instalador)

Ejecución del plan `PlanFinalizarGestor.md` (rama `finalizar-entrega`; rastro
vivo en `ENTREGA_FINAL.md`). Módulo `18.0.2.0.0` → **`18.0.3.0.0`**. Suite:
**249 pruebas, 0 fallos, 0 errores** al cierre (partiendo de 236).

- **Documentación / VeriFactu** (`FACTURACION.md` y otros): VeriFactu queda
  fuera de la entrega por decisión de la propietaria; corregido el marco de
  plazos con la fila de **productores/comercializadores de SIF** (29-07-2025,
  no ampliado) y el matiz «desarrollo propio vs. comercializado». Emitir
  tickets no equivale a cumplir ni valida la facturación.
- **Acceso solo con contraseña** (`ACCESO.md`, `models/mgs_access.py`,
  `controllers/mgs_auth.py`, migración `18.0.3.0.0`): cuenta de propietaria
  separada de `base.user_admin` (gestión de tienda, sin admin técnico);
  formulario sin selección de usuario; primer acceso con código de activación
  de un solo uso; recuperación por **clave impresa** (rota, invalida sesiones,
  sin correo); límite de intentos persistente; CSRF; Configuración → Seguridad;
  rastro de restablecimientos; `recuperar-acceso.ps1` (administrador de
  Windows) para la pérdida total. Menú de usuario filtrado al construirse.
- **Misma app en todos los equipos**: `start-odoo.ps1` aplica la actualización
  pendiente antes de servir (`tools/check_pending_upgrade.py`) y comprueba la
  integridad del motor (`tools/verificar_motor.py`: commit fijado + sin ficheros
  versionados modificados/añadidos; la falta de documentación/empaquetado/
  ficheros de prueba no bloquea); la caja de tienda se crea antes de los
  ajustes comunes del TPV; `install_database.py` no oculta un fallo de la caja;
  `db_name` como fuente única del nombre de base; nombre comercial separado de
  la razón social; **diagnóstico exportable sin secretos** (`mgs.diagnostic`,
  `diagnostico.ps1`, `comparar_diagnosticos.py`) + histórico de versiones
  aplicadas; contraseña PostgreSQL por defecto fuera de `odoo.conf`.
- **Instalador y actualizaciones firmadas** (`ACTUALIZACIONES.md`,
  `EntreRamblas/instalador/`, `EntreRamblas/publicar/`): firma **Ed25519**
  (`tools/paquete_firma.py`, probada, incluido el rechazo de un manifiesto
  manipulado); **actualizador independiente con estado persistente**
  (`tools/actualizador.py`): comprobar/preparar/aplicar en 7 pasos con
  reversión de base y luego código; en la app, «Actualización disponible» y
  «Actualizar al cerrar»; Inno Setup `.iss` + orquestador (PostgreSQL
  dedicado, servicio, acceso directo a Edge, PDF, base sin demo,
  reinstalar/desinstalar conserva datos y copias); pipeline `empaquetar.ps1`.

### Pendiente (no es código)

- Crear `AaronRuizzz/EntreRamblasReleases` y decidir la cuenta de publicación.
- Generar la clave privada de firma definitiva, offline, y custodiarla fuera.
- Instalar Inno Setup, compilar el `.exe` y probar instalación limpia.
- Registrar el servicio en el SCM (consola de administrador) y probar
  reinicio/apagado/recuperación.
- Matriz física del plan §5 (hardware, SSD, jornada real, actualización con
  paquete alterado / disco lleno / corte a mitad).
- Gestoría: régimen, IVA por familia, serie, vía SIF/VeriFactu.
