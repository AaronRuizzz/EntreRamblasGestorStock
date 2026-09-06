# Entre Ramblas · Clavel & Azahar — Gestor de stock + TPV (Odoo 18)

> Documento de traspaso entre sesiones. Recoge todo lo hecho hasta **2026-09-05**.
> Léelo entero antes de continuar.

---

## 0. Cambios recientes (2026-09-05) — hardware de tienda y copia en disco

- **Los cuatro aparatos de la factura ya tienen sitio en el programa**, sin IoT
  Box y sin depender del navegador. Nueva pantalla **Configuración →
  Dispositivos** (`models/mgs_config.py`, modelo `mgs.config`, registro único):
  lectores, impresora y cajón, con botones de **«Imprimir ticket de prueba»** y
  **«Abrir el cajón»** para validar el montaje el día que se conecte todo.
- **Impresora Approx appPOS80AM**: el servidor le habla **ESC/POS** directamente
  (`models/mgs_escpos.py`, sin dependencias externas) por **red (TCP 9100)**, por
  la **cola de Windows en modo RAW** o por una **ruta/puerto**. Los tickets del
  TPV salen solos, sin el diálogo de impresión del navegador (adiós al apaño del
  *kiosk-printing*), y si la impresora no responde el TPV vuelve solo a imprimir
  por el navegador: **una venta nunca se queda sin ticket**.
- **Cajón Approx CASH01**: se abre con el pulso `ESC p` que la impresora manda
  por el RJ11. El TPV ya llama a `openCashbox()` al cobrar en efectivo o al dar
  cambio; ahora esa llamada llega de verdad al cajón
  (`static/src/js/pos_hardware.js`). **Esto era el punto dudoso de §2 y queda
  resuelto sin IoT Box.**
- **Etiquetas de producto en la térmica**: la impresora dibuja el código de
  barras ella misma (comando `GS k`), así que no hace falta PDF ni imagen.
  Botones en la ficha del producto y en Recepción (una etiqueta por línea o
  todas de golpe).
- **Códigos internos para lo que llega sin EAN** (flor a granel, envoltorios,
  composiciones propias): botón «Generar código interno», que crea un **EAN-13
  válido** con prefijo `28` — a propósito fuera de los prefijos que el TPV
  reserva para descuentos (`22`), precio incrustado (`23`) y cajero/cliente
  (`041`/`042`).
- **Los dos lectores** siguen funcionando por donde funcionaban (HID = teclado),
  y ahora además: se les puede quitar el prefijo/sufijo que se les programe, se
  ajusta el retardo entre teclas para el Bluetooth desde la pantalla de
  Configuración, y **escanear en el panel de Stock abre la ficha del producto**
  (consultar precio y existencias con la pistola, sin teclear).
- **Persistencia en un archivo del disco** (`models/mgs_backup.py`): cada pocas
  horas se deja en disco **un único `.zip` con todo dentro** —base de datos,
  imágenes y adjuntos—, en el formato de copia nativo de Odoo. Además del
  histórico con fecha, se mantiene siempre
  `.odoo_data\backups\mi_base_stock-ultima.zip`, un nombre fijo que siempre
  contiene el estado más reciente (cómodo para sincronizar con el SSD externo).
  Para volver atrás: **`.\restore-backup.ps1`**. Detalle completo en **§11**.

## 0bis. Cambios recientes (2026-09-03, tarde)

- **Recepción con dos modos.** «Producto existente» (escaneas y se reutiliza toda
  su información, refrescando fecha de recepción y caducidad) y «Producto nuevo»
  (rellenas nombre, categoría, precio, coste y caducidad, y le asignas el código
  escaneándolo). Ya no se puede elegir un producto a mano de una lista.
- **Caducidad**: `mgs_reception_date` y `mgs_expiry_date` en el producto, que se
  actualizan en cada entrada de mercancía.
- **Avisos configurables** (modelo `mgs.stock.alert`, menú Stock → Alertas): por
  cantidad («rosas: avísame con 10 o menos», se evalúa en vivo) o periódicos
  («cuánto clavel tengo, cada semana/mes/X días», los genera un `ir.cron`).
  Aparecen como tarjetas en el panel de Stock.
- **Panel de Stock** (`static/src/js/stock_dashboard.js`, componente OWL propio y
  ahora pantalla de inicio): avisos activos, caducidades próximas, los 3 productos
  con menos stock y el listado agrupado por categorías.
- **«Compra» fuera del menú.** El TPV sigue instalado y registrando cada venta
  (descuenta stock, ticket, cajón); simplemente se abre aparte a pantalla completa
  en `/pos/ui`. Los informes siguen alimentándose de él.
- **Informe mensual en PDF** (Informes → Informe mensual): ventas del periodo,
  coste de lo vendido, beneficio bruto, gasto en reposición, balance y valor del
  stock restante. Más gráficas de ventas y ranking de productos más vendidos.
- **Menos ruido en el panel de control.** Recepción es un flujo de trabajo, no
  una ficha: se le quitan «Nuevo», la rueda de ajustes y el guardar/descartar
  genéricos (el icono de nube confundía), porque la acción de verdad son sus
  botones de cabecera. Se hace con `create/duplicate/delete="false"` en el arch
  más `js_class="mgs_clean_form"` (`static/src/js/clean_form.js`), que solo añade
  una clase al raíz del formulario para poder acotar el CSS a esa pantalla —
  **nunca un `display:none` global**. La lista de Stock pierde «Nuevo» (los
  productos se dan de alta en Recepción) y la ficha de producto pierde
  «Duplicar». La lista de Alertas deja de ser editable en línea: «Nuevo» abre el
  formulario, donde los campos cambian según el tipo de aviso.
- **Página de inicio** (`static/src/js/home.js`, acción cliente `mgs_home`, y ya
  la pantalla que se abre tras el login): emblema, nombre de la tienda y tres
  accesos grandes a Recepción, Stock e Informes, más un aviso discreto si hay
  avisos de stock pendientes. **No ocupa sitio en el menú**: la acción va en el
  propio `menu_mgs_root`, así que pulsar «Gestor de Stock» en la barra superior
  (o su icono en el lanzador de apps) vuelve aquí. Odoo solo desciende al primer
  hijo con acción cuando la app no tiene la suya
  (`web/models/ir_ui_menu.py`, `load_web_menus`).
- **«Nuevo» con nombre propio**: el botón genérico de Odoo no dice qué crea. En
  Alertas se sustituye por uno que pone **«Nuevo aviso de stock»** y abre un
  diálogo (`<header><button display="always">` en la lista, patrón nativo que
  usa el propio core).
- **Barra de navegación rehecha**: el nombre de la app se separa con un filete
  del grupo de secciones, y Recepción / Stock / Informes se ven como pestañas
  uniformes (misma altura, mismo relleno, pastilla redondeada), tanto las hojas
  como los desplegables, con estados de hover y activo legibles.

