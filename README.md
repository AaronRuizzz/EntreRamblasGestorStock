# Entre Ramblas · Clavel & Azahar — Gestor de stock + TPV (Odoo 18)

> Documento de traspaso entre sesiones. Recoge todo lo hecho hasta **2026-09-02**.
> Léelo entero antes de continuar.

---

## 0. Cambios recientes (2026-09-03, tarde)

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

## 0bis. Cambios recientes (2026-09-03, mañana)

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

## 0ter. Cambios anteriores (2026-09-02)

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
- **Ticket**: sale como PDF; con Chrome en *kiosk-printing* se imprime sin diálogo.
- **Cajón**: solo se abre de forma fiable con impresora Epson *ePOS* o *IoT Box*. La Approx es ESC/POS genérica. Pendiente de probar el auto-kick del firmware.
- Odoo instaló `pos_epson_printer` automáticamente pero **solo sirve para impresoras Epson**.

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

## 4. Credenciales y accesos

| Qué | Valor |
|---|---|
| URL | http://localhost:8069 |
| Base de datos | `mi_base_stock` |
| **Usuario administrador** | `entreramblasclavelyazahar@gmail.com` |
| **Contraseña** | `gestionDeStockNani2026` |

> Estas credenciales las **fija el módulo** (`_mgs_setup_spanish` en
> `res_company.py`) al crear la BD desde cero. Si el cliente cambia la contraseña
> en producción, un `-u` posterior **no** la vuelve a pisar (solo actúa mientras
> el login siga siendo `admin`).

| Contraseña maestra (crear/borrar BD) | `admin` (en `odoo.conf`, `admin_passwd`) — el gestor de BD está **desactivado** por `list_db = False` |
| PostgreSQL superusuario | `postgres` / `postgres` |
| PostgreSQL rol Odoo | `odoo` / `odoo` |

> El login de Odoo es **100% local**: valida contra la tabla `res.users` de PostgreSQL
> (hash pbkdf2). No hay ninguna llamada a internet. El navegador puede guardar la
> contraseña localmente (autocompletar), sin internet.

---

## 5. Cómo arrancar / trabajar

### La base de datos SALE DEL REPOSITORIO (no se sube a git)

La BD `mi_base_stock` **no se versiona**. Es un producto derivado del módulo
`mi_gestor_stock`: toda la personalización (marca, idioma español, estilos,
vistas, ajustes, apps instaladas) vive como código/datos dentro del módulo.
Cualquier equipo la reconstruye idéntica con **`bootstrap.ps1`**.

```powershell
cd ...\EntreRamblasGestorStock\EntreRamblas

# --- PRIMERA VEZ en un equipo (crea venv, deps y la BD desde cero) ---
.\bootstrap.ps1

# --- Arrancar el servidor ---
.\start-odoo.ps1

# --- Recrear la BD desde cero (borra la actual) ---
.\bootstrap.ps1 -Reset
```

### Flujo de trabajo entre compañeros (push / pull)

| Situación | Qué hacer |
|---|---|
| Cambié **SCSS / JS / QWeb** y hago push | El compañero: `git pull` → Ctrl+F5 en el navegador. Nada más. |
| Cambié **vistas XML / modelos Python / datos** (`data/*.xml`) y hago push | El compañero: `git pull` → `.\start-odoo.ps1 -Update mi_gestor_stock` |
| Añadí una **app nueva** (la puse en `depends` del `__manifest__.py`) | El compañero: `git pull` → `.\start-odoo.ps1 -Update mi_gestor_stock` (instala la nueva dependencia) |
| La BD local quedó inconsistente | `.\bootstrap.ps1 -Reset` (se pierde solo lo tecleado a mano, no la config del módulo) |

> ⚠️ Lo que se teclea **a mano** en Odoo (productos reales, configuración del
> almacén, métodos de pago del TPV…) **NO viaja por git**. Si hay que compartirlo,
> se convierte en datos del módulo (`data/*.xml` o `.csv`) o se pasa un dump de la
> BD aparte. La marca, el idioma y los estilos SÍ viajan porque son del módulo.

```powershell
# Instalar un módulo suelto sin tocar el manifest (ej. uno de la OCA):
.\start-odoo.ps1 -Init web_ir_actions_client_scan
```

