# Estado del proyecto — gestor de stock Entre Ramblas

> **Actualización del 10 de septiembre de 2026 — entrega final (plan
> `PlanFinalizarGestor.md`).** Rama `finalizar-entrega`, módulo → `18.0.3.0.0`,
> suite **249 pruebas en verde**. Hecho: acceso solo con contraseña + primer
> acceso con código + recuperación por clave impresa + herramienta local
> (`ACCESO.md`); arranque que aplica la actualización pendiente e integridad del
> motor; diagnóstico exportable sin secretos; nombre comercial ≠ razón social;
> firma Ed25519 + actualizador con estado y aplicación segura en 7 pasos
> (`ACTUALIZACIONES.md`); instalador Inno Setup + pipeline de publicación
> (`EntreRamblas/instalador/`, `EntreRamblas/publicar/`); VeriFactu documentado
> como fuera de la entrega. **Rastro y pendientes en `ENTREGA_FINAL.md`.** Lo
> que sigue necesitando una persona: crear el repo de releases, la clave privada
> de firma definitiva, compilar y probar el `.exe`, registrar el servicio en el
> SCM, la jornada física y la gestoría.

> **Actualización del 9 de septiembre de 2026 — recorte del módulo.** A petición
> del usuario se han **eliminado del código** nueve secciones que la tienda no va
> a usar: **Compras** (pedidos a proveedor y previsión), la pantalla **Partidas**
> (los campos de coste histórico de `stock.lot` se conservan; solo se fue la
> vista), **Recuento físico**, **Reposición**, **Bajas de caducados**, **Recetas
> de ramo**, **Tarifas de campaña** y **Existencias iniciales**. El menú Stock
> queda en Panel · Productos · Alertas · Alta de catálogo.
>
> Las **recetas de ramo** sostenían las composiciones de los eventos: se ha
> reemplazado esa dependencia por una **lista de materiales en la propia línea del
> evento** (`mgs.event.line.component`), validada por el mismo parser que usa el
> TPV al cobrar. No se pierde el descuento de flor exacto ni el coste real.
>
> Además: «Vender» ya crea una **caja de floristería** sin plano de mesas; la
> barra superior **resalta la sección activa**; **Mermas** pierde «Documento de
> origen» y «Ubicación de origen» y el informe mensual añade fecha/referencia/
> autor de cada merma; los **avisos** admiten un nombre opcional buscable; el menú
> **«Impresiones y aperturas»** está traducido; y hay una herramienta nueva
> `reset-catalogo.ps1` para vaciar el catálogo antes de una entrega. Las partes de
> este documento y del resto que describan Compras, Recuento, Reposición, Recetas,
> Tarifas, Partidas o Existencias iniciales **son históricas**. **APERTURA.md y
> RECUENTOS.md quedan obsoletos por completo.** El diagnóstico del ticket frente a
> la normativa está en [FACTURACION.md](FACTURACION.md) §2bis.

Última revisión: **7 de septiembre de 2026**. Sustituye al traspaso anterior:
esta sesión ejecutó un plan de continuación completo (8 fases: correcciones,
quitar la marca Odoo, compras y proveedores, consumo real de flor, caducidad
asistida, recetas de ramo, previsión de compra y tarifas de campaña — ver
sección 3). **El proyecto sigue sin estar listo para producción**, pero por
motivos concretos y acotados que se enumeran en la sección 5: falta hardware
físico, falta el servicio de Windows instalado con permisos de administrador y
falta el cumplimiento SIF/VERI\*FACTU antes de sus plazos. Nada de eso es
código: es puesta en marcha real, fuera del alcance de una sesión de agente.

## 1. Objetivo y decisiones que se deben conservar

Gestor de stock a medida (sobre Odoo 18 Community, aunque la marca Odoo está
deliberadamente oculta de la interfaz — ver sección 3, Fase 1) para una
floristería, un PC Windows local, sin nube. Stock por partidas, caducidad,
costes históricos congelados, recepción, TPV, devoluciones, mermas, recuentos,
reposición, estadísticas, roles y copias recuperables. Interfaz en español y
periodos Europe/Madrid. Hardware acordado: Honeywell 1472g, lector PcCom,
Approx appPOS80AM, cajón CASH01 y SSD Corsair. Datáfono independiente: el
programa registra tarjeta, no cobra/reembolsa por API.