## 0ter. Cambios recientes (2026-09-03, mañana)

- **Limpieza total: el módulo se reduce a 4 flujos.** `mi_gestor_stock` pasa de
  "maquillaje CSS sobre Odoo estándar" a una app propia con menú explícito:
  **Recepción** (pantalla de escaneo propia), **Stock** (Productos + Alertas),
  **Compra** (TPV) e **Informes** (Ventas/balance + Más vendidos). Se oculta
  todo lo demás (Inventario, TPV nativo, Contactos, Facturación, Tableros,
  Apps, Discuss); solo queda visible **Ajustes**, y solo para el administrador
  (ya restringido por grupo). `backend.scss` se reescribió desde cero (de
  ~1030 líneas y ~400 `!important` a ~170 sin ninguno real): ya no oculta el
  chatter, los smart buttons, los botones de cabecera («Validar»/«Confirmar»)
  ni las pestañas de los formularios de forma global. Detalle completo en
  §6bis-§6quinquies. Plan de la reestructuración:
  `C:\Users\Usuario\.claude\plans\busco-una-limpieza-total-vivid-aurora.md`.

## 0quater. Cambios anteriores (2026-09-02)

- **BD reproducible desde el repo.** La base de datos ya **no se sube a git**;
  se reconstruye idéntica en cualquier equipo con **`bootstrap.ps1`** (crea venv,
  instala deps y crea `mi_base_stock` instalando `mi_gestor_stock`). Todas las apps
  del proyecto (Inventario, TPV, Contactos, `l10n_es`) están ahora en `depends` del
  `__manifest__.py`, así `-i mi_gestor_stock` reproduce el mismo conjunto de módulos.
  Flujo push/pull entre compañeros documentado en §5. `start-odoo.ps1 -Update/-Init`
  ya pasa `-d mi_base_stock` solo.
- **`venv\` y `odoo\` NO están en el repo** (`.gitignore`). Cada equipo los crea:
  `bootstrap.ps1` hace el `venv`; el fuente de Odoo se clona con
  `git clone --depth 1 --branch 18.0 https://github.com/odoo/odoo.git odoo`.
  En el PC de desarrollo actual son *junctions* a la carpeta antigua
  `C:\Users\Usuario\Desktop\EntreRamblas\{venv,odoo}`.
