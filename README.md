# Entre Ramblas · Clavel & Azahar — Gestor de stock + TPV (Odoo 18)

> Documento de traspaso entre sesiones. Recoge todo lo hecho hasta **2026-09-02**.
> Léelo entero antes de continuar.

---

## 0. Cambios recientes (2026-09-02)

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
| Contraseña maestra (crear/borrar BD) | `admin` (en `odoo.conf`, `admin_passwd`) — el gestor de BD está **desactivado** por `list_db = False` |
| PostgreSQL superusuario | `postgres` / `postgres` |
| PostgreSQL rol Odoo | `odoo` / `odoo` |

> El login de Odoo es **100% local**: valida contra la tabla `res.users` de PostgreSQL
> (hash pbkdf2). No hay ninguna llamada a internet. El navegador puede guardar la
> contraseña localmente (autocompletar), sin internet.

---

## 5. Cómo arrancar / trabajar

```powershell
cd C:\Users\Usuario\Desktop\EntreRamblasGestorStock\EntreRamblas

# Arrancar el servidor
.\start-odoo.ps1

# Tras editar XML de vistas o Python del módulo -> recargar cambios:
.\start-odoo.ps1 -Update mi_gestor_stock

# Instalar un módulo nuevo (ej. uno de la OCA):
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

> `start-odoo.ps1 -Init` / `-Update` **también deberían llevar `-d mi_base_stock`**.
> Pendiente de añadirlo al script (§9, punto 0).

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
__init__.py                # importa models/
models/
  __init__.py
  res_company.py           # aplica marca (nombre+logo) e idioma español  (NUEVO)
data/
  branding.xml             # llama a los métodos de marca/idioma + desactiva registro público
  ux_defaults.xml          # pantalla de inicio = Inventario; oculta la app Discuss
views/
  stock_picking_views.xml  # herencia del formulario de albaranes (ejemplo inicial)
  login_templates.xml      # personalización de la pantalla de login
static/src/
  img/
    logo-crest.svg / logo.svg  # emblema original (clavel + azahar), vectorial — FUENTE del logo
    login-logo.png        # logo de la pantalla de login  — rasterizado del SVG
    logo.png              # logo de la empresa (backend, informes PDF) — rasterizado del SVG
    favicon.png           # favicon del login (vía x_icon en la plantilla)
    login-logo.svg / favicon.svg  # placeholders antiguos (ya no se usan)
  scss/
    custom_style.scss     # estilos backend (ejemplo inicial: .custom-inventory-card)
    login.scss            # estilos de la pantalla de login (paleta calmada)
    backend.scss          # retoque de color del backend (navbar verde, botones verdes)
  js/
    title.js              # pone "Gestión de stock" como título de la pestaña
```

### `__manifest__.py` — puntos clave
- `depends`: `["stock", "barcodes", "web", "point_of_sale"]`
- `data`: `branding.xml`, `ux_defaults.xml`, `stock_picking_views.xml`, `login_templates.xml`
- **Python**: `models/res_company.py` hereda `res.company` y añade `_mgs_apply_branding()`
  (nombre + logo) y `_mgs_setup_spanish()` (idioma). `branding.xml` los invoca con
  `<function ... eval="[[]]"/>` en cada `-u` — un `<record>` sobre `base.main_company`
  no sirve (es `noupdate`).
- `web.assets_backend`: `custom_style.scss`, `backend.scss`, `title.js`
- `web.assets_frontend`: `login.scss`  ← **el login usa el bundle FRONTEND, no el backend**

---

## 7. Personalización de la marca — hecho

| Elemento | Estado |
|---|---|
| Logo en el login | ✅ **Emblema real** (clavel + azahar), `login-logo.png` rasterizado del SVG |
| Logo de la empresa (backend + informes PDF) | ✅ Mismo emblema, `logo.png` → `res.company.logo` |
| Fondo del login | ✅ Degradado calmado crema→verde salvia |
| Botón "Iniciar sesión" | ✅ Verde bosque `#2f4a37` |
| "Powered by Odoo" | ✅ Eliminado (`disable_footer` = True) |
| "Manage Databases" | ✅ Eliminado (`disable_footer` + `list_db = False`) |
| Registro público de cuentas | ✅ Eliminado (`auth_signup.allow_uninvited = False`) |
| Pie propio del login | ✅ "Entre Ramblas · Clavel & Azahar" |
| Título de la pestaña | ✅ "Gestión de stock" (login vía `<t t-set="title">`, backend vía `title.js`) |
| Favicon del login | ✅ El emblema (`favicon.png` vía `x_icon` en la plantilla) |
| Favicon del backend | ⚠️ Por defecto de Odoo. `res.company.favicon` **no existe** en Community sin el módulo `website` |
| Nombre de la empresa | ✅ "Entre Ramblas · Clavel & Azahar" (`_mgs_apply_branding` en `res_company.py`) |
| "My Company" / "Administrator" | ✅ Renombrados a la empresa y a "Administrador" |
| Colores del backend | ✅ Retoque suave: barra superior verde oscuro, botones verdes |