**Alcance ampliado el 7-9-2026 por el usuario**: la tienda trabaja boda y día a
día. El programa cubre **ramos y composiciones a medida** (con recetas
guardables) y **bodas con material de alquiler** (incluidas composiciones
dentro de una boda, vía receta). Decisiones acordadas: los muebles se alquilan
o se venden **según el artículo**, el ramo **descuenta cada flor** de su
partida, y las bodas van por **presupuesto → aceptado → entregado → material
devuelto → cobrado**, con sus cobros en un apartado propio del informe (no
pasan por la caja del TPV).

Más tarde el mismo día, el usuario pidió un **plan de continuación** con lo que
faltara, y un punto explícito para **quitar la marca Odoo** de todo lo que ve
la dueña, sustituyéndola por «Gestor de Stock» (dentro del programa) o «Entre
Ramblas» (de cara a la clienta). Ese plan se ejecutó completo en esta misma
sesión (detalle en la sección 3).

## 2. Rutas, entorno y protección de datos

- Raíz Git: `C:/Users/ruben/OneDrive/Escritorio/FoodGuard/gestorStockFloristeria/EntreRamblasGestorStock`.
- Runtime: subcarpeta `EntreRamblas` de esa raíz.
- Addon: `EntreRamblas/custom_addons/mi_gestor_stock`.
- Python: `EntreRamblas/venv/Scripts/python.exe`, Python 3.12.0.
- Odoo: `EntreRamblas/odoo`, checkout ignorado por Git, revisión fijada
  `167e83374756c4c38bc46eb96763dfbd8cb8de6f`.
- PostgreSQL 18: `C:/Program Files/PostgreSQL/18/bin`.
- Base principal `mi_base_stock` en puerto 5432: **no se ha tocado en ningún
  momento** de esta sesión, ni para probar ni para nada.
- Base de pruebas `mgs_validation`, clúster aislado en
  `EntreRamblas/.odoo_data/validation-postgres`, puerto 55432, usuario `mgs_test`.
  Autenticación trust restringida al localhost, solo para datos sintéticos.
  **Se reseteó una vez esta sesión** (contenía el rastro de pruebas manuales de
  una sesión anterior que falseaba un test; ver sección 4) — es una base
  desechable por diseño, recrearla es seguro y esperado.
- `.odoo_data` contiene logs, filestore y evidencias ignorados por Git.
- `odoo.conf` es una plantilla sin secretos. Conserva filtro `^mi_base_stock$`:
  al iniciar HTTP de pruebas hay que pasar explícitamente el filtro correcto.
- Configuración privada anterior en `odoo.local`, ignorado. No copiar
  credenciales a documentación, Git o archivos de traspaso.
- **Instalación limpia detectada como incompleta**: una base de datos
  realmente nueva instala la compañía con el plan contable **genérico**
  (`generic_coa`), no el español (`es_pymes`), aunque `l10n_es` esté entre las
  dependencias — Odoo no lo hace automático. Sin el plan español no hay tipos
  de IVA reales (0/4/10/21), y el alta de catálogo y las pruebas que dependen
  de impuestos fallan. Se cargó a mano para esta sesión
  (`env['account.chart.template'].try_loading('es_pymes', company)`), pero
  **el addon no lo hace solo todavía**: es un hueco real para la instalación
  limpia (punto 6 de la sección 5), no una decisión de la gestoría — el
  régimen fiscal y la numeración sí lo son y siguen pendientes (punto 3).