- **El proyecto se movió de carpeta.** Antes: `C:\Users\Usuario\Desktop\EntreRamblas\`.
  Ahora: **`C:\Users\Usuario\Desktop\EntreRamblasGestorStock\EntreRamblas\`**
  (la raíz del repositorio git es `EntreRamblasGestorStock`; los archivos del proyecto
  viven en el subdirectorio `EntreRamblas\`).
  - `odoo.conf` y `start-odoo.ps1` usan solo rutas relativas → no necesitaron cambios.
  - El `venv` apuntaba a la ruta antigua; se regeneró in situ con `python -m venv venv`
    y se reescribieron los lanzadores `pip.exe` / `pybabel.exe` / `pysassc.exe`.
- **Fase 2 completada** (apps core): ver §3.
- **Pantalla de inicio arreglada**: tras el login se abre **Inventario → Resumen**,
  ya no "Conversaciones" (Discuss). La app Discuss se ha ocultado del menú. Ver §7bis.
- **Toda la interfaz en español (es_ES)**: idioma cargado y fijado como único activo
  (en_US desactivado), idioma por defecto de usuarios y contactos = español. Ver §7ter.
- **Logo real puesto** (clavel + azahar). El emblema SVG se rasterizó a PNG y se aplica
  como logo de empresa (backend + informes) y de la pantalla de login. Ver §7.
- **"My Company" eliminado**: la empresa y su contacto se llaman
  "Entre Ramblas · Clavel & Azahar"; el usuario admin ahora es "Administrador".
  El nombre/logo se aplican desde código Python (`models/res_company.py`) porque
  `base.main_company` es `noupdate` y un `<record>` normal lo ignoraba. Ver §7.

---

## 1. Objetivo del proyecto

Montar, para una **floristería**, un programa de **gestión de stock / inventario + Punto de Venta (TPV)**
reutilizando los módulos de **Odoo 18 Community**, personalizándolo mediante un **módulo propio**
(`mi_gestor_stock`, sin tocar el código fuente de Odoo, para no romper futuras actualizaciones).

Requisitos del cliente:

- Al vender un producto en el TPV, que se **descuente automáticamente del stock**. ✅ (nativo de Odoo)
- Que funcione **100% en local, sin depender de internet** para el día a día. ✅
- Interfaz con **colores calmados** (se pasará mucho tiempo revisando stock). ✅
- Pantalla de login personalizada con su marca. ✅

### Máquinas

| Equipo | Rol |
|---|---|
| **PC actual** (`DESKTOP-49BLHDL`, usuario `Usuario`) | **Solo desarrollo.** Aquí se construye todo. |
| **PC nuevo PcCom i5-12400 / 16 GB / Win 11 Pro** | **Producción.** Aquí funcionará con todo el hardware conectado. La BD vivirá en el disco de este PC (el cliente dará detalles). |

---

## 2. Hardware comprado (factura PC Componentes 19/08/2026)

| Equipo | Uso | Integración | ¿Drivers? |
|---|---|---|---|
| **Honeywell Voyager XP 1472g** (Bluetooth 1D/2D) | Lector principal | Modo **HID teclado** (por defecto). Emparejar leyendo el código "Bluetooth HID" del manual. Sufijo = Enter. Odoo lo detecta solo | **No** |
| **PcCom lector inalámbrico** | Lector secundario / repuesto | Dongle 2.4 GHz, HID teclado | **No** |
| **Approx appPOS80AM** (térmica 80 mm USB/LAN) | Tickets / etiquetas | Impresora normal de Windows (driver genérico ESC/POS "POS-80" de approx). Odoo imprime PDF con wkhtmltopdf. Para impresión automática sin diálogo → Chrome en modo *kiosk-printing* | **Sí** (una vez) |
| **iggual papel térmico 80×80** | Consumible | — | — |
| **Approx CASH01** (cajón portamonedas) | Caja de efectivo | Se abre por señal RJ11 **desde la impresora**. En Odoo Community sin *IoT Box* la apertura automática NO está garantizada. Opciones: (a) firmware "abrir cajón al cortar" de la impresora, (b) IoT Box con Raspberry Pi, (c) llave manual. **A validar con el hardware físico en el PC i5** | — |
| **PcCom Work i5-12400 / 16 GB / W11 Pro** | PC de producción | Suficiente para Odoo + PostgreSQL local | — |
| **Monitor Alurin 27" FHD** + combo teclado/ratón MK20 | Periféricos | — | **No** |
| **Corsair EX300U 1 TB SSD externo** | Recomendado para **copias de seguridad** de la BD + filestore | — | **No** |

### Notas sobre el TPV en Community (sin IoT Box)

> **Actualizado el 2026-09-05**: lo de abajo era el punto de partida de Odoo
> estándar. El módulo ya no depende de nada de eso — habla ESC/POS directamente
> con la impresora y dispara el cajón por el RJ11. Ver **§11**.

- **Ticket**: de fábrica sale como PDF y con Chrome en *kiosk-printing* se imprime sin diálogo. **Ya no hace falta**: el ticket se manda en ESC/POS desde el servidor.
- **Cajón**: Odoo solo lo abre de forma fiable con impresora Epson *ePOS* o *IoT Box*, y la Approx es ESC/POS genérica. **Resuelto** parcheando `openCashbox()` del TPV para que el pulso salga por nuestra impresora (`static/src/js/pos_hardware.js`).
- Odoo instaló `pos_epson_printer` automáticamente pero **solo sirve para impresoras Epson**; no se usa.

---

## 3. Entorno instalado (PC de desarrollo)

Todo bajo `C:\Users\Usuario\Desktop\EntreRamblasGestorStock\EntreRamblas\`

| Componente | Detalle |
|---|---|
| **Python** | 3.12.10 (Windows Store) |
| **PostgreSQL** | 16.15 (winget). Servicio Windows `postgresql-x64-16`. Superusuario `postgres` / `postgres`. Rol de Odoo: **`odoo` / `odoo`** (con CREATEDB). Binarios en `C:\Program Files\PostgreSQL\16\bin` |
| **Odoo** | 18.0 Community, clon superficial (`--depth 1`) de `github.com/odoo/odoo` rama `18.0`, en `odoo\` |
| **venv** | `venv\` — virtualenv con `odoo\requirements.txt` instalado. `python-ldap` se omitió (sin wheel para Windows → sin login LDAP, irrelevante). Regenerado 2026-09-02 tras el cambio de carpeta |
| **wkhtmltopdf** | 0.12.6 (build "patched qt") en `C:\Program Files\wkhtmltopdf\bin`. En el PATH de usuario y en `start-odoo.ps1` |
| **OCA** | `custom_addons\stock-logistics-barcode\` (rama 18.0) — clonado, **no instalado**. Aporta `web_ir_actions_client_scan`, generadores de códigos de barras, informe de etiquetas de picking, `product_multi_barcode` |
| **Módulo propio** | `custom_addons\mi_gestor_stock\` |
| **Base de datos** | `mi_base_stock` (sin datos demo) |
| **Config** | `odoo.conf` |
| **Arranque** | `start-odoo.ps1` |

### Fase 2 — Apps core de Odoo 18 (estado 2026-09-02)

| App pedida | Módulo | Estado |
|---|---|---|
| **Inventario** (Inventory) | `stock` | ✅ Instalado. Almacenes, reglas push/pull de reabastecimiento, trazabilidad por lotes/números de serie. |
| **Punto de Venta** (POS) | `point_of_sale` | ✅ Instalado. Interfaz de caja Odoo 18, descuento de stock al vender. |
| **Contactos** (Contacts) | `contacts` | ✅ Instalado (Fase 2). Directorio unificado de clientes y proveedores. |
| **Código de Barras** (Barcode) | `barcodes` | ✅ Motor instalado. Permite escanear en formularios del backend (recepciones, entregas, ajustes de inventario) y en el TPV. |

> ⚠️ **La app "Barcode" con interfaz de escaneo dedicada (`stock_barcode`) es de Odoo
> Enterprise** y aparece como *uninstallable* en Community. Se decidió usar solo el motor
> nativo `barcodes`. Si más adelante se quiere un flujo de escaneo más completo, están
> descargados (sin instalar) los módulos OCA en `custom_addons\stock-logistics-barcode\`:
> `web_ir_actions_client_scan`, `product_multi_barcode`, `barcodes_generator_product`
> (este necesita el paquete Python `python-barcode`), `stock_picking_product_barcode_report`.

### Módulos instalados en `mi_base_stock` (62 en total)
`base`, `web`, `mail`, `stock`, `barcodes`, `barcodes_gs1_nomenclature`, `product`,
`stock_account`, `account`, `l10n_es`, `l10n_es_edi_facturae` (localización fiscal española:
IVA 21/10/4, plan PYMEs, validación NIF), `point_of_sale`, `contacts`, `stock_sms`,
`pos_epson_printer`, `pos_sms`, … y `mi_gestor_stock`.

---

## 4. Acceso e instalación actuales

La configuración con credenciales se guarda en un archivo privado `odoo.local`,
ignorado por Git. `odoo.conf` es una plantilla sin secretos para pruebas.
Las instalaciones nuevas generan una contraseña única en un archivo local
`<base>-first-access.secret`. El módulo no cambia contraseñas existentes.

## 5. Arranque, actualización y recuperación

Consulta [INSTALACION.md](INSTALACION.md) para los comandos actuales y
[IMPLEMENTACION.md](IMPLEMENTACION.md) para la evidencia y los pendientes.
Los comandos y notas históricas del resto de este documento describen versiones
anteriores; la guía de instalación actual prevalece sobre ellos.

No se ofrece un borrado automático de bases. La recuperación usa una base nueva
para conservar la original. El instalador comprueba la revisión Odoo fijada y
usa `requirements-windows.lock`.

## 6. Estructura del módulo `custom_addons\mi_gestor_stock\`

```
__manifest__.py
__init__.py                     # importa models/
models/
  __init__.py
  res_company.py                # aplica marca (nombre+logo) e idioma español
  product_template.py           # defaults de floristería, alertas, datos del panel, etiquetas
  mgs_reception.py              # wizard de Recepción (pantalla de escaneo)
  mgs_stock_alert.py            # avisos por cantidad y periódicos (+ su cron)
  mgs_monthly_report.py         # asistente del informe mensual en PDF
  mgs_config.py                 # § HARDWARE: lectores, impresora, cajón y ajustes de copia
  mgs_escpos.py                 # § HARDWARE: comandos ESC/POS y transportes (sin dependencias)
  mgs_backup.py                 # § COPIAS: volcado a un .zip del disco + cron + retención
data/
  branding.xml                  # marca/idioma + desactiva registro público + fix salida TPV
  ux_defaults.xml               # pantalla de inicio, home action, oculta apps que no se usan
  cron_alerts.xml               # ir.cron cada 6 h: avisos periódicos de stock
  mgs_hardware_data.xml         # registro único de configuración (noupdate), secuencia, cron de copias
security/
  ir.model.access.csv           # ACL de los modelos mgs.*
