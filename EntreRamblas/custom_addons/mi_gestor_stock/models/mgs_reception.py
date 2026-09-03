# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError


class MgsReception(models.TransientModel):
    """Pantalla de recepción de mercancía, con dos modos:

      - "existente": se escanea el código y, como el producto ya está dado de
        alta, se reutiliza toda su información; solo se refrescan la fecha de
        recepción y la de caducidad.
      - "nuevo": se rellena la información del producto y se le asigna un código
        escaneándolo; al añadirlo se crea el producto y entra en la lista.

    El registro que queda de verdad es el stock.picking de entrada que se crea y
    valida en action_confirm(); este wizard es solo el bloc de notas donde se
    acumulan las líneas mientras se escanea.
    """
    _name = "mgs.reception"
    _inherit = ["barcodes.barcode_events_mixin"]
    _description = "Recepción de mercancía"
    _transient_max_hours = 8.0

    mode = fields.Selection([
        ("existente", "Producto existente"),
        ("nuevo", "Producto nuevo"),
    ], string="Modo", default="existente", required=True)

    line_ids = fields.One2many("mgs.reception.line", "reception_id", string="Líneas")
    scan_message = fields.Char(readonly=True)

    # --- modo "existente" ---
    manual_barcode = fields.Char(
        string="Código de barras",
        help="Respaldo para teclear el código a mano si el lector no engancha.")

    # --- modo "nuevo" ---
    new_barcode = fields.Char("Código de barras")
    new_name = fields.Char("Nombre del producto")
    new_categ_id = fields.Many2one("product.category", string="Categoría")
    new_price = fields.Float("Precio de venta", digits="Product Price")
    new_cost = fields.Float("Precio de coste", digits="Product Price")
    new_expiry_date = fields.Date("Caduca el")

    # ------------------------------------------------------------------
    # Entrada de escaneos
    # ------------------------------------------------------------------
    def on_barcode_scanned(self, barcode):
        """Override del mixin barcodes.barcode_events_mixin: se llama cuando el
        lector (en modo HID, en cualquier parte de la pantalla) termina una
        lectura con Enter."""
        self.ensure_one()
        barcode = (barcode or "").strip()
        if not barcode:
            return
        if self.mode == "nuevo":
            self._mgs_assign_new_barcode(barcode)
        else:
            self._mgs_add_barcode(barcode)

    @api.onchange("manual_barcode")
    def _onchange_manual_barcode(self):
        code = (self.manual_barcode or "").strip()
        self.manual_barcode = False
        if code:
            self._mgs_add_barcode(code)

    @api.onchange("mode")
    def _onchange_mode(self):
        self.scan_message = False

    def _mgs_assign_new_barcode(self, barcode):
        """Modo 'nuevo': el escaneo rellena el código del producto que se va a dar
        de alta, avisando si ya lo tiene otro."""
        existing = self._mgs_find_product(barcode)
        if existing:
            self.scan_message = _(
                "Ese código ya es de «%s». Cambia a «Producto existente» para recibirlo.",
                existing.display_name)
            return
        self.new_barcode = barcode
        self.scan_message = _("Código %s asignado al producto nuevo.", barcode)

    def _mgs_add_barcode(self, barcode):
        """Modo 'existente': busca el producto y suma una unidad a su línea."""
        product = self._mgs_find_product(barcode)
        if not product:
            self.scan_message = _(
                "«%s» no está dado de alta. Cambia a «Producto nuevo» para crearlo.",
                barcode)
            return

        line = self.line_ids.filtered(lambda l: l.product_id.id == product.id)[:1]
        if line:
            line.quantity += 1
        else:
            # OJO: nunca `self.line_ids = [Command.create({...})]` aqui.
            # Este wizard es un TransientModel NUEVO (sin _origin): esa
            # asignacion arranca de ids=() en convert_to_cache y BORRA las
            # lineas ya añadidas (odoo/fields.py, _RelationalMulti, ~4446).
            # Hay que concatenar con |= sobre un .new(...).
            self.line_ids |= self.env["mgs.reception.line"].new({
                "product_id": product.id,
                "quantity": 1.0,
                "expiry_date": product.product_tmpl_id.mgs_expiry_date,
            })
        self.scan_message = _("%s · +1", product.display_name)

    def _mgs_find_product(self, barcode):
        Product = self.env["product.product"]
        product = Product.search([("barcode", "=", barcode)], limit=1)
        if not product:
            product = Product.search([("default_code", "=", barcode)], limit=1)
        return product

    # ------------------------------------------------------------------
    # Modo "nuevo": alta del producto
    # ------------------------------------------------------------------
    def action_add_new_product(self):
        self.ensure_one()
        if not self.new_name:
            raise UserError(_("Escribe el nombre del producto."))
        if not self.new_barcode:
            raise UserError(_("Escanea el código de barras del producto nuevo."))
        if self._mgs_find_product(self.new_barcode):
            raise UserError(_("Ya existe un producto con el código %s.", self.new_barcode))

        template = self.env["product.template"].create({
            "name": self.new_name,
            "barcode": self.new_barcode,
            "list_price": self.new_price,
            "standard_price": self.new_cost,
            "categ_id": self.new_categ_id.id or self.env.ref("product.product_category_all").id,
            "is_storable": True,
            "sale_ok": True,
            "available_in_pos": True,
            "mgs_expiry_date": self.new_expiry_date,
        })
        self.line_ids |= self.env["mgs.reception.line"].new({
            "product_id": template.product_variant_id.id,
            "quantity": 1.0,
            "expiry_date": self.new_expiry_date,
        })
        self.scan_message = _("%s creado y añadido.", template.name)

        # Deja el formulario limpio para dar de alta otro producto nuevo.
        self.new_barcode = False
        self.new_name = False
        self.new_categ_id = False
        self.new_price = 0.0
        self.new_cost = 0.0
        self.new_expiry_date = False

    def action_clear(self):
        self.ensure_one()
        self.line_ids = [Command.clear()]
        self.scan_message = False

    # ------------------------------------------------------------------
    # Guardar en almacén: crea y valida un albarán de entrada real
    # ------------------------------------------------------------------
    def _mgs_get_picking_type(self):
        picking_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("company_id", "=", self.env.company.id),
        ], limit=1)
        if not picking_type:
            raise UserError(_(
                "No hay ningún tipo de operación de entrada configurado para "
                "esta empresa."))
        return picking_type

    def action_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Escanea al menos un producto antes de guardar."))

        picking_type = self._mgs_get_picking_type()
        src = picking_type.default_location_src_id or self.env.ref("stock.stock_location_suppliers")
        dest = picking_type.default_location_dest_id or self.env.ref("stock.stock_location_stock")

        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": src.id,
            "location_dest_id": dest.id,
            "origin": _("Recepción rápida"),
            "move_ids": [Command.create({
                "name": line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": line.quantity,
                "product_uom": line.product_id.uom_id.id,
                "location_id": src.id,
                "location_dest_id": dest.id,
            }) for line in self.line_ids],
        })
        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        result = picking.button_validate()
        if isinstance(result, dict):
            # Caso defensivo: alguna configuracion no estandar del tipo de
            # operacion pide un wizard (backorder, lotes...). Se lo pasamos
            # al usuario en vez de asumir que la recepcion quedo validada.
            return result

        # Refresca fecha de recepcion y caducidad de cada producto recibido.
        today = fields.Date.context_today(self)
        for line in self.line_ids:
            vals = {"mgs_reception_date": today}
            if line.expiry_date:
                vals["mgs_expiry_date"] = line.expiry_date
            line.product_id.product_tmpl_id.write(vals)

        message = _("%(n)s productos guardados en almacén · albarán %(ref)s",
                    n=len(self.line_ids), ref=picking.name)
        new_wizard = self.create({})
        reopen = self.env["ir.actions.actions"]._for_xml_id("mi_gestor_stock.action_mgs_reception")
        reopen["res_id"] = new_wizard.id
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("Guardado en almacén"),
                "message": message,
                "next": reopen,
            },
        }


class MgsReceptionLine(models.TransientModel):
    _name = "mgs.reception.line"
    _description = "Línea de recepción"
    _transient_max_hours = 8.0

    reception_id = fields.Many2one("mgs.reception", required=True, ondelete="cascade", index=True)
    product_id = fields.Many2one("product.product", string="Producto", required=True)
    barcode = fields.Char(related="product_id.barcode", readonly=True)
    quantity = fields.Float(string="Unidades", default=1.0, required=True,
                             digits='Product Unit of Measure')
    qty_available = fields.Float(related="product_id.qty_available", string="Stock actual",
                                  readonly=True)
    expiry_date = fields.Date("Caduca el")