- Esta sesión son **~55 rutas sin commit** (`git status --short` las lista):
  modelos, vistas, datos, tests y documentación nuevos y modificados. No
  ejecutar reset/clean ni descartar los archivos sin seguimiento. `venv/`,
  `odoo/`, `.odoo_data/` y `odoo.local` están ignorados, comprobado con
  `git check-ignore`. Comprobado también que ningún secreto entra en el commit
  (el único hallazgo del grep fue el nombre del campo `admin_passwd` dentro de
  una recomendación de seguridad en `README.md`, no un valor).

Documentación: `MANUAL_TIENDA.md` (manual general de tienda y recuperación),
`APERTURA.md` (catálogo y existencias iniciales), `EVENTOS.md` (ramos a medida,
recetas, bodas y alquiler), `RECUENTOS.md`, `DEVOLUCIONES.md`, `INFORMES.md`
(incluye consumo de flor, bajas de caducados y previsión de compra),
`FACTURACION.md`, `INSTALACION.md`, `IMPLEMENTACION.md` (cronología y
evidencias) y `README.md`.

## 3. El plan de continuación, ejecutado esta sesión

Ocho fases, cada una verificada con `test.ps1` en verde antes de pasar a la
siguiente. **121 pruebas Odoo del módulo, 0 fallos, 0 errores** al cierre
(partiendo de 70 al empezar esta sesión).

### Fase 0 — Correcciones

- **Mojibake en `mgs_reception.py`**: 42 líneas de texto con UTF-8 doblemente
  codificado (`"RecepciÃ³n"`, etc.), visibles en la pantalla que más se usa a
  diario. Arreglado por transformación de bytes determinista
  (`s.encode('cp1252').decode('utf-8')`), verificado con AST y `git diff`
  línea a línea: solo cambiaron cadenas y comentarios, ninguna línea de código.
  Guardián nuevo, `tools/check_encoding.py`, enganchado en `test.ps1`.
- **Un ramo dentro de una boda no descontaba nada** (`mgs_event.py`): una
  composición sin receta se podía añadir a una boda y `action_deliver()` la
  saltaba en silencio, sin sacar ni una flor del almacén. Corregido con un
  dominio en el campo, una restricción (`@api.constrains`) y el rechazo en
  `_check_valid()`. Se cierra del todo en la Fase 5, con recetas.
- **Código muerto** en `mgs_config.py` (~50 líneas: apertura de cajón e
  impresión de ticket síncronas, sustituidas hace tiempo por el outbox
  transaccional de `mgs_hardware_job.py` sin que nadie las borrara) y el campo
  zombi `backup_keep`: eliminados.
- **ACL mal etiquetada**: dos filas de `ir.model.access.csv` se llamaban
  `_user` pero apuntaban al grupo manager, dejando a la dependienta sin ACL
  propia sobre `mgs.config` (funcionaba de rebote por `.sudo()`). Corregida.
- **Fijado con test, no arreglado**: la devolución de un ramo NO reingresa las
  flores al stock (están cortadas y montadas) — es la decisión ya documentada
  en `EVENTOS.md`, ahora con una prueba que impide que alguien la "corrija" sin
  darse cuenta de por qué existe. Igual con la convivencia de los dos parches
  de `_create_move_from_pos_order_lines` (`mgs_bouquet.py` / `mgs_pos_stock.py`):
  probada con un ticket mixto ramo + producto suelto, no solo con el orden de
  import.

### Fase 1 y 1B — Quitar la marca Odoo, y lo que sobra en una tienda de dos personas

Todo por herencia de plantillas QWeb/OWL, sin tocar rutas técnicas
(`odoo/`, `odoo-bin`, `odoo.conf`, imports): pestaña y favicon del backend y
del TPV, «Powered by Odoo» del recibo en pantalla, menú de usuario (quita
Documentación/Soporte/Cuenta de Odoo.com/Instalar aplicación), nombre del
acceso directo PWA, título de los PDF, diálogo de sesión caducada, y las 5
cadenas propias que nombraban a Odoo en tooltips y avisos. Se descartó
expresamente la vía de traducción por catálogo `es_ES`: en Python solo lee el
`.po` del propio módulo, y en JS el orden de aplicación depende de un `set()`
— no determinista, cambiaría de un arranque a otro.