views/
  mgs_menus.xml                 # ÚNICA app visible: Recepción · Stock · Informes · Configuración
  mgs_reception_views.xml       # formulario + acción de la pantalla de Recepción
  mgs_alert_views.xml           # lista/formulario de avisos de stock
  mgs_dashboard_views.xml       # acciones cliente: inicio y panel de Stock
  product_views.xml             # ficha de producto simplificada + lista/buscador de Stock
  pos_report_views.xml          # acciones de Informes (reutilizan report.pos.order nativo)
  mgs_config_views.xml          # pantalla de Dispositivos + historial de copias
  login_templates.xml           # personalización de la pantalla de login
report/
  mgs_monthly_report.xml        # plantilla QWeb del informe mensual
static/src/
  img/
    logo-emblema.png / logo.png / favicon.png   # emblema a color, USADOS (login/empresa/favicon)
  scss/
    login.scss                  # estilos de la pantalla de login (paleta azul pizarra)
    backend.scss                # estilos del backend, con ámbito acotado (ver §6bis)
    primary_variables.scss      # color de marca de Odoo ($o-community-color, etc.)
  js/
    title.js                    # título de pestaña + limpieza mínima del systray
    clean_form.js               # js_class que marca los formularios-flujo (Recepción)
    home.js / home.xml          # página de inicio
    stock_dashboard.js / .xml   # panel de Stock (escanear aquí abre la ficha del producto)
    pos_hardware.js             # § HARDWARE: puente TPV ↔ impresora ESC/POS y cajón
```

### `__manifest__.py` — puntos clave
- `depends`: `["stock", "barcodes", "web", "point_of_sale", "contacts", "l10n_es"]`
- `application: True` — el módulo se comporta como una app propia con su icono
  (`static/description/icon.png`) en el lanzador.
- `data`: `security/ir.model.access.csv`, `data/branding.xml`, `data/cron_alerts.xml`,
  `views/mgs_reception_views.xml`, `views/product_views.xml`, `views/pos_report_views.xml`,
  `views/mgs_menus.xml`, `views/login_templates.xml`, `data/ux_defaults.xml` — **este orden
  importa**: `mgs_menus.xml` necesita las acciones ya cargadas, y `ux_defaults.xml` necesita
  `menu_mgs_root` y `action_mgs_products` ya definidos (ambos van al final).
- **Python**: `models/res_company.py` hereda `res.company` (marca + idioma, sin cambios);
  `models/product_template.py` añade los campos de alerta (`mgs_alert_on`, `mgs_min_qty`,
  `mgs_low_stock`) y el método del cron (`_mgs_cron_stock_alerts`); `models/mgs_reception.py`
  es el wizard (`TransientModel`) de la pantalla de Recepción.
- `web.assets_backend`: `backend.scss`, `title.js`
- `web.assets_frontend`: `login.scss`  ← **el login usa el bundle FRONTEND, no el backend**
- `web._assets_primary_variables`: `primary_variables.scss` (prepend)

---

## 7. Personalización de la marca — hecho

> **Rediseño del login (2026-09-02, v2):** `login.scss` reescrito en el **azul
> pizarra del backend** (`#0f172a` / `#1e293b` / `#1e3a5f`, mismo `backend.scss`)
> para unificar el tema. Fondo perla frío con brumas azules, tarjeta blanca con
> filete azul y sombra, tarjeta más ancha (`max-width: 468px`) y responsive
> (`@media max-width: 520px`), campos y botón redondeados con foco/hover. El
> emblema (`static/src/img/logo-emblema.png`, `<img>` directo, **sin recorte
> circular** — el recorte cortaba las esquinas de la ilustración) se muestra a
> ~72% del ancho. Como el emblema ya lleva el nombre de la floristería, **no hay
> rótulo ni pie de marca** en la tarjeta (sobraba repetirlo).
>
> **Emblema definitivo (a color) ya puesto.** Origen:
> `Desktop\Clavel-y-Azahar\public\logo-orginal2.png` (1254×1254). Procesado con
> Pillow: relleno por inundación desde las 4 esquinas (`ImageDraw.floodfill`,
> `thresh=28`) para dejar el fondo crema **transparente**, recorte del margen y
> lienzo cuadrado. Salidas en `static/src/img/`: `logo-emblema.png` 900px (login),
> `logo.png` 560px (`res.company.logo`, backend + informes) y `favicon.png` 256px.
> El vector monocromo original queda como `logo-emblema.svg` (solo referencia:
> es de un solo color `#061b0e`, no sirve para la versión a color).
>
> - **Selector "Elija un usuario" eliminado**: la plantilla `mgs_login` quita el
>   `<owl-component name="web.user_switch"/>` y le fuerza al `<form>` la clase
>   `oe_login_form` sin `d-none` (ese componente era quien destapaba el formulario).
> - **Credenciales del admin** ahora las fija el módulo (`_mgs_setup_spanish` en
>   `res_company.py`): en una BD nueva el login pasa de `admin` a
>   `entreramblasclavelyazahar@gmail.com` / `[credencial local retirada]`. En cuanto el
>   login deja de ser `admin`, un `-u` posterior ya no toca la contraseña.

| Elemento | Estado |
|---|---|
| Logo en el login | ✅ Emblema a color (`logo-emblema.png`, fondo transparente) |
| Logo de la empresa (backend + informes PDF) | ✅ Mismo emblema, `logo.png` → `res.company.logo` |
| Fondo del login | ✅ Degradado perla frío con brumas azules |
| Botón "Iniciar sesión" | ✅ Azul pizarra `#1e293b` |
| "Powered by Odoo" | ✅ Eliminado (`disable_footer` = True) |
| "Manage Databases" | ✅ Eliminado (`disable_footer` + `list_db = False`) |
| Registro público de cuentas | ✅ Eliminado (`auth_signup.allow_uninvited = False`) |
| Selector "Elija un usuario" | ✅ Eliminado (`web.user_switch` fuera + `d-none` quitado del form) |
| Pie propio del login | ✅ Sin texto (el emblema ya lleva el nombre), solo línea de cierre |
| Título de la pestaña | ✅ "Gestión de stock" (login vía `<t t-set="title">`, backend vía `title.js`) |
| Favicon del login | ✅ El emblema (`favicon.png` vía `x_icon` en la plantilla) |
| Favicon del backend | ⚠️ Por defecto de Odoo. `res.company.favicon` **no existe** en Community sin el módulo `website` |
| Nombre de la empresa | ✅ "Entre Ramblas · Clavel & Azahar" (`_mgs_apply_branding` en `res_company.py`) |
| "My Company" / "Administrator" | ✅ Renombrados a la empresa y a "Administrador" |
| Moneda de la empresa | ✅ EUR (Odoo la instala en USD; `_mgs_apply_branding` la corrige) |
| Color de marca de Odoo | ✅ Azul `#1e3a5f` vía `primary_variables.scss` en `web._assets_primary_variables` |

---

## 6bis. Los flujos de la app

Tras el login se abre el **panel de Stock** dentro de **Gestor de Stock**, la
única app del sistema (`views/mgs_menus.xml`):

