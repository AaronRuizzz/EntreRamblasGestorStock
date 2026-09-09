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
import logging

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
        "Carpeta de las copias",
        default=lambda self: self.env["mgs.backup"]._mgs_default_dir())
    backup_every_hours = fields.Integer("Hacer una copia cada (horas)", default=6)
    backup_retention_days = fields.Integer("Días de conservación", default=30)
    backup_ssd_dir = fields.Char("Carpeta de réplica en SSD",
        help="Carpeta existente del disco externo. Se mantiene también la copia local.")
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
                    "No hay ninguna caja configurada. Pide a la propietaria "
                    "que cree una en Ajustes → Punto de venta."))
            else:
                raise UserError(_(
                    "Hay más de una caja configurada y no se ha dicho cuál es "
                    "la de la tienda. Pide a la propietaria que elija una en "
                    "Configuración → Dispositivos → «Caja de la tienda»."))
        return pos_config.open_ui()

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
                escpos.send_network(payload, self.printer_host, self.printer_port,
                                    timeout=self.printer_timeout or 5)
            elif self.printer_mode == "windows":
                escpos.send_windows(payload, self.printer_name, doc_name)
            else:
                escpos.send_path(payload, self.printer_path)
        except escpos.PrinterError as err:
            raise UserError(str(err)) from err
        return True

    def _mgs_company_header(self, doc):
        """Cabecera del ticket: nombre, dirección y NIF de la tienda."""
        company = self.env.company
        doc.align("center").bold(True).size(1, 2).ln(company.name).size().bold(False)
        street = ", ".join(part for part in [company.street, company.city] if part)
        if street:
            doc.ln(street)
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
            doc.align("center").ln(self.receipt_footer).align("left")
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
        """Qué hardware hay activo. El TPV lo consulta una vez, al abrir."""
        require_operator(self.env)
        config = self._mgs_get()
        return {
            "escpos_receipt": bool(config.pos_autoprint and config.printer_mode != "disabled"),
            "drawer": bool(config.drawer_enabled and config.drawer_on_sale
                           and config.printer_mode != "disabled"),
        }

    def _mgs_pos_ticket(self, order):
        """Construye el ticket ESC/POS de una venta del TPV."""
        self.ensure_one()
        doc = self._mgs_doc()
        currency = order.currency_id or self.env.company.currency_id
        self._mgs_company_header(doc)

        date = fields.Datetime.context_timestamp(self, order.date_order)
        doc.columns(order.name, date.strftime("%d/%m/%Y %H:%M"))
        if order.partner_id:
            doc.ln(_("Cliente: %s", order.partner_id.name))
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
            doc.ln(self.receipt_footer)
        doc.ln()
        doc.barcode(order.name.replace("/", "-"), height=50, width=2)
        doc.align("left").cut()
        return doc