### El logo definitivo — ya está puesto
El emblema (clavel + azahar) se guardó como **SVG** en
`static\src\img\logo-crest.svg` (= `logo.svg`) y se **rasterizó a PNG** con
`wkhtmltoimage` (no hay `cairosvg`/`inkscape`), recortando márgenes y centrando
con Pillow:
- `logo.png` 560×560 — logo de empresa (backend + informes)
- `login-logo.png` 620×700 — pantalla de login
- `favicon.png` 256×256

**Para cambiarlo por otro:** sustituye el/los SVG, vuelve a rasterizar (el script
está en el historial de la sesión; en resumen `wkhtmltoimage --transparent --format png`
sobre una copia del SVG con `width`/`height` explícitos + recorte con Pillow), deja los
PNG con esos nombres y `.\start-odoo.ps1 -Update mi_gestor_stock`.
`_mgs_apply_branding()` vuelve a cargar `logo.png` en la empresa en cada `-u`.

### Ajustar colores
`static/src/scss/login.scss` (variables al principio):
```scss
$mgs-green:      #2f4a37;   // botón
$mgs-green-dark: #14351f;   // títulos
$mgs-sage:       #8a9a7b;   // foco de campos
```
`static/src/scss/backend.scss` para el resto de la app.

---

## 7bis. Pantalla de inicio tras el login (`data/ux_defaults.xml`)

**Problema resuelto (2026-09-02):** al entrar, Odoo abría el primer menú por secuencia,
que era **"Conversaciones" (Discuss)** — un chat interno que no interesa en una floristería.

**Solución en `mi_gestor_stock/data/ux_defaults.xml`:**

1. **Pantalla de inicio = "Inventario → Resumen"** (`stock.stock_picking_type_action`).
   Se fija el campo *Home Action* (`res.users.action_id`) del administrador
   (`base.user_admin`) y de la plantilla de usuarios nuevos (`base.default_user`),
   mediante un `<function model="res.users" name="write">` (un `<field>` normal **no
   funciona** con este campo).
2. **Se oculta la app Discuss** del menú principal: `mail.menu_root_discuss` con
   `active = False`. El módulo `mail` es dependencia obligatoria y no se puede
   desinstalar, pero el chat de las fichas (mensajes en productos, albaranes…) sigue
   funcionando; solo desaparece la aplicación independiente de la barra superior.

Verificado por login HTTP real: `action_id` del admin = `Inventory Overview` (id 278),
`mail.menu_root_discuss.active = False`. Reproducible: partiendo de estado limpio,
`-u mi_gestor_stock` vuelve a aplicar ambos cambios.

Para revertir: poner `active = True` en el menú y borrar el `<function>`, luego `-u`.
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
0. **Añadir `-d mi_base_stock` a `start-odoo.ps1`** en las ramas `-Init` / `-Update`.
1. **Fijar la localización fiscal española** en la empresa (Ajustes → Contabilidad →
   paquete "España - PGCE PYMEs") y configurar impuestos por defecto.
2. **Crear el almacén** y ubicaciones básicas de la floristería.
3. **Configurar el Punto de Venta**: método de pago efectivo/tarjeta, formato de ticket
   80 mm, vincular al almacén para el descuento de stock, decidir si el stock baja al
   pagar o al cerrar caja.
4. **Personalizar `mi_gestor_stock`**:
   - Campos/vistas de producto (código de barras, stock mínimo, alertas).
   - Pantalla de recepción de mercancía con escaneo.
   - Informe de etiquetas de producto en formato 80 mm.
5. ~~Poner el logo definitivo~~ ✅ hecho (§7).
6. **Datos de prueba**: productos con códigos de barras reales para validar el circuito
   completo: compra → recepción escaneada → venta en TPV → stock actualizado.
7. Instalar módulos OCA que hagan falta desde `custom_addons\stock-logistics-barcode`.
8. (Opcional) Ampliar el tema de color del backend.
   - (Opcional) Favicon del backend con la marca: requiere instalar `website` o
     sobrescribir la ruta estática del favicon.

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
- `odoo.conf` — `addons_path = odoo/addons, custom_addons, custom_addons/stock-logistics-barcode`
  (recoge `mi_gestor_stock` porque `custom_addons` es la carpeta padre).