1. **Recepción** (`models/mgs_reception.py` + `views/mgs_reception_views.xml`):
   pantalla de escaneo con **dos modos** (campo `mode`):
   - *Producto existente*: se escanea y, como ya está dado de alta, se reutiliza
     toda su información; solo se refrescan `mgs_reception_date` y
     `mgs_expiry_date`. Repetir el escaneo suma unidades a la misma línea.
   - *Producto nuevo*: se rellenan nombre, categoría, precio, coste y caducidad,
     y el escaneo **asigna el código de barras** al producto que se va a crear.

   Hereda `barcodes.barcode_events_mixin` (nativo del módulo `barcodes`), así que
   el lector Honeywell (HID + Enter) funciona en cualquier parte de la pantalla,
   sin necesidad de tener el foco en un campo — hay además un campo de respaldo
   para teclear el código a mano. Al pulsar "Guardar en almacén" crea y valida un
   `stock.picking` de entrada de verdad (trazabilidad completa: `WH/IN/000xx`),
   sin pedir proveedor ni albarán manual.
   > ⚠️ Al tocar este fichero, recuerda: en un `TransientModel` nuevo,
   > `self.line_ids = [Command.create(...)]` dentro de un método que añade
   > líneas **borra las líneas anteriores** (no tiene `_origin`). Hay que
   > concatenar con `self.line_ids |= self.env[...].new({...})`.
2. **Stock**, con tres entradas:
   - *Panel* (`static/src/js/stock_dashboard.js`, acción cliente
     `mgs_stock_dashboard`, **pantalla de inicio**): avisos activos, caducidades
     próximas, los 3 productos con menos stock y el listado agrupado por
     categorías. Todos los datos salen de una única llamada a
     `product.template.mgs_dashboard_data()`.
   - *Productos* (`views/product_views.xml`): lista filtrada a `is_storable`
     (fuera los técnicos del TPV/localización: Propinas, DUA Valoración…),
     agrupada por categoría, con filas en rojo si están bajo mínimo.
   - *Alertas* (`models/mgs_stock_alert.py`): avisos configurables por producto,
     **por cantidad** (se evalúan en vivo, así desaparecen solos al reponer) o
     **periódicos** (los genera el `ir.cron` cada 6 h, se descartan a mano).

   El campo `mgs_low_stock` es un booleano **no almacenado con `search=`** propio
   (`_search_mgs_low_stock` en `models/product_template.py`) — un dominio tipo
   `[('qty_available','<=','min_qty')]` no es una opción: Odoo compara campo
   contra literal, y lanza `UserError` si el operando derecho no es un número.
3. **Informes** (`views/pos_report_views.xml` + `report/mgs_monthly_report.xml`):
   gráficas de ventas y ranking de más vendidos sobre el modelo nativo
   `report.pos.order`, más un **informe mensual en PDF** (asistente
   `mgs.monthly.report`) con ventas, coste de lo vendido, beneficio bruto, gasto
   en reposición, balance y valor del stock restante.

**El TPV no está en el menú** (se quitó «Compra»), pero sigue instalado y
registrando cada venta — se abre aparte a pantalla completa en `/pos/ui`, que es
como se usa en el mostrador. **Importante**: al cerrar una sesión de TPV, Odoo
redirige a la acción cliente `point_of_sale.action_client_pos_menu`, cuyo
`menu_id` por defecto es `point_of_sale.menu_point_root` — como ese menú está
desactivado (ver §7bis), `data/ux_defaults.xml` lo reapunta a
`mi_gestor_stock.menu_mgs_root` con un `<function model="ir.actions.client"
name="write">` (el `<record>` normal se ignora: ese registro es `noupdate="1"`).

`_mgs_rename_picking_types()` en `res_company.py` sigue renombrando
"PoS Orders" → "Pedidos TPV" (nombre del albarán generado al vender).

### `backend.scss` reescrito desde cero

De ~1030 líneas / ~400 `!important` a ~170 líneas sin ninguno real. Regla de
oro: nada de `display:none` global sobre botones, pestañas o smart buttons —
eso se hace en el **arch de la vista** (`invisible="1"`), no en CSS. Se
eliminó en concreto: la ocultación global del chatter (rompía las alertas de
stock, que usan actividades), `.oe_stat_button:not(:first-child)` (ocultaba
smart buttons en cualquier formulario), `.o_form_view header
button:not(:first-child)` (ocultaba "Validar"/"Confirmar" en los albaranes),
`.o_notebook_headers{display:none}` (ocultaba pestañas en toda la app) y el
rediseño CSS del kanban de "Inventario → Resumen" (esa pantalla ya no es
accesible, al desactivarse `stock.menu_stock_root`). Lo que queda: navbar,
hoja de formulario, botones con ámbito acotado, listas, kanban de productos y
la caja de escaneo de Recepción (`.mgs-scan-box`).

### Logo — sin cambios respecto a antes de esta limpieza
`static/src/img/logo-emblema.png` (login + `res.company.logo`), `logo.png`
(logo de respaldo) y `favicon.png` son los únicos ficheros de imagen que
quedan en el módulo — los SVG originales y los PNG antiguos sin usar se
borraron (~2 MB). Para cambiar el logo: sustituye esos PNG y
`.\start-odoo.ps1 -Update mi_gestor_stock` (`_mgs_apply_branding()` recarga
`logo.png` en la empresa en cada `-u`).

### Ajustar colores
Paleta azul pizarra, definida en dos sitios que conviene mantener
sincronizados: `static/src/scss/login.scss` (variables `$navy-dark` / `$navy`
/ `$navy-action` al principio del fichero) y `static/src/scss/backend.scss`
(`$mgs-navy` / `$mgs-slate` / `$mgs-blue` al principio, misma paleta).

---

## 7bis. Pantalla de inicio y menús ocultos (`data/ux_defaults.xml`)

**`mi_gestor_stock/data/ux_defaults.xml`** hace tres cosas:

1. **Pantalla de inicio = "Stock → Productos"** (`mi_gestor_stock.action_mgs_products`).
   Se fija el campo *Home Action* (`res.users.action_id`) del administrador
   (`base.user_admin`) y de la plantilla de usuarios nuevos (`base.default_user`),
   mediante un `<function model="res.users" name="write">` (un `<field>` normal **no
   funciona** con este campo).
2. **Reapunta la salida del TPV** a `menu_mgs_root` (ver §6bis, punto 3) — si no, al
   cerrar una sesión de caja el usuario aterriza en un menú desactivado.