Además: **«Vender» entra directo al TPV** (antes abría el kanban nativo de
cajas registradoras, pensado para varios puntos de venta) — con un campo
nuevo (`mgs.config.pos_config_id`) para elegir la caja si algún día hubiera
más de una. Se añadió **Informes → Cierres de caja** para no perder el único
sitio desde donde se veían las sesiones pasadas. Se quitó el reloj de
actividades del systray (avisaba de un cron que nunca existió,
`_mgs_cron_stock_alerts` — comentario obsoleto corregido) y el chatter de
Mermas (seguidores, mensajes): esto lo usan dos personas, no un equipo.

### Fase 2 — Compras y proveedores

**Decisión: modelo propio (`mgs.purchase.order`), no el módulo nativo
`purchase`.** Sus rutas de almacén no pasan por `mgs_reception.action_confirm`,
que es donde nace el coste congelado de cada partida — instalarlo habría
degradado el margen de todo lo comprado, en silencio. Pedido → confirmado →
recibido en parte/del todo, con candado sobre la fila del pedido (mismo orden
que el candado de producto que ya usan recepción y apertura, para que dos
recepciones a la vez contra el mismo pedido no se pisen). La recepción sigue
siendo `mgs.reception`, ahora con `purchase_id`/`supplier_ref`/`document_date`
opcionales — no obligatorios, para no estorbar una compra de urgencia. Nueva
pantalla **Stock → Partidas**, que expone `mgs_supplier_id`/`mgs_received_at`
(se grababan y no se veían en ningún sitio).

### Fase 3 — Consumo real de flor

Un ramo de 12 rosas contaba, en «Productos más vendidos», como 1 unidad de
«Ramo a medida» — el dato que hace falta para comprar (cuántas rosas se
gastan) se perdía. Vista SQL nueva (`mgs.flower.consumption`) sobre
`stock.move.line`, que ya tiene todo unificado con el coste histórico
congelado; un filtro por `location_dest_id.usage = 'customer'` basta para
quedarse con lo realmente vendido (excluye mermas, devoluciones y alquiler
que vuelve). **Hallazgo de plataforma documentado en el propio modelo**: una
vista `_auto=False` no vuelca sola las escrituras pendientes de las tablas que
lee (`search()`/`search_count()`/`read_group()` bypasean el volcado
automático); se corrige forzando `self.env.flush_all()` dentro de `_search()`
— el único punto por el que pasan los cuatro caminos.

### Fase 4 — Caducidad: baja asistida, no automática

**El automatismo detecta, la persona confirma** — `stock.scrap.do_scrap()` es
irreversible, y un PC de tienda puede llevar días sin abrirse. Cron diario que
genera o refresca una única propuesta abierta (`mgs.expiry.writeoff`) con lo
caducado más allá de un margen configurable (`mgs.config.expiry_grace_days`,
2 días por defecto). Confirmar vuelve a comprobar que el stock no cambió desde
que se vio la propuesta (mismo patrón que el recuento físico) y dobla como
candado contra doble clic. El valor de stock del informe mensual se separa
ahora en vendible y caducado.

### Fase 5 — Recetas de ramo, y cierre de la Fase 0

`mgs.bouquet.recipe`: «Ramo novia clásico = 12 rosas + 3 eucalipto», con
`spec_json` precalculado en el servidor y validado contra el MISMO parser que
usa el cobro (`_mgs_parse_components`) — una receta guardada nunca puede
contener algo que luego el TPV rechace. En el TPV, un botón por receta
precarga el diálogo; **sigue pudiéndose ajustar antes de cobrar**, no es un
candado. Cierra la Fase 0: una composición **con receta** ya puede ir en una
boda — se entrega descontando cada componente de la receta, multiplicado por
la cantidad de la línea, nunca la composición en sí (que no tiene existencias).

### Fase 6 — Previsión de compra por campaña