- El servidor está en **modo desarrollo** (`dev_mode = reload,qweb,xml` en `odoo.conf`).
- **SCSS / JS / QWeb**: se recargan al refrescar el navegador (Ctrl+F5). No hace falta reiniciar.
- **Vistas XML nuevas / modelos Python / datos**: requieren `-Update mi_gestor_stock`.
- Modo desarrollador de Odoo: Ajustes → Activar modo desarrollador.

### ⚠️ Gotcha importante: instalar/actualizar módulos por línea de comandos

Al usar `-i` (instalar) o `-u` (actualizar) con `--stop-after-init` hay que pasar
**`-d mi_base_stock` explícito**. El `dbfilter` de `odoo.conf` solo afecta al enrutado
HTTP, no al destino de los comandos CLI: sin `-d`, Odoo arranca, detecta wkhtmltopdf y
se apaga ("Initiating shutdown") **sin tocar la base de datos**.

```powershell
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d mi_base_stock -i <modulo> --stop-after-init
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d mi_base_stock -u mi_gestor_stock --stop-after-init
```

> ✅ **Ya resuelto**: `start-odoo.ps1` añade `-d mi_base_stock` automáticamente en
> `-Init` / `-Update` (parámetro `-Database` para cambiarlo), lanza el paso con
> `--stop-after-init` y luego arranca el servidor normal. `bootstrap.ps1` hace lo
> mismo al crear la BD.

Además, al lanzar desde PowerShell 5.1 **no uses `2>&1`** con Odoo: envuelve cada línea
de log como error y puede abortar el arranque. Redirige a fichero con
`Start-Process ... -RedirectStandardError`.

### Comandos útiles

```powershell
# Consola Python de Odoo (para tocar datos directamente)
.\venv\Scripts\python.exe .\odoo\odoo-bin shell -c odoo.conf -d mi_base_stock --no-http

# Copia de seguridad manual de la BD
$env:PGPASSWORD='odoo'
& "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -U odoo -h localhost -Fc mi_base_stock -f backup_mi_base_stock.dump
# + copiar la carpeta .odoo_data\ (filestore: imágenes y adjuntos)
```

---

## 6. Estructura del módulo `custom_addons\mi_gestor_stock\`

```
__manifest__.py
__init__.py                    # importa models/
models/
  __init__.py
  res_company.py                # aplica marca (nombre+logo) e idioma español
  product_template.py           # defaults de floristería + campos y lógica de alertas de stock
  mgs_reception.py               # wizard de Recepción (pantalla de escaneo)
data/
  branding.xml                  # marca/idioma + desactiva registro público + fix salida TPV
  ux_defaults.xml               # pantalla de inicio, home action, oculta apps que no se usan
  cron_alerts.xml               # ir.cron diario: avisos de stock bajo mínimo
security/
  ir.model.access.csv           # ACL de mgs.reception y mgs.reception.line
views/
  mgs_menus.xml                  # ÚNICA app visible: Recepción · Stock · Compra · Informes
  mgs_reception_views.xml       # formulario + acción de la pantalla de Recepción
  product_views.xml             # ficha de producto simplificada + lista/buscador de Stock
  pos_report_views.xml          # acciones de Informes (reutilizan report.pos.order nativo)
  login_templates.xml           # personalización de la pantalla de login
static/src/
  img/
    logo-emblema.png / logo.png / favicon.png   # emblema a color, USADOS (login/empresa/favicon)
  scss/
    login.scss                  # estilos de la pantalla de login (paleta azul pizarra)
    backend.scss                # estilos del backend, con ámbito acotado (ver §6bis)
    primary_variables.scss      # color de marca de Odoo ($o-community-color, etc.)
  js/
    title.js                    # título de pestaña + limpieza mínima del systray
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
>   `entreramblasclavelyazahar@gmail.com` / `gestionDeStockNani2026`. En cuanto el
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
11. Instalar drivers de la impresora Approx, configurar Chrome *kiosk-printing*, probar
    **ticket + cajón** con el hardware real. Decidir si hace falta IoT Box para el cajón.
12. Emparejar el lector Honeywell (modo HID) y probar el escaneo en TPV y en recepción.
13. **Copias de seguridad automáticas** al SSD Corsair (tarea programada de Windows con
    `pg_dump` + copia del filestore).
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