3. **Oculta todos los menús raíz salvo el nuestro y "Ajustes"** (`active = False` sobre
   cada uno): `mail.menu_root_discuss`, `contacts.menu_contacts`,
   `spreadsheet_dashboard.spreadsheet_dashboard_menu_root`,
   `point_of_sale.menu_point_root`, `account.menu_finance`, `stock.menu_stock_root`,
   `base.menu_management`, `base.menu_tests`. **`base.menu_administration` (Ajustes) NO
   se toca**: ya está restringido por grupo (`base.group_system` /
   `base.group_erp_manager`), así que un usuario de tienda no lo ve sin necesidad de
   desactivarlo — y sigue haciendo falta para configurar TPV, impuestos y almacén.

Verificado por login HTTP real (`/web/webclient/load_menus`) tras un `bootstrap.ps1
-Reset` completo: el lanzador de apps muestra exactamente **"Gestor de Stock"** y
**"Ajustes"**; `action_id` del admin = `Stock` (`product.template`); los 6 elementos hoja
del menú (Recepción, Productos, Alertas, Compra, Ventas y balance, Productos más
vendidos) resuelven `actionID`; cerrar una sesión de TPV vuelve a la app, no a un menú
en blanco. Reproducible: `-u mi_gestor_stock` vuelve a aplicar los tres puntos.

Para revertir algún menú oculto: quita su `<record>` de `ux_defaults.xml` y `-u`.
Para cambiar la pantalla de inicio de un usuario puntualmente: Ajustes → Usuarios →
(usuario) → pestaña *Preferencias* → *Acción de inicio*.

---

## 7ter. Idioma: todo en español (`models/res_company.py` → `_mgs_setup_spanish`)

**Hecho (2026-09-02):** la interfaz estaba en inglés. Ahora:

1. Se **activa `es_ES`** y se **cargan las traducciones** de todos los módulos
   instalados (`base.language.install` → `lang_install()`, lee los `i18n/es.po` que
   ya vienen en el repo de Odoo — **sin internet**). Solo se cargan la primera vez;
   en `-u` posteriores no se recargan (rápido).
2. Se **desactiva `en_US`** → `es_ES` es el único idioma activo, así la **pantalla de
   login** y cualquier página anónima también salen en español. (Internamente `en_US`
   sigue siendo el idioma fuente aunque esté inactivo.)
3. Idioma **por defecto** de contactos (`ir.default` sobre `res.partner.lang`) y de
   todos los usuarios/contactos existentes = `es_ES`.
4. El usuario `base.user_admin` pasa a llamarse **"Administrador"**.

Verificado por login HTTP real: menús raíz = *Contactos, Tableros, Punto de venta,
Facturación, Inventario, Aplicaciones, Ajustes*; login = *Correo electrónico /
Contraseña / Iniciar sesión*; `user_context.lang = es_ES`.

**Recargar traducciones** tras instalar módulos nuevos: Ajustes → Traducciones →
*Cargar una traducción* (o `-u <módulo>` reimporta su `es.po`).
**Reactivar inglés** (si hiciera falta): Ajustes → Traducciones → Idiomas → `en_US` → activar.
La localización fiscal española (`l10n_es`) ya estaba instalada (§3).

---

## 8. Trucos / gotchas aprendidos (Odoo 18)

- **`-d mi_base_stock` obligatorio** en comandos `-i` / `-u` (ver §5).
- **`res.users.action_id` (Home Action)** no se puede fijar con `<field ... ref=...>` en
  un data XML; hay que usar `<function model="res.users" name="write">`.
- **`base.main_company` es `noupdate`**: un `<record id="base.main_company">` en un módulo
  propio se **ignora en `-u`** (nombre, logo… no cambian). Solución: aplicarlo desde
  código Python llamado con `<function ... eval="[[]]"/>` (ver `models/res_company.py`).
- **`<function model="X" name="Y"/>` sin `<value>` peta** con `IndexError` en Odoo 18
  (`call_kw` espera al menos el arg de ids). Usar `eval="[[]]"` para pasar un recordset vacío.
- **`res.company.favicon` no existe** en Community sin el módulo `website`.
- **SVG → PNG**: no hay `cairosvg` ni Inkscape en el entorno. Se usa
  `wkhtmltoimage` (viene con wkhtmltopdf) sobre una copia del SVG con `width`/`height`
  explícitos (si solo tiene `viewBox`, wkhtmltoimage lo renderiza como una tira de 10 px),
  y luego Pillow recorta márgenes transparentes y centra en un lienzo.
- **Traducciones en Odoo 18**: ya no hay tabla `ir_translation`; van en columnas `jsonb`
  de cada modelo (`{"en_US": "...", "es_ES": "..."}`). `res.users.lang` es un campo
  relacionado de `res.partner`; en SQL se consulta en `res_partner`.
- **Herencia de plantillas QWeb del login**: la tarjeta y el formulario usan `t-attf-class`,
  así que `hasclass('...')` en el xpath **no funciona**. Anclar en elementos con `class`
  estático: `//div[hasclass('card-body')]/parent::div`, `//div[hasclass('border-bottom')]/img`, `//form`.
- La herencia de vistas **no permite usar `alt`** (ni la mayoría de atributos) como selector
  xpath. Solo `id`, `name`, `class`/`hasclass`, `t-name`…
- Fondo del login a pantalla completa: reemplazar `<t t-set="body_classname">` para añadir
  una clase propia al `<body>` y estilarla (el compilador SCSS de Odoo ignora `:has()`).
- El favicon del login se controla con la variable de plantilla `x_icon`.
- El título de la pestaña en backend: servicio que hace `title.setParts({ zopenerp: "..." })`.
- Imagen de empresa (`res.company.logo`): hay que dar PNG (no SVG). Se carga desde
  `models/res_company.py` con `odoo.tools.file_path(...)` + `base64.b64encode` (el helper
  antiguo `get_module_resource` ya **no existe** en Odoo 18).
- En Windows, `gevent` no se instala (excluido en requirements) → Odoo corre en modo
  *threaded*. Correcto para local.
- **No usar `2>&1`** al lanzar Odoo desde PowerShell 5.1 (ver §5).
- El servidor se lanza **detached** con `Start-Process` (no queda "vigilado").

---

## 9. Pendiente (por orden sugerido)

### En desarrollo (PC actual)
0. ~~Añadir `-d mi_base_stock` a `start-odoo.ps1`~~ ✅ hecho (§5).
1. **Fijar la localización fiscal española** en la empresa (Ajustes → Contabilidad →
   paquete "España - PGCE PYMEs") y configurar impuestos por defecto.
2. **Crear el almacén** y ubicaciones básicas de la floristería.
3. **Configurar el Punto de Venta**: método de pago efectivo/tarjeta, formato de ticket
   80 mm, vincular al almacén para el descuento de stock, decidir si el stock baja al
   pagar o al cerrar caja.
4. ~~Personalizar `mi_gestor_stock` con los 4 flujos del negocio~~ ✅ hecho (§6bis,
   2026-09-03): campos/vistas de producto con stock mínimo y alertas, pantalla de
   recepción con escaneo, informes de ventas y más vendidos. **Pendiente dentro de
   esto**: informe de etiquetas de producto en formato 80 mm (no se ha abordado).