`mgs.purchase.forecast`: San Valentín / Día de la Madre (primer domingo de
mayo, calculado) / Todos los Santos / fechas libres. Mira el consumo real
(Fase 3) del mismo periodo en años anteriores, propone el máximo histórico con
un margen de seguridad menos el stock que ya hay sin caducar, y «Crear pedido»
rellena un `mgs.purchase.order` en borrador agrupado por el proveedor más
frecuente de cada producto (según las partidas ya recibidas). Lo que no tenga
proveedor conocido se queda fuera, avisando cuál es — no bloquea el resto.

### Fase 7 — Tarifas de campaña y descuentos

**Tarifas: `product.pricelist` nativo, envuelto en un asistente simple**
(`mgs.pricelist.campaign`) para que la dueña no vea nunca el formulario nativo.
Comprobados y descartados los tres riesgos: el margen sigue viniendo del coste
histórico, nunca del precio (`_compute_total_cost`); el ramo a medida conserva
su precio manual al cambiar de tarifa (nace con `price_type: "manual"` porque
siempre lleva `price_unit`, y el POS solo recalcula las líneas `"original"`);
el ticket sigue recalculando el IVA desde los subtotales reales. **Descuentos:
ya funcionaban** (`manual_discount` viene activado de serie); se activó
`restrict_price_control` para que solo la propietaria los cambie.
**Fidelización: no se instaló** `loyalty`/`pos_loyalty` — inyectan líneas de
recompensa que atraviesan el prechequeo de stock y podrían bloquear un cobro
por falta de existencias del regalo; para dos personas, la tarjeta de cartón
sellada basta.

## 4. Estado de las pruebas

`.\test.ps1` termina con código 0 y ejecuta, en este orden:

1. Pruebas del archivo de copia (3).
2. Guardián de codificación (`tools/check_encoding.py`).
3. **Las pruebas Odoo del módulo, 0 fallos y 0 errores.**
4. Prueba transaccional de hardware.

Los logs se acumulan en `.odoo_data/mgs-validation.log`: mirar la última
ejecución, no una línea verde antigua.

**Nota sobre falsos fallos ya resueltos, por si vuelven a aparecer**: la base
de pruebas `mgs_validation` acumula datos reales de sesiones de validación
manual en el navegador; un test que asume «no hay ventas hoy» puede fallar por
eso, no por una regresión — comprobar antes de asumir lo peor, y resetear la
base (es desechable) si hace falta. Y una vista de solo lectura (`_auto=False`)
sobre una tabla que se acaba de escribir en la MISMA transacción puede no ver
los datos sin `flush_all()` explícito (ver Fase 3): si se añade otra vista así,
recordar este patrón.

## 5. Lo que sigue pendiente, y por qué

Por orden de lo que bloquea la puesta en producción:

1. **Servicio Windows registrado en el SCM.** El supervisor arranca y para
   bien, pero **nunca se ha registrado como servicio**: hace falta una consola
   con permisos de administrador, que esta sesión no tiene. Falta también
   comprobar reinicio, apagado, recuperación ante fallo, permisos efectivos de
   LocalService y la impresora bajo esa cuenta.
2. **SSD físico.** Falta conectar el disco y comprobar réplica, retención de
   30 días, desconexión y reconexión, espacio insuficiente y una restauración
   real desde el disco externo. Las restauraciones ensayadas son locales.
3. **Cumplimiento SIF / VERI\*FACTU.** Fuera de esta entrega por decisión de la
   propietaria. Los plazos **de usuario** son 1-1-2027 / 1-7-2027, pero el de
   **productores/comercializadores** de software (29-07-2025) ya venció y puede
   aplicar si el programa se considera comercializado a la tienda. Emitir tickets
   hoy **no equivale a cumplir** ni valida nada. Elegir vía y cerrar con la
   gestoría el régimen, los tipos de IVA por familia y la serie de numeración.
   Ver `FACTURACION.md` §2 (reescrito el 10-09-2026).
4. **Jornada física completa**: lectores HID reales, impresora de 80 mm,
   cajón, datáfono manual, pago mixto, merma, devolución, recuento y cierre de
   caja, con desconexiones y un reinicio por medio. Las simulaciones no valen.
