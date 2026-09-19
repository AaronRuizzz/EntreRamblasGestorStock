# -*- coding: utf-8 -*-
"""Configuración del hardware de la tienda y de la copia de seguridad.

Un único registro (singleton) con todo lo que hay que tocar para que el
programa hable con los cuatro aparatos de la factura:

  1. Honeywell Voyager XP 1472g  (Bluetooth -> base -> HID teclado)
  2. PcCom lector inalámbrico    (dongle 2,4 GHz -> HID teclado)
       Los dos escriben el código como si fuera texto tecleado; lo recoge el
       motor `barcodes` de Odoo. Aquí solo se ajustan el retardo entre teclas
       y los caracteres de prefijo/sufijo que añaden algunos lectores.
  3. Approx appPOS80AM-USBLAN    (impresora térmica 80 mm, ESC/POS)
  4. Approx CASH01               (cajón, pulso RJ11 disparado por la 3)

Todo lo que se manda a la impresora se construye en models/mgs_escpos.py.
"""
import base64
import io
import logging
import os
from pathlib import Path

import qrcode

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import formatLang

from . import mgs_escpos as escpos
from .mgs_permissions import require_manager, require_operator

_logger = logging.getLogger(__name__)

# Prefijos EAN-13 que YA usan las reglas de la nomenclatura por defecto del
# TPV (odoo/addons/point_of_sale/data/default_barcode_patterns.xml):
#   22{NN}       -> descuento      23.....{NNNDD} -> precio incrustado
#   041 / 042    -> cajero / cliente
# Un código interno que empiece por ahí lo interpretaría mal el TPV, así que
# el prefijo por defecto para códigos propios es 28 (rango libre de uso
# interno, 20-29, sin regla asociada).
DEFAULT_INTERNAL_PREFIX = "28"