5. ~~Poner el logo definitivo~~ ✅ hecho (§7).
6. **Datos de prueba con el lector físico**: la lógica de Recepción (escaneo, alta
   rápida, dos escaneos del mismo producto, albarán generado) está verificada por
   shell/HTTP (§6bis), pero falta probarla con el lector Honeywell real y a ojo en el
   navegador — colores, que el widget `barcode_handler` engancha con el hardware real,
   comportamiento del contador de alertas (reloj de actividades) en uso normal.
7. ~~Instalar módulos OCA desde `custom_addons\stock-logistics-barcode`~~ — esa carpeta
   ya **no existe** en este repo (ver §10); si hace falta en el futuro, hay que
   volver a clonarla.
8. (Opcional) Revisar si conviene un grupo de seguridad propio para la app en vez de
   `base.group_user` en `security/ir.model.access.csv` (por ahora cualquier usuario
   interno puede usar Recepción).

### En producción (PC i5) — más adelante
9. Replicar el entorno o migrar: instalar PostgreSQL + Python + clonar repos, o copiar la
   carpeta `EntreRamblasGestorStock\` entera + restaurar el dump de la BD.
10. **Mover la BD/filestore al disco que indique el cliente** (`data_dir` y `db` en
    `odoo.conf`, o `data_directory` de PostgreSQL).
11. ~~Instalar drivers de la impresora Approx, configurar Chrome *kiosk-printing*~~ —
    ya no hace falta: el ticket sale en ESC/POS desde el servidor (§11.2). Queda
    **probar ticket + cajón con el hardware real** (Configuración → Dispositivos
    tiene los dos botones de prueba). IoT Box descartada.
12. Emparejar el lector Honeywell (modo HID) y probar el escaneo en TPV y en recepción.
13. ~~Copias de seguridad automáticas~~ ✅ hecho (§11.4): las hace el propio módulo
    cada 6 h en un `.zip` con base de datos + filestore. **Pendiente en producción**:
    apuntar la carpeta al SSD Corsair desde Configuración → Dispositivos.
14. Arrancar Odoo como **servicio de Windows** para que se inicie con el equipo (NSSM o similar).
15. Revisar seguridad: `admin_passwd` robusta, `list_db = False` (ya está), quizá cifrado del disco.

---

## 10. Estado del código

- Repo git: **inicializado** en `EntreRamblasGestorStock\` (rama `main`, commit inicial
  `7910146`). ⚠️ El commit inicial incluyó `venv\`, `odoo\` y `.odoo_data\` (miles de
  ficheros). Recomendable añadir un `.gitignore` con `venv/`, `odoo/`, `.odoo_data/`,
  `*.log`, `*.dump` y sacarlos del control de versiones (`git rm -r --cached`).
- Odoo 18 clonado con `--depth 1` (sin historial). Para actualizar Odoo: `git -C odoo pull`
  (necesita internet).
- `odoo.conf` — `addons_path = odoo/addons, custom_addons` (recoge `mi_gestor_stock`
  porque `custom_addons` es la carpeta padre). No incluye `stock-logistics-barcode`:
  esa carpeta OCA no está presente en este repo (solo existía en la carpeta antigua
  `C:\Users\Usuario\Desktop\EntreRamblas\`, sin instalar).

---

## 11. Hardware de la tienda y persistencia en disco

Todo lo de esta sección se configura en **Gestor de Stock → Configuración →
Dispositivos** (menú visible solo para el administrador). Es un **registro
único** del modelo `mgs.config`, creado por `data/mgs_hardware_data.xml` con
`noupdate="1"`: lo que se ajuste en la tienda **no se pisa** en el siguiente
`-u mi_gestor_stock`.

### 11.1 Los dos lectores (Honeywell XP 1472g y PcCom)

Los dos son **HID**: cada lectura se escribe como si se tecleara y termina en
Enter. No hay driver, ni puerto, ni configuración en Windows — y por eso los dos
funcionan exactamente igual para el programa. Quien los recoge es el motor
`barcodes` de Odoo, que ya estaba instalado.

Dónde funciona el escaneo:

| Pantalla | Qué hace al escanear |
|---|---|
| **Recepción** | Suma unidades (modo existente) o asigna el código (modo nuevo). Hereda `barcodes.barcode_events_mixin`: engancha en cualquier punto de la pantalla, sin poner el foco en un campo |
| **Panel de Stock** | Abre la ficha del producto — consultar precio/existencias con la pistola (`onBarcodeScanned` en `stock_dashboard.js` → `product.template.mgs_find_by_barcode`) |
| **TPV** (`/pos/ui`) | Añade el producto a la venta (nativo de Odoo) |
| **Cualquier campo de texto** | Se escribe el código, como con un teclado |

Ajustes disponibles, todos opcionales:

- **Retardo máximo entre teclas** (150 ms por defecto). Si el lector Bluetooth
  pierde caracteres, súbelo a 250. Se guarda en el parámetro de sistema
  `barcode.max_time_between_keys_in_ms`, que Odoo sirve en la sesión del
  navegador (`odoo/addons/barcodes/models/ir_http.py`) → hace falta **Ctrl+F5**
  para que el cambio llegue al navegador.
- **Prefijo / sufijo a descartar**: solo si alguien programa el lector para
  añadir caracteres. El Enter final **no** se pone aquí (es la marca de fin de
  lectura y Odoo ya lo consume).
- **Prefijo de códigos internos** (`28` por defecto).

> ⚠️ **No uses 22, 23, 041 ni 042** como prefijo de códigos internos: la
> nomenclatura por defecto del TPV los reserva para descuentos, precio
> incrustado, cajero y cliente
> (`odoo/addons/point_of_sale/data/default_barcode_patterns.xml`). Un código
> propio que empiece por ahí lo interpretaría mal la caja.

### 11.2 Impresora Approx appPOS80AM (ESC/POS)

El servidor le manda **ESC/POS** en crudo. El generador de comandos está en
`models/mgs_escpos.py` (unas 250 líneas, **sin dependencias externas**: nada de
`python-escpos`). Tres formas de conectarla:

| Modo | Cuándo usarlo | Requisitos |
|---|---|---|
| **Red (TCP 9100)** — recomendado | La impresora en la LAN por su boca Ethernet | IP **fija** (reserva en el router o su utilidad de configuración) |
| **Impresora de Windows (RAW)** | Conectada por USB al PC de caja | Driver instalado + `pip install pywin32` en el venv |
| **Ruta o puerto** | `\\EQUIPO\POS80`, `COM1`, o **un fichero para probar sin hardware** | — |

Qué imprime:

- **Ticket del TPV**, automáticamente al cobrar: cabecera con nombre/NIF de la
  tienda, líneas con cantidad y precio, total, **desglose de IVA** (ticket
  simplificado español), pagos, cambio, pie y el número de ticket en código de
  barras. Sale directo por la térmica, **sin diálogo del navegador**.
- **Etiquetas de producto**: nombre, PVP y el código de barras. Lo dibuja la
  propia impresora (`GS k`, EAN-13 si el código es válido y CODE128 si no), así
  que no hace falta ni PDF ni wkhtmltopdf.
- **Ticket de prueba** con acentos, euro y un código de barras de muestra: si ese
  código se lee con la pistola, el circuito completo funciona.

Si en el ticket salen símbolos raros, cambia el **juego de caracteres** (cp858
por defecto, que es cp850 + euro). La opción **«Sin acentos»** siempre funciona:
transliterá los acentos y escribe `EUR` en lugar de `€`.

### 11.3 Cajón Approx CASH01

No recibe datos: cuelga del **RJ11 de la impresora** y se abre con un pulso de
12 V. Abrir el cajón es, técnicamente, mandarle 5 bytes a la impresora
(`ESC p m t1 t2`).

- **Al cobrar en efectivo o dar cambio**, el TPV ya llama a `openCashbox()`
  (`payment_screen.js` → `_finalizeValidation`). `static/src/js/pos_hardware.js`
  parchea esa llamada para que, además del camino de la IoT Box (que aquí no
  existe y no hace nada), se dispare nuestro pulso.
- **A mano**, con el botón «Abrir el cajón» de la pantalla de Configuración.
- Si la impresora está apagada o sin red, **no hay pulso**: el cajón se abre con
  la llave. Es una limitación física del montaje, no del programa.

Ajustables: patilla del RJ11 (2 por defecto, algunos cajones usan la 5) y
duración del pulso (100 ms; súbelo si el solenoide no llega a saltar).

### 11.4 La persistencia: un archivo en el disco con todo dentro

**Odoo no puede funcionar sobre un fichero suelto** (necesita PostgreSQL: usa
vistas, secuencias y tipos propios). Lo que sí se hace, y es lo que se pidió, es
**volcar automáticamente el estado completo a un archivo del disco**:

```
.odoo_data\backups\
  mi_base_stock-ultima.zip          <- SIEMPRE el estado más reciente (nombre fijo)
  mi_base_stock-20260905-1130.zip   <- histórico con fecha (14 copias por defecto)