5. **Catálogo real.** El asistente de alta está hecho y probado, pero los
   datos los tiene que dar la dueña.
6. **Instalación realmente limpia**: descarga y venv nuevos en una máquina sin
   nada previo. _(10-09-2026: el plan contable español ya lo carga el addon
   (`_mgs_ensure_spanish_chart`), y el instalador `EntreRamblas-Setup.exe`
   monta PostgreSQL dedicado + servicio + acceso directo. Falta compilar el
   `.exe` con Inno Setup y probarlo en una máquina limpia — `ENTREGA_FINAL.md`.)_
7. **Aceptación de UI de lo más nuevo**: los flujos de esta sesión
   (compras, consumo de flor, bajas de caducados, recetas, previsión de
   compra, tarifas de campaña) están verificados por test pero no recorridos
   en el navegador uno a uno, a diferencia de las fases anteriores.
8. **Auditoría de caminos RPC alternativos**: queda por barrer sistemáticamente
   si alguna ruta RPC permite modificar o borrar trazas, y si los datos propios
   del TPV sobreviven a recarga y a trabajo sin conexión.
9. **Commits.** El trabajo hasta el 9-09-2026 y la entrega final del 10-09-2026
   están commiteados en la rama **`finalizar-entrega`** (5 commits, desde
   `14d474d`), a la espera de revisión y de fusionar a `main`. Comprobado que
   no entran secretos (la clave privada de firma vive fuera del repo) y que el
   runtime privado sigue ignorado.
10. **No bloquea nada, es una decisión ya tomada**: el menú «Ajustes» de Odoo
    (Usuarios y compañías, Ajustes generales, modo desarrollador) se oculta
    del todo — no solo las otras ocho apps nativas — porque esta app es de
    gestión de tienda, no de administración de Odoo. _(10-09-2026: el acceso
    pasa a ser **una sola cuenta, la propietaria**, con su propia recuperación
    por clave impresa y herramienta local — `ACCESO.md`. `/odoo/settings`
    sigue respondiendo por URL para quien mantenga el equipo, pero la cuenta
    `admin` ya no tiene contraseña utilizable: se restablece con
    `recuperar-acceso.ps1 -Admin`. Una cuenta separada de dependienta hoy no
    entra por el formulario; sería un cambio en la pantalla de acceso.)_

## 6. Comandos

Desde `EntreRamblas` (PowerShell):

```powershell
.\test.ps1                 # suite completa
.\test.ps1 -Restore        # añade copia y restauración reales
.\test.ps1 -Tags /mi_gestor_stock:TestOpeningStock
```

HTTP de pruebas (sin cron; no usar como producción):

```powershell
.\venv\Scripts\python.exe odoo/odoo-bin -c odoo.conf --db_host=127.0.0.1 --db_port=55432 --db_user=mgs_test -d mgs_validation --db-filter=^mgs_validation$ --http-interface=127.0.0.1 --http-port=8075 --max-cron-threads=0 --logfile=.odoo_data/ui-validation.log
```

Login: `http://127.0.0.1:8075/web/login?db=mgs_validation`.
Usuarios sintéticos y contraseñas en `.odoo_data/ui-validation.json`; no
copiarlas a Git. `prepare_ui_validation.py` **regenera** contraseñas y datos:
leerlo antes de ejecutarlo, no lanzarlo solo para consultar credenciales.

Herramientas: `tools/check_report_pdf.py`, `check_report_pdf_long.py`
(requieren el HTTP de pruebas levantado), `check_service_worker.py`,
`check_backup_restore.py`, `check_hardware_outbox.py`,
`check_encoding.py` (sin requisitos, revisa `custom_addons/` directamente).

## 7. Condiciones

No se deja ningún servidor HTTP de pruebas en ejecución a propósito. PostgreSQL
aislado puede seguir escuchando en 55432: comprobar procesos y puertos, no
asumir que una sesión antigua sigue viva. **No detener el PostgreSQL
principal.** No se ha hecho despliegue final ni commit. La base principal
`mi_base_stock` no se ha tocado en ningún momento.