class MgsConfig(models.Model):
    _name = "mgs.config"
    _description = "Configuración de dispositivos y copias"

    name = fields.Char(default="Configuración de la tienda", readonly=True)

    # Qué caja abre el botón «Vender» del menú. Con una sola caja configurada
    # (lo normal en esta tienda) no hace falta tocarlo: se elige sola.
    pos_config_id = fields.Many2one(
        "pos.config", string="Caja de la tienda",
        help="El botón «Vender» del menú abre directamente esta caja. Solo "
             "hay que elegirla a mano si alguna vez hay más de una configurada.")

    # ==================================================================
    # Datos de la tienda. Sin "Ajustes" (donde vivía Compañías) no hay otra
    # pantalla desde la que corregirlos.
    #
    # Se separan el NOMBRE COMERCIAL (lo que ve la clienta: emblema, pantalla
    # de inicio, título de la pestaña) de la RAZÓN SOCIAL fiscal
    # (`res.company.name`, lo que va en el ticket y en las facturas). Una
    # actualización del programa ya NO sobrescribe la razón social cuando
    # tiene un valor de verdad (ver res_company._mgs_apply_branding), así que
    # los dos son editables aquí.
    # ==================================================================
    mgs_commercial_name = fields.Char(
        "Nombre comercial", compute="_compute_company_fields",
        inverse="_inverse_commercial_name",
        help="El nombre que ve la clienta. No aparece en el ticket ni en las facturas.")
    mgs_company_name = fields.Char(
        "Razón social (fiscal)", compute="_compute_company_fields",
        inverse="_inverse_company_fields",
        help="El nombre legal de la tienda: el que sale en el ticket y en las "
             "facturas. Una actualización del programa no lo cambia.")
    mgs_company_vat = fields.Char(
        "NIF/CIF", compute="_compute_company_fields", inverse="_inverse_company_fields")
    mgs_company_street = fields.Char(
        "Dirección", compute="_compute_company_fields", inverse="_inverse_company_fields")
    mgs_company_city = fields.Char(
        "Población", compute="_compute_company_fields", inverse="_inverse_company_fields")
    mgs_company_zip = fields.Char(
        "Código postal", compute="_compute_company_fields", inverse="_inverse_company_fields")
    mgs_company_phone = fields.Char(
        "Teléfono", compute="_compute_company_fields", inverse="_inverse_company_fields")

    def _compute_company_fields(self):
        company = self.env.company
        commercial = self.env["ir.config_parameter"].sudo().get_param(
            "mgs.commercial_name") or company.name
        for config in self:
            config.mgs_commercial_name = commercial
            config.mgs_company_name = company.name
            config.mgs_company_vat = company.vat
            config.mgs_company_street = company.street
            config.mgs_company_city = company.city
            config.mgs_company_zip = company.zip
            config.mgs_company_phone = company.phone

    def _inverse_company_fields(self):
        # sudo(): escribir en res.company exige group_erp_manager, que la
        # propietaria no tiene. La ACL de mgs.config (solo group_mgs_manager
        # puede escribir aquí) ya hace de guarda: quien llega a este inverse
        # es porque ya pudo escribir en el propio mgs.config.
        for config in self:
            vals = {
                "vat": config.mgs_company_vat,
                "street": config.mgs_company_street,
                "city": config.mgs_company_city,
                "zip": config.mgs_company_zip,
                "phone": config.mgs_company_phone,
            }
            if config.mgs_company_name:
                vals["name"] = config.mgs_company_name
            self.env.company.sudo().write(vals)

    def _inverse_commercial_name(self):
        for config in self:
            self.env["ir.config_parameter"].sudo().set_param(
                "mgs.commercial_name", (config.mgs_commercial_name or "").strip())

    # ==================================================================
    # 1 y 2. Lectores de códigos de barras (HID: se comportan como teclado)
    # ==================================================================
    scan_max_delay_ms = fields.Integer(
        "Retardo máximo entre teclas (ms)", default=150,
        help="Tiempo máximo entre dos caracteres para que el programa considere "
             "que es un escaneo y no un tecleo humano. El lector Bluetooth puede "
             "necesitar subirlo a 250 si se pierden lecturas.")
    scan_strip_prefix = fields.Char(
        "Prefijo a descartar",
        help="Algunos lectores se programan para añadir caracteres delante de "
             "cada lectura. Si es el caso, escríbelos aquí y se ignorarán.")
    scan_strip_suffix = fields.Char(
        "Sufijo a descartar",
        help="Igual que el prefijo, pero al final. El Enter final NO se pone "
             "aquí: es la marca de fin de lectura y el programa ya lo consume.")
    internal_prefix = fields.Char(
        "Prefijo de códigos internos", default=DEFAULT_INTERNAL_PREFIX,
        help="Para los productos que llegan sin código de barras (flores a "
             "granel, envoltorios) se genera uno propio con este prefijo. "
             "Evita 22, 23, 041 y 042: el TPV los reserva para descuentos, "
             "precios, cajeros y clientes.")

    # ==================================================================
    # 3. Impresora térmica de tickets
    # ==================================================================
    printer_mode = fields.Selection([
        ("network", "Red (Ethernet/LAN, TCP 9100)"),
        ("windows", "Impresora de Windows (USB)"),
        ("path", "Ruta o puerto (avanzado)"),
        ("disabled", "Sin impresora"),
    ], string="Conexión de la impresora", default="network", required=True,
        help="La appPOS80AM admite USB y LAN a la vez. Por red es lo más "
             "estable y no necesita drivers ni paquetes extra.")
    printer_host = fields.Char("Dirección IP", help="Ej. 192.168.1.50")
    printer_port = fields.Integer("Puerto", default=9100)
    printer_name = fields.Char(
        "Nombre en Windows",
        help="El nombre exacto que aparece en Dispositivos e impresoras "
             "(ej. POS-80). Requiere el paquete pywin32 en el entorno.")
    printer_path = fields.Char(
        "Ruta o puerto",
        help="Recurso compartido (\\\\EQUIPO\\POS80), puerto serie (COM1) o un "
             "fichero para hacer pruebas sin la impresora conectada.")
    printer_timeout = fields.Integer("Espera máxima (s)", default=5)
    paper_width = fields.Selection([
        ("80", "80 mm (48 caracteres)"),
        ("58", "58 mm (32 caracteres)"),
    ], string="Ancho del papel", default="80", required=True)
    printer_codepage = fields.Selection([
        ("cp858", "cp858 — europeo occidental con símbolo del euro"),
        ("cp850", "cp850 — europeo occidental"),
        ("cp1252", "cp1252 — Windows"),
        ("cp437", "cp437 — estándar antiguo"),
        ("ascii", "Sin acentos (a prueba de bombas)"),
    ], string="Juego de caracteres", default="cp858", required=True,
        help="Si en el ticket salen símbolos raros en lugar de acentos o del "
             "euro, prueba otro juego. «Sin acentos» siempre funciona.")
    receipt_footer = fields.Char(
        "Pie del ticket", default="¡Gracias por su compra!")
    google_review_url = fields.Char(
        "Enlace a las reseñas de Google",
        help="El enlace «Valorar» de la ficha de Google del negocio "
             "(g.page/r/.../review). Si se rellena, tanto el ticket que sale "
             "por la impresora térmica como el PDF de reimpresión llevan un "
             "código QR invitando a dejar una reseña. Vacío: no sale ese QR "
             "en ninguno de los dos.")
    label_copies = fields.Integer("Etiquetas por producto", default=1)

    pos_autoprint = fields.Boolean(
        "Imprimir el ticket del TPV automáticamente", default=True,
        help="Al cobrar, el ticket sale directo por la impresora térmica, sin "
             "diálogo de impresión del navegador. Si se desactiva, el TPV "
             "vuelve a imprimir el PDF por el navegador.")

    # ==================================================================
    # 4. Cajón portamonedas
    # ==================================================================
    drawer_enabled = fields.Boolean("Cajón conectado a la impresora", default=True)
    drawer_pin = fields.Selection([
        ("0", "Patilla 2 (lo habitual)"),
        ("1", "Patilla 5"),
    ], string="Patilla del RJ11", default="0", required=True)
    drawer_pulse_ms = fields.Integer(
        "Duración del pulso (ms)", default=100,
        help="Entre 100 y 200 ms. Si el cajón no llega a abrir, súbelo.")
    drawer_on_sale = fields.Boolean(
        "Abrir el cajón al cobrar en efectivo", default=True)

    # ==================================================================
    # Copia de seguridad (ver models/mgs_backup.py)
    # ==================================================================
    backup_enabled = fields.Boolean("Copia de seguridad automática", default=True)
    backup_dir = fields.Char(
        "Carpeta local de las copias",
        default=lambda self: self.env["mgs.backup"]._mgs_default_dir(),
        help="Ruta local de Windows donde se guardan las copias, por ejemplo "
             "C:\\CopiasEntreRamblas. No es una dirección IP.")
    backup_every_hours = fields.Integer("Hacer una copia cada (horas)", default=6)
    backup_retention_days = fields.Integer("Días de conservación", default=30)
    backup_ssd_dir = fields.Char("Carpeta externa (SSD o USB)",
        help="Ruta de una carpeta ya creada en el disco externo, por ejemplo "
             "E:\\CopiasEntreRamblas. No se introduce una dirección IP; la copia "
             "local se mantiene siempre.")
    backup_last_date = fields.Datetime("Última copia", readonly=True)
    backup_last_path = fields.Char("Archivo de la última copia", readonly=True)
    backup_latest_name = fields.Char(
        "Archivo permanente", compute="_compute_backup_latest_name",
        help="Este archivo se reescribe en cada copia y siempre contiene el "
             "estado completo del programa: base de datos, imágenes y "
             "adjuntos. Es el que hay que llevarse al disco externo.")

    # ------------------------------------------------------------------
    # Acceso al registro único
    # ------------------------------------------------------------------
    @api.model
    def _mgs_get(self):
        """Devuelve el registro de configuración, creándolo si hiciera falta.

        Va en sudo: cualquier usuario de tienda tiene que poder imprimir un
        ticket o abrir el cajón sin permisos de administración.
        """
        config = self.env.ref("mi_gestor_stock.mgs_config_default", raise_if_not_found=False)
        if not config:
            config = self.sudo().search([], limit=1)
        if not config:
            config = self.sudo().create({})
        return config.sudo()

    @api.model
    def action_mgs_open(self):
        """Abre la pantalla de configuración sobre el registro único."""
        require_manager(self.env)
        config = self._mgs_get()
        return {
            "type": "ir.actions.act_window",
            "name": _("Dispositivos y copias de seguridad"),
            "res_model": "mgs.config",
            "res_id": config.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def action_mgs_open_pos(self):
        """«Vender» del menú: entra directo al TPV, sin pasar por el kanban
        nativo de cajas (pensado para varios puntos de venta; aquí hay uno).

        `pos.config.open_ui()` ya hace todo lo que hace falta: crea la sesión
        si no hay una abierta, valida que la caja esté lista para vender, y
        devuelve la URL de /pos/ui. No se reimplementa nada de eso aquí."""
        pos_config = self._mgs_get().pos_config_id
        if not pos_config:
            candidates = self.env["pos.config"].search([])
            if len(candidates) == 1:
                pos_config = candidates
            elif not candidates:
                raise UserError(_(
                    "No hay ninguna caja de tienda. El programa la crea solo al "
                    "instalar o actualizar; si ves esto, la instalación quedó a "
                    "medias. Vuelve a ejecutar la actualización del módulo o "
                    "avisa a quien mantiene el equipo."))
            else:
                raise UserError(_(
                    "Hay más de una caja configurada y no se ha dicho cuál es "
                    "la de la tienda. Elígela en Configuración → Dispositivos → "
                    "«Caja de la tienda»."))
        return pos_config.open_ui()

    def action_mgs_save_configuration(self):
        """Confirmación del botón visible de guardado de configuración.

        El cliente de Odoo guarda los campos pendientes antes de ejecutar un
        botón de objeto. Este método aporta la confirmación visible y mantiene
        la misma comprobación de permisos que el resto de ajustes de tienda.
        """
        self.ensure_one()
        require_manager(self.env)
        return self._mgs_notify(_("Configuración guardada."))

    def write(self, vals):
        res = super().write(vals)
        if "scan_max_delay_ms" in vals:
            # Lo lee el servicio JS de códigos de barras al cargar la sesión
            # (odoo/addons/barcodes/models/ir_http.py).
            self.env["ir.config_parameter"].sudo().set_param(
                "barcode.max_time_between_keys_in_ms",
                str(vals["scan_max_delay_ms"] or 150))
        return res

    @api.depends("backup_last_path")
    def _compute_backup_latest_name(self):
        for config in self:
            config.backup_latest_name = self.env["mgs.backup"]._mgs_latest_path(config)

    # ==================================================================
    # Lectores: normalización de la lectura
    # ==================================================================
    @api.model
    def mgs_clean_scan(self, barcode):
        """Limpia una lectura: espacios, retornos y prefijo/sufijo programados."""
        require_operator(self.env)
        code = (barcode or "").strip().strip("\r\n\t")
        if not code:
            return ""
        config = self._mgs_get()
        prefix = (config.scan_strip_prefix or "").strip()
        suffix = (config.scan_strip_suffix or "").strip()
        if prefix and code.startswith(prefix):
            code = code[len(prefix):]
        if suffix and code.endswith(suffix):
            code = code[: -len(suffix)]
        return code.strip()

    @api.model
    def mgs_next_internal_barcode(self):
        """Genera un EAN-13 interno válido y libre, para productos sin código."""
        require_manager(self.env)
        config = self._mgs_get()
        prefix = "".join(ch for ch in (config.internal_prefix or "") if ch.isdigit())
        prefix = prefix[:6] or DEFAULT_INTERNAL_PREFIX
        sequence = self.env["ir.sequence"].sudo()
        Product = self.env["product.product"].sudo()
        for _attempt in range(50):
            number = sequence.next_by_code("mgs.internal.barcode") or "1"
            body = "".join(ch for ch in number if ch.isdigit())
            code12 = (prefix + body.zfill(12 - len(prefix)))[:12]
            barcode = code12 + escpos.ean13_check_digit(code12)
            if not Product.search_count([("barcode", "=", barcode)]):
                return barcode
        raise UserError(_(
            "No se ha podido generar un código interno libre. Revisa el "
            "prefijo en Configuración → Dispositivos."))

    # ==================================================================
    # Impresora: envío
    # ==================================================================
    def _mgs_doc(self):
        """Documento ESC/POS vacío, ya con el ancho y el juego de caracteres."""
        self.ensure_one()
        width = escpos.WIDTH_BY_PAPER.get(self.paper_width or "80", 48)
        return escpos.EscposDocument(width=width, codepage=self.printer_codepage or "cp858")

    def _mgs_send(self, payload, doc_name="Ticket"):
        """Manda los bytes por el transporte configurado."""
        self.ensure_one()
        if self.printer_mode == "disabled":
            raise UserError(_(
                "No hay ninguna impresora configurada. Ve a Configuración → "
                "Dispositivos y elige cómo está conectada."))
        try:
            if self.printer_mode == "network":
                if not (self.printer_host or "").strip():
                    raise UserError(_(
                        "Falta la dirección IP de la impresora. Indícala en "
                        "Configuración → Dispositivos → Impresora y cajón "
                        "antes de imprimir."))
                escpos.send_network(payload, self.printer_host, self.printer_port,
                                    timeout=self.printer_timeout or 5)
            elif self.printer_mode == "windows":
                escpos.send_windows(payload, self.printer_name, doc_name)
            else:
                escpos.send_path(payload, self.printer_path)
        except escpos.PrinterError as err:
            raise UserError(str(err)) from err
        return True

    def _mgs_logo_bitmap(self, doc):
        """Convierte el logo de la empresa (PNG, `res.company.logo`) al mapa
        de bits que entiende la impresora (doc.raster_image), escalado al
        ancho del papel.

        Antes de esto el ticket era solo texto: no se mandaba ninguna
        imagen, así que nunca podía salir el logotipo por mucho que
        estuviera puesto en Configuración → Datos de la tienda.

        Cualquier fallo (Pillow no disponible, PNG corrupto…) se traga y
        deja el ticket sin logo en vez de romper la venta: el logo es
        decorativo, la razón social y el NIF de debajo son lo que de verdad
        tiene que salir siempre.
        """
        company = self.env.company
        if not company.logo:
            return None
        try:
            from PIL import Image, ImageEnhance
        except ImportError:
            _logger.warning("mi_gestor_stock: Pillow no disponible; el ticket sale sin logo.")
            return None
        try:
            img = Image.open(io.BytesIO(base64.b64decode(company.logo)))
            if img.mode not in ("L", "1"):
                img = img.convert("RGBA")
                # Recorta el margen transparente sobrante: el emblema real
                # (un dibujo detallado en un círculo) ocupa una fracción del
                # lienzo cuadrado del PNG, y sin recortar se imprime más
                # pequeño de lo necesario. Sin bbox (imagen totalmente
                # transparente) se deja tal cual.
                bbox = img.split()[-1].getbbox()
                if bbox:
                    img = img.crop(bbox)
                # Fondo blanco antes de aplanar: la transparencia no debe
                # volverse negro.
                background = Image.new("RGBA", img.size, (255, 255, 255, 255))
                img = Image.alpha_composite(background, img)
            # Encaja en el ancho del papel (mismo criterio que
            # WIDTH_BY_PAPER: fuente A, 12 puntos por columna) Y limita la
            # altura a un logo discreto (~27 mm a 203 ppp): con un emblema
            # cuadrado, ajustar solo al ancho ocuparía la mitad del ticket.
            # El más restrictivo de los dos manda; luego queda centrado
            # (align("center")) porque casi nunca llega a ocupar todo el
            # ancho del papel.
            max_paper_w = doc.width * 12
            max_logo_h = 220
            ratio = min(max_paper_w / img.width, max_logo_h / img.height)
            target_w = max(1, round(img.width * ratio))
            target_h = max(1, round(img.height * ratio))
            gray = img.convert("L").resize((target_w, target_h))
            # Un dibujo detallado con líneas finas y sombreados suaves (no un
            # bloque de color plano) pierde casi todo el contraste al
            # reducirlo a 160-220 puntos de alto; sin esto sale gris borroso
            # e ilegible. Con más contraste, el trazo del dibujo se conserva
            # nítido en blanco y negro puro.
            gray = ImageEnhance.Contrast(gray).enhance(1.6)
            pixels = gray.load()
            width_bytes = (target_w + 7) // 8
            data = bytearray(width_bytes * target_h)
            threshold = 160  # más oscuro que esto -> punto negro impreso
            for y in range(target_h):
                for x in range(target_w):
                    if pixels[x, y] < threshold:
                        data[y * width_bytes + x // 8] |= 0x80 >> (x % 8)
            return width_bytes, target_h, bytes(data)
        except Exception:  # noqa: BLE001 - un logo mal formado no debe tumbar la venta
            _logger.exception("mi_gestor_stock: no se pudo convertir el logo para el ticket")
            return None

    def _mgs_company_header(self, doc):
        """Cabecera del ticket: logo (si hay), nombre, dirección y NIF."""
        company = self.env.company
        bitmap = self._mgs_logo_bitmap(doc)
        if bitmap:
            width_bytes, height, data = bitmap
            doc.align("center").raster_image(width_bytes, height, data).ln()
        doc.align("center").bold(True).size(1, 2)
        doc.wrapped(company.name)
        doc.size().bold(False)
        street = ", ".join(part for part in [company.street, company.city] if part)
        if street:
            doc.wrapped(street)
        if company.vat:
            doc.ln(_("NIF: %s", company.vat))
        if company.phone:
            doc.ln(_("Tel. %s", company.phone))
        return doc.align("left").rule()

    def _mgs_amount(self, amount, currency=None):
        currency = currency or self.env.company.currency_id
        return formatLang(self.env, amount, currency_obj=currency)

    # ==================================================================
    # Botones de la pantalla de configuración
    # ==================================================================
    def action_mgs_test_print(self):
        require_manager(self.env)
        self.ensure_one()
        doc = self._mgs_doc()
        self._mgs_company_header(doc)
        doc.title(_("PRUEBA"))
        doc.ln()
        doc.columns(_("Impresora"), dict(self._fields["printer_mode"].selection).get(
            self.printer_mode, self.printer_mode))
        doc.columns(_("Papel"), _("%s mm", self.paper_width))
        doc.columns(_("Caracteres"), self.printer_codepage)
        doc.columns(_("Fecha"), fields.Datetime.context_timestamp(
            self, fields.Datetime.now()).strftime("%d/%m/%Y %H:%M"))
        doc.rule()
        doc.ln(_("Acentos y euro: ñ á é í ó ú ü ç 12,50 €"))
        doc.ln()
        doc.align("center").barcode("8412345678905").align("left")
        doc.wrapped(_("Si el código de arriba se lee con la pistola, el "
                      "circuito completo funciona."))
        if self.receipt_footer:
            doc.align("center").wrapped(self.receipt_footer).align("left")
        doc.cut()
        self._mgs_send(doc.to_bytes(), _("Prueba de impresión"))
        return self._mgs_notify(_("Ticket de prueba enviado a la impresora."))

    def action_mgs_backup_now(self):
        require_manager(self.env)
        self.ensure_one()
        backup = self.env["mgs.backup"].sudo()._mgs_run_backup(kind="manual")
        if not backup:
            return self._mgs_notify(_("Ya hay una copia en curso."), "warning")
        if backup.state != "done":
            return self._mgs_notify(backup.message or _("La copia de seguridad ha fallado."), "danger")
        if backup.replica_state == "error":
            return self._mgs_notify(backup.message, "warning")
        return self._mgs_notify(_("Copia guardada en %s", backup.path))

    def action_mgs_test_ssd(self):
        """Botón «Probar carpeta del SSD»: comprueba la carpeta de réplica
        SIN copiar nada, para no tener que esperar a la próxima copia
        automática (o forzar una manual) solo para saber si la ruta sirve.
        Usa la misma comprobación que la réplica real (mgs_backup.py,
        _mgs_check_replica_dir), así que el resultado es el mismo que daría
        la próxima copia de verdad."""
        require_manager(self.env)
        self.ensure_one()
        if not self.backup_ssd_dir:
            return self._mgs_notify(_("Escribe primero una carpeta de réplica en SSD."), "warning")
        local_dir = Path(self.env["mgs.backup"]._mgs_dir(self)).resolve()
        destination = Path(self.backup_ssd_dir).resolve()
        latest = self.backup_last_path
        required = os.path.getsize(latest) if latest and os.path.isfile(latest) else None
        try:
            self.env["mgs.backup"]._mgs_check_replica_dir(destination, local_dir, required)
        except Exception as err:  # noqa: BLE001 - mismo criterio que _mgs_replicate
            return self._mgs_notify(str(err), "danger")
        return self._mgs_notify(_("La carpeta del SSD está lista: existe, se puede "
                                  "escribir en ella y tiene sitio."))

    def _mgs_notify(self, message, kind="success"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"type": kind, "message": message, "sticky": False},
        }

    # ==================================================================
    # Etiquetas de producto
    # ==================================================================
    def _mgs_print_labels(self, products, copies=None):
        """Etiqueta de 80 mm: nombre, precio y código de barras impreso.

        La impresora dibuja las barras por su cuenta (comando GS k), así que
        no hace falta generar una imagen ni pasar por el PDF.
        """
        self.ensure_one()
        products = products.exists()
        if not products:
            raise UserError(_("No hay ningún producto que etiquetar."))
        without_code = products.filtered(lambda p: not p.barcode)
        if without_code:
            raise UserError(_(
                "Estos productos no tienen código de barras: %s\n\n"
                "Asígnaselo escaneando el del proveedor, o pulsa «Generar "
                "código interno» en su ficha.",
                ", ".join(without_code.mapped("display_name"))))

        doc = self._mgs_doc()
        copies = max(1, copies or self.label_copies or 1)
        for product in products:
            for _copy in range(copies):
                doc.align("center")
                doc.bold(True).size(1, 2)
                doc.wrapped(product.name)
                doc.size().bold(False)
                template = product.product_tmpl_id if product._name == "product.product" else product
                doc.ln(self._mgs_amount(template.list_price))
                doc.ln()
                doc.barcode(product.barcode, height=80, width=3)
                doc.align("left").cut(feed=2)
        self._mgs_send(doc.to_bytes(), _("Etiquetas"))
        return self._mgs_notify(_("%s etiqueta(s) enviada(s).", len(products) * copies))

    # ==================================================================
    # Ticket del TPV (lo llama static/src/js/pos_hardware.js)
    # ==================================================================
    @api.model
    def mgs_pos_hardware_info(self):
        """Qué hardware hay activo, más los datos del QR de reseña de
        Google / web de la tienda para el recibo EN PANTALLA del TPV
        (mismos datos que ya llevan el ticket térmico y el PDF de
        reimpresión: ver mgs_pos_receipt.py y _mgs_receipt_marketing_block
        más abajo). Antes esos dos QR solo salían al reimprimir desde el
        backend o por la térmica: el recibo que ve la clienta nada más
        cobrar — y lo que sale si ese recibo se imprime por el navegador,
        con la impresión térmica automática desactivada — se quedaba sin
        ellos. El TPV lo consulta una vez, al abrir."""
        require_operator(self.env)
        config = self._mgs_get()
        website = (self.env.company.partner_id.website or "").strip()
        if website and not website.startswith(("http://", "https://")):
            website = "https://" + website
        return {
            "escpos_receipt": bool(config.pos_autoprint and config.printer_mode != "disabled"),
            "drawer": bool(config.drawer_enabled and config.drawer_on_sale
                           and config.printer_mode != "disabled"),
            "review_qr": self._mgs_qr_png(config.google_review_url),
            "website_qr": self._mgs_qr_png(website),
            "website_url": website or False,
        }

    @api.model
    def _mgs_qr_png(self, data):
        """PNG en base64 de un QR con `data`, o False si `data` está vacío.

        Centralizado aquí porque lo usa el recibo en pantalla del TPV (este
        método), el informe en PDF (mgs_pos_receipt.py, que delega en este
        mismo método) y, en su variante ESC/POS nativa (doc.qr(), sin PNG
        de por medio), el ticket térmico (_mgs_receipt_marketing_block)."""
        data = (data or "").strip()
        if not data:
            return False
        buffer = io.BytesIO()
        qrcode.make(data, box_size=4, border=1).save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()

    def _mgs_pos_ticket(self, order):
        """Construye el ticket ESC/POS de una venta del TPV."""
        self.ensure_one()
        doc = self._mgs_doc()
        currency = order.currency_id or self.env.company.currency_id
        self._mgs_company_header(doc)

        date = fields.Datetime.context_timestamp(self, order.date_order)
        doc.columns(order.name, date.strftime("%d/%m/%Y %H:%M"))
        if order.partner_id:
            doc.wrapped(_("Cliente: %s", order.partner_id.name))
        # Una devolución es una factura rectificativa: el artículo 7 del RD
        # 1619/2012 exige que remita a la factura rectificada. Sin esta línea el
        # ticket negativo no dice de qué venta sale (ver FACTURACION.md).
        if order.refunded_order_id:
            doc.ln(_("Rectifica el ticket %s", order.refunded_order_id.name))
        doc.rule()

        # --- Líneas ---
        for line in order.lines:
            doc.wrapped(line.full_product_name or line.product_id.display_name)
            qty = ("%g" % line.qty)
            detail = _("%(qty)s x %(price)s", qty=qty,
                       price=self._mgs_amount(line.price_unit, currency))
            if line.discount:
                detail = _("%(detail)s  (-%(disc)g%%)", detail=detail, disc=line.discount)
            doc.columns(detail, self._mgs_amount(line.price_subtotal_incl, currency), indent=2)
        doc.rule()

        # --- Total ---
        doc.bold(True).size(1, 2)
        doc.columns(_("TOTAL"), self._mgs_amount(order.amount_total, currency))
        doc.size().bold(False)

        # --- Desglose de IVA (ticket simplificado español) ---
        # El artículo 7 del RD 1619/2012 pide el TIPO IMPOSITIVO, así que se
        # imprime el porcentaje ("IVA 21%") y no el nombre interno del impuesto
        # de l10n_es ("21% G"), que a un cliente no le dice nada.
        taxes = {}
        for line in order.lines:
            label = ", ".join(
                _("IVA %g%%", tax.amount) if tax.amount_type == "percent" else tax.name
                for tax in line.tax_ids) or _("Sin IVA")
            base, quota = taxes.get(label, (0.0, 0.0))
            taxes[label] = (base + line.price_subtotal,
                            quota + line.price_subtotal_incl - line.price_subtotal)
        if taxes:
            doc.rule()
            doc.ln(_("IVA incluido:"))
            for label, (base, quota) in taxes.items():
                doc.columns(_("%(label)s  base %(base)s", label=label,
                              base=self._mgs_amount(base, currency)),
                            self._mgs_amount(quota, currency), indent=2)

        # --- Pagos y cambio ---
        if order.payment_ids:
            doc.rule()
            for payment in order.payment_ids:
                # El TPV apunta el cambio como un pago en negativo sobre el
                # mismo metodo; en el ticket se lee mejor como "Cambio".
                label = payment.payment_method_id.name
                amount = payment.amount
                if amount < 0:
                    label, amount = _("Cambio"), -amount
                doc.columns(label, self._mgs_amount(amount, currency))

        doc.rule()
        doc.align("center")
        if self.receipt_footer:
            doc.wrapped(self.receipt_footer)
        doc.ln()
        self._mgs_receipt_marketing_block(doc, order)
        self._mgs_receipt_invoice_block(doc, order)
        doc.barcode(order.name.replace("/", "-"), height=50, width=2)
        doc.align("left").cut()
        return doc

    def _mgs_receipt_marketing_block(self, doc, order):
        """QR de reseña de Google y/o de la web de la tienda, iguales a los
        del ticket en PDF (mgs_pos_receipt.py). Antes solo salían en el PDF:
        `qr()` (mgs_escpos.py) ya estaba implementado para esto — el propio
        comentario de `_mgs_receipt_qr` decía que la térmica «sí usa» el
        comando QR nativo — pero nunca se llegó a invocar aquí."""
        review_url = order._mgs_receipt_review_url()
        website_url = order._mgs_receipt_website_url()
        if not (review_url or website_url):
            return
        doc.align("center")
        if review_url:
            doc.wrapped(_("Valóranos en Google"))
            doc.qr(review_url)
        if website_url:
            doc.wrapped(website_url)
            doc.qr(website_url)
        doc.align("left")

    def _mgs_receipt_invoice_block(self, doc, order):
        """«¿Necesita factura?»: mismo QR que el recibo de pantalla del TPV
        (point_of_sale, campo `pos_qr_code`) para pedir la factura de esta
        venta online, con su código único debajo. Antes solo salía cuando el
        ticket se imprimía por el navegador (autoimpresión térmica
        desactivada, o botón «Imprimir factura»): en el ticket ESC/POS no
        salía nunca, aunque `qr()` (mgs_escpos.py) ya estaba implementado y
        sin usar."""
        if not order._mgs_receipt_invoice_qr_ready():
            return
        mode = order.company_id.point_of_sale_ticket_portal_url_display_mode
        url = order._mgs_receipt_invoice_portal_url()
        doc.align("center")
        doc.wrapped(_("¿Necesita factura de esta compra?"))
        if mode in ("qr_code", "qr_code_and_url"):
            doc.qr(url)
        if mode in ("url", "qr_code_and_url"):
            doc.wrapped(url)
        doc.wrapped(_("Código: %s", order.ticket_code))
        doc.align("left")