```

Dentro de cada `.zip`:

| Contenido | Qué es |
|---|---|
| `dump.sql` | La base de datos entera: productos, stock, ventas, clientes, usuarios y la propia configuración de los dispositivos |
| `filestore/` | Imágenes y adjuntos |
| `manifest.json` | Versión de Odoo y módulos instalados |

Es el **formato de copia nativo de Odoo**, así que ese archivo se puede restaurar
en este equipo o en cualquier otro Odoo 18.

- **Cada cuánto**: un `ir.cron` se despierta cada hora y el modelo decide si toca
  copia comparando con la última (6 h por defecto). Mirar la última copia en vez
  de fiarlo al intervalo del cron hace que, si la tienda pasa la noche apagada,
  al encender se haga **la copia que tocaba, no cuatro seguidas**.
- **Dónde**: por defecto `<data_dir>\backups`. Cambiando la carpeta en la
  pantalla de Configuración se escriben directamente en el **SSD Corsair**
  (`E:\CopiasEntreRamblas`, por ejemplo).
- **Historial**: menú Configuración → Copias de seguridad, con el botón
  «Hacer una copia ahora». Las copias fallidas también quedan registradas, con
  el motivo.

**Restaurar** (con el servidor **parado**):

```powershell
.\restore-backup.ps1                       # la copia más reciente
.\restore-backup.ps1 -Lista                # ver qué copias hay
.\restore-backup.ps1 -Archivo E:\copias\mi_base_stock-20260905-1130.zip
```

Pide confirmación escribiendo `SI`, borra la base actual y restaura la copia
(base de datos + filestore). Por debajo llama a `tools\restore_backup.py`.

> ⚠️ **Gotcha (dos veces el mismo)**: `dump_db`, `restore_db` y `exp_drop` de
> `odoo/service/db.py` llevan el decorador `check_db_management_enabled`, que
> lanza `AccessDenied` cuando **`list_db = False`** — y así está `odoo.conf` a
> propósito, para ocultar el gestor de bases de datos del navegador. Por eso:
> **(a)** `models/mgs_backup.py` **no** llama a `dump_db`, sino que rehace el
> volcado (pg_dump + filestore + manifest + zip), que es exactamente lo que hace
> Odoo por dentro; **(b)** `tools/restore_backup.py` levanta `list_db` en
> memoria antes de restaurar, algo legítimo en un script local con el servidor
> parado.
>
> ⚠️ Y otro: en Windows **`pg_dump` no está en el PATH**, así que la copia
> fallaría en silencio. `odoo.conf` fija ahora `pg_path = C:\Program
> Files\PostgreSQL\16\bin` (si se instala otra versión, hay que cambiar el
> número); además `_mgs_pg_tool()` lo busca por su cuenta en
> `C:\Program Files\PostgreSQL\*\bin` como red de seguridad.

### 11.5 Puesta en marcha en el PC de producción

1. Emparejar el **Honeywell** en modo HID Bluetooth (código del manual) y
   enchufar el dongle del **PcCom**. Probar en cualquier campo de texto: el
   código debe escribirse y saltar de línea solo.
2. Conectar la **impresora** (red o USB) y el **cajón** al RJ11 de la impresora.
3. Configuración → Dispositivos → elegir la conexión y pulsar **«Imprimir ticket
   de prueba»** y **«Abrir el cajón»**.
4. Escanear el código de barras del propio ticket de prueba: cierra el círculo
   lector ↔ impresora.
5. Poner la **carpeta de copias** en el SSD externo y pulsar «Hacer una copia
   ahora» para dejar la primera hecha.

### 11.6 Archivos que intervienen

| Archivo | Qué hace |
|---|---|
| `models/mgs_escpos.py` | Generador de comandos ESC/POS y los tres transportes (red / Windows RAW / ruta) |
| `models/mgs_config.py` | Modelo `mgs.config`: ajustes, tickets, etiquetas, cajón, códigos internos |
| `models/mgs_backup.py` | Modelo `mgs.backup`: volcado a `.zip`, archivo permanente, retención y cron |
| `views/mgs_config_views.xml` | Pantalla de configuración (3 pestañas) y lista de copias |
| `data/mgs_hardware_data.xml` | Registro único (`noupdate`), secuencia de códigos internos y cron de copias |
| `static/src/js/pos_hardware.js` | Puente TPV ↔ hardware: ticket ESC/POS y apertura de cajón, con vuelta atrás segura |
| `tools/restore_backup.py` + `restore-backup.ps1` | Restauración de una copia |
