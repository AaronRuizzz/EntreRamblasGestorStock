# -*- coding: utf-8 -*-
from datetime import datetime, time
import pytz
from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare

from .mgs_permissions import assert_not_maintenance


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
    # Sin un campo de título Odoo muestra el identificador técnico del
    # transient (por ejemplo, «mgs.reception,8») en cuanto el formulario se
    # guarda al crear una categoría o al procesar un escaneo.
    _rec_name = "name"
    _transient_max_hours = 8.0

    name = fields.Char(default=lambda self: _("Recepción de mercancía"), readonly=True)
    mode = fields.Selection([
        ("existente", "Producto existente"),
        ("nuevo", "Producto nuevo"),
    ], string="Modo", default="existente", required=True)

    line_ids = fields.One2many("mgs.reception.line", "reception_id", string="Líneas")
    scan_message = fields.Char(readonly=True)
    supplier_id = fields.Many2one("res.partner", string="Proveedor")
    picking_id = fields.Many2one("stock.picking", readonly=True, copy=False)

    # Datos del albarán del proveedor. Opcionales a propósito: no toda
    # recepción trae albarán (una compra de urgencia, una donación, una
    # corrección), y exigirlos entorpecería justo lo que se quiere facilitar.
    supplier_ref = fields.Char("Nº de albarán del proveedor")
    document_date = fields.Date("Fecha del albarán")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    # --- modo "existente" ---
    manual_barcode = fields.Char(
        string="Código de barras",
        help="Respaldo para teclear el código a mano si el lector no engancha.")

    # --- modo "nuevo" ---
    new_barcode = fields.Char("Código de barras")
    new_name = fields.Char("Nombre del producto")
    new_categ_id = fields.Many2one(
        "product.category", string="Categoría",
        default=lambda self: self._mgs_default_category())
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id, readonly=True)
    new_cost = fields.Float("Precio de coste", digits="Product Price")
    # Calculadora de margen: mismo criterio que las calculadoras financieras
    # de márgenes (no el «markup» de comercio, que sería sobre el coste): el
    # margen es la parte del PRECIO DE VENTA que es beneficio, así que
    # PVP sin IVA = coste / (1 - margen/100). Con coste 10 € y margen 30 %
    # salen 14,29 €, no 13 €. `new_markup_hint` muestra la equivalencia sobre
    # el coste al lado, para que la cifra no sea una caja negra.
    new_margin_preset = fields.Selection([
        ("10", "10 %"), ("20", "20 %"), ("30", "30 %"), ("40", "40 %"), ("60", "60 %"),
        ("otro", "Otro"),
    ], string="Margen", default="30")
    new_margin = fields.Float("Margen sobre el precio de venta (%)", default=30.0)
    new_margin_amount = fields.Float(
        "Beneficio", digits="Product Price", readonly=True,
        help="Precio de venta sin IVA menos el coste.")
    new_markup_hint = fields.Char("Equivalencia", readonly=True)
    new_price = fields.Float("Precio de venta sin IVA", digits="Product Price")
    new_tax_id = fields.Many2one(
        "account.tax", string="IVA",
        # En la recepción solo se trabajan los dos tipos habituales de la
        # tienda. La dueña conserva la opción nativa de crear otro impuesto
        # desde el desplegable si su gestoría se lo indica.
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id), "
               "('amount_type', '=', 'percent'), ('amount', 'in', [0, 21])]",
        default=lambda self: self._mgs_default_sale_tax())
    new_price_taxed = fields.Float("Precio de venta", digits="Product Price")
    new_expiry_date = fields.Date("Caduca el")
    # Alquiler para eventos (campo real en product.template, ver
    # models/mgs_event.py): se decide aquí, al recibir el producto, para no
    # tener que volver a la ficha después.
    new_rental_ok = fields.Boolean("Se alquila para eventos")
    new_rental_deposit = fields.Float(
        "Fianza por unidad", digits="Product Price",
        help="Importe que se pide en depósito por cada unidad que sale.")

    # ------------------------------------------------------------------
    # Entrada de escaneos
    # ------------------------------------------------------------------
    def on_barcode_scanned(self, barcode):
        """Override del mixin barcodes.barcode_events_mixin: se llama cuando el
        lector (en modo HID, en cualquier parte de la pantalla) termina una
        lectura con Enter.

        Tanto el Honeywell (Bluetooth -> base -> teclado) como el PcCom
        (dongle 2,4 GHz -> teclado) entregan la lectura como texto tecleado,
        así que los dos entran por aquí. `mgs_clean_scan` quita el prefijo o
        el sufijo que se les haya programado (ver Configuración →
        Dispositivos)."""
        self.ensure_one()
        barcode = self.env["mgs.config"].mgs_clean_scan(barcode)
        if not barcode:
            return
        if self.mode == "nuevo":
            self._mgs_assign_new_barcode(barcode)
        else:
            self._mgs_add_barcode(barcode)

    @api.onchange("manual_barcode")
    def _onchange_manual_barcode(self):
        code = self.env["mgs.config"].mgs_clean_scan(self.manual_barcode)
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
                "unit_cost": product.standard_price,
            })
        self.scan_message = _("%s · +1", product.display_name)

    def _mgs_find_product(self, barcode):
        Product = self.env["product.product"]
        product = Product.search([("barcode", "=", barcode)], limit=1)
        if not product:
            product = Product.search([("default_code", "=", barcode)], limit=1)
        return product

    # ------------------------------------------------------------------
    # Modo "nuevo": precio con/sin IVA reactivo
    # ------------------------------------------------------------------
    @api.model
    def _mgs_default_category(self):
        """Categoría de partida para una floristería española.

        Se crea una única vez si aún no existe. El modelo de categorías crea
        también su botón equivalente en el TPV, por lo que el artículo estará
        clasificado correctamente al actualizar el catálogo de la caja.
        """
        Category = self.env["product.category"]
        category = Category.search([("mgs_name_normalized", "=", "flor cortada")], limit=1)
        return category or Category.create({"name": _("Flor cortada")})

    @api.model
    def _mgs_default_sale_tax(self):
        """IVA general español (21 %) como opción inicial de la tienda.

        La lista del alta solo muestra 21 % y 0 %. La localización española
        distingue bienes (``G``) de servicios, así que se prefiere el de
        bienes cuando exista más de uno con el mismo porcentaje.
        """
        taxes = self.env["account.tax"].search([
            ("type_tax_use", "=", "sale"),
            ("company_id", "=", self.env.company.id),
            ("amount_type", "=", "percent"),
            ("amount", "=", 21),
        ])
        goods_tax = taxes.filtered(lambda tax: (tax.name or "").strip().endswith(" G"))
        return (goods_tax or taxes or self.env.company.account_sale_tax_id)[:1]

    def _mgs_new_tax_ratio(self):
        """(incluido, excluido) para una base de 1.0 con new_tax_id, o (1.0, 1.0)
        sin impuesto elegido — mismo patrón que mgs_event._mgs_pos_price_unit."""
        if not self.new_tax_id:
            return 1.0, 1.0
        result = self.new_tax_id.compute_all(
            1.0, currency=self.company_id.currency_id, quantity=1.0)
        return (result.get("total_included") or 1.0), (result.get("total_excluded") or 1.0)

    @api.onchange("new_price", "new_tax_id")
    def _onchange_new_price(self):
        precision = self.env["decimal.precision"].precision_get("Product Price")
        included, excluded = self._mgs_new_tax_ratio()
        if not excluded:
            return
        expected = self.new_price * (included / excluded)
        if float_compare(expected, self.new_price_taxed, precision_digits=precision) != 0:
            self.new_price_taxed = expected

    @api.onchange("new_price_taxed")
    def _onchange_new_price_taxed(self):
        precision = self.env["decimal.precision"].precision_get("Product Price")
        included, excluded = self._mgs_new_tax_ratio()
        if not included:
            return
        expected = self.new_price_taxed * (excluded / included)
        if float_compare(expected, self.new_price, precision_digits=precision) != 0:
            self.new_price = expected

    # ------------------------------------------------------------------
    # Modo "nuevo": calculadora de margen
    # ------------------------------------------------------------------
    _MARGIN_PRESETS = ("10", "20", "30", "40", "60")

    @api.onchange("new_margin_preset")
    def _onchange_new_margin_preset(self):
        """Pulsar un preset (10/20/30/40/60 %) fija el margen; «Otro» no
        toca nada, es solo lo que queda marcado cuando el margen no coincide
        con ningún preset (ver _onchange_new_price_margin_display)."""
        if self.new_margin_preset and self.new_margin_preset != "otro":
            self.new_margin = float(self.new_margin_preset)

    @api.onchange("new_margin", "new_cost")
    def _onchange_new_margin(self):
        """Margen -> precio de venta sin IVA: PVP = coste / (1 - margen/100).

        Un margen de 100 % o más pediría un precio infinito (o negativo); un
        coste de 0 no tiene margen que calcular sobre él. En los dos casos se
        deja el precio como esté, en vez de escribir un número sin sentido.
        """
        precision = self.env["decimal.precision"].precision_get("Product Price")
        if self.new_cost <= 0 or self.new_margin >= 100:
            return
        expected = self.new_cost / (1 - self.new_margin / 100.0)
        if float_compare(expected, self.new_price, precision_digits=precision) != 0:
            self.new_price = expected

    @api.onchange("new_price", "new_cost")
    def _onchange_new_price_margin_display(self):
        """Camino inverso: si se teclea el precio a mano (o cambia el coste),
        se recalculan el margen que ese precio representa, el beneficio en
        euros y su equivalencia sobre el coste — y el preset se marca «Otro»
        en cuanto el margen deja de coincidir con uno de los botones.

        Comparte disparador (`new_price`, `new_cost`) con el camino
        margen -> precio de arriba: cuando ES ese camino el que ha movido el
        precio, el margen recalculado aquí coincide con el que ya había
        (dentro de la precisión del campo) y el `float_compare` de abajo no
        vuelve a tocarlo, así que no hay bucle entre los dos onchange.
        """
        if self.new_cost <= 0 or self.new_price <= 0:
            self.new_margin_amount = 0.0
            self.new_markup_hint = False
            return
        self.new_margin_amount = self.new_price - self.new_cost
        markup_percent = (self.new_price - self.new_cost) / self.new_cost * 100
        self.new_markup_hint = _("equivale a +%s %% sobre el coste") % ("%.1f" % markup_percent)

        margin_from_price = (self.new_price - self.new_cost) / self.new_price * 100
        if float_compare(margin_from_price, self.new_margin, precision_digits=2) != 0:
            self.new_margin = margin_from_price
        matched_preset = next(
            (preset for preset in self._MARGIN_PRESETS
             if float_compare(margin_from_price, float(preset), precision_digits=0) == 0),
            "otro")
        if self.new_margin_preset != matched_preset:
            self.new_margin_preset = matched_preset

    # ------------------------------------------------------------------
    # Modo "nuevo": alta del producto
    # ------------------------------------------------------------------
    def action_add_new_product(self):
        self.ensure_one()
        if not self.new_name:
            raise UserError(_("Escribe el nombre del producto."))
        if self.new_cost < 0 or self.new_price < 0:
            raise UserError(_("El precio y el coste no pueden ser negativos."))
        if not self.new_barcode:
            raise UserError(_("Escanea el código de barras del producto nuevo."))
        if not self.new_categ_id:
            raise UserError(_("Elige una categoría para el producto, o escribe una "
                              "nueva y pulsa «Crear»."))
        if self._mgs_find_product(self.new_barcode):
            raise UserError(_("Ya existe un producto con el código %s.", self.new_barcode))

        vals = {
            "name": self.new_name,
            "barcode": self.new_barcode,
            "list_price": self.new_price,
            "standard_price": self.new_cost,
            "categ_id": self.new_categ_id.id,
            "is_storable": True,
            "sale_ok": True,
            "available_in_pos": True,
            "tracking": "lot",
            "mgs_auto_lots": True,
            "use_expiration_date": True,
            "mgs_rental_ok": self.new_rental_ok,
            "mgs_rental_deposit": self.new_rental_deposit if self.new_rental_ok else 0.0,
        }
        if self.new_tax_id:
            vals["taxes_id"] = [Command.set(self.new_tax_id.ids)]
        template = self.env["product.template"].create(vals)
        self.line_ids |= self.env["mgs.reception.line"].new({
            "product_id": template.product_variant_id.id,
            "quantity": 1.0,
            "expiry_date": self.new_expiry_date,
            "unit_cost": self.new_cost,
        })
        self.scan_message = _("%s creado y añadido.", template.name)

        # Deja el formulario limpio para dar de alta otro producto nuevo.
        self.new_barcode = False
        self.new_name = False
        self.new_categ_id = False
        self.new_price = 0.0
        self.new_price_taxed = 0.0
        self.new_cost = 0.0
        self.new_margin = 30.0
        self.new_margin_preset = "30"
        self.new_margin_amount = 0.0
        self.new_markup_hint = False
        self.new_rental_ok = False
        self.new_rental_deposit = 0.0
        self.new_expiry_date = False
        # Hallazgo 18: se limpiaba new_categ_id pero el formulario seguía en
        # modo "nuevo", que la vista exige rellenar (required="mode == 'nuevo'")
        # — "Guardar en almacén" quedaba bloqueado con «Campos no válidos:
        # Categoría» hasta cambiar el modo a mano. La categoría solo hace
        # falta al CREAR el producto, ya creado; volver a modo existente.
        self.mode = "existente"

    def action_mgs_generate_barcode(self):
        """Modo 'nuevo': código interno para un producto que llega sin EAN.

        Se rellena el campo, se crea el producto con él y luego se imprime la
        etiqueta con «Imprimir etiquetas»: a partir de ahí el producto se
        escanea como cualquier otro.
        """
        self.ensure_one()
        self.new_barcode = self.env["mgs.config"].mgs_next_internal_barcode()
        self.scan_message = _("Código interno %s generado. Imprime la etiqueta "
                              "cuando lo añadas.", self.new_barcode)
        return True

    def action_mgs_print_labels(self):
        """Una etiqueta por producto de la recepción, en la térmica de 80 mm."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No hay productos que etiquetar todavía."))
        products = self.env["product.product"].browse(
            [line.product_id.id for line in self.line_ids if line.product_id])
        return self.env["mgs.config"]._mgs_get()._mgs_print_labels(products)

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
        # Sin esto, mgs.maintenance (lo pone el actualizador antes de copiar
        # y aplicar una actualización) no bloqueaba nada aquí: la recepción
        # no pasa por require_manager (hallazgo 11).
        assert_not_maintenance(self.env)
        # Serializa reintentos y doble clic sobre el mismo asistente.
        self.env.cr.execute("SELECT id FROM mgs_reception WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["picking_id"])
        if self.picking_id:
            return {
                "type": "ir.actions.act_window", "res_model": "stock.picking",
                "view_mode": "form", "res_id": self.picking_id.id,
            }
        if not self.line_ids:
            raise UserError(_("Escanea al menos un producto antes de guardar."))

        # Candado por producto y en orden de id: sin el, una entrada simultanea
        # del mismo articulo podria confirmarse entre su comprobacion de stock y
        # su ajuste, y las existencias quedarian contadas dos veces.
        self.env.cr.execute("SELECT id FROM product_product WHERE id IN %s ORDER BY id FOR UPDATE",
                            [tuple(self.line_ids.product_id.ids)])

        for line in self.line_ids:
            if line.quantity <= 0 or line.unit_cost < 0:
                raise UserError(_("La cantidad debe ser positiva y el coste no puede ser negativo."))
            product = line.product_id
            if product.tracking == "serial":
                raise UserError(_("La recepción rápida trabaja por partidas, no por números de serie."))
            if product.tracking == "none":
                if self.env["stock.quant"].search_count([
                    ("product_id", "=", product.id), ("location_id.usage", "=", "internal"),
                    ("quantity", "!=", 0),
                ]):
                    raise UserError(_("%s tiene existencias sin partida. Regularízalas antes de activar las partidas.", product.display_name))
                product.write({"tracking": "lot", "use_expiration_date": True})
            product.mgs_auto_lots = True

        picking_type = self._mgs_get_picking_type()
        src = picking_type.default_location_src_id or self.env.ref("stock.stock_location_suppliers")
        dest = picking_type.default_location_dest_id or self.env.ref("stock.stock_location_stock")

        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": src.id,
            "location_dest_id": dest.id,
            "origin": self.supplier_ref or _("Recepción rápida"),
            "partner_id": self.supplier_id.id,
            "move_ids": [Command.create({
                "name": line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": line.quantity,
                "product_uom": line.product_id.uom_id.id,
                "location_id": src.id,
                "location_dest_id": dest.id,
            }) for line in self.line_ids],
        })
        self.picking_id = picking
        # No fusionar líneas: cada entrada conserva su coste y caducidad.
        picking.move_ids._action_confirm(merge=False)
        zone = pytz.timezone(self.env.user.tz or "Europe/Madrid")
        for line, move in zip(self.line_ids.sorted("id"), picking.move_ids.sorted("id")):
            expiry = (zone.localize(datetime.combine(line.expiry_date, time.max))
                      .astimezone(pytz.UTC).replace(tzinfo=None, microsecond=0)) if line.expiry_date else False
            lot = self.env["stock.lot"].create({
                "product_id": line.product_id.id,
                "company_id": picking.company_id.id,
                "expiration_date": expiry,
                "mgs_received_at": fields.Datetime.now(),
                "mgs_supplier_id": self.supplier_id.id,
                "mgs_supplier_ref": self.supplier_ref,
                "mgs_document_date": self.document_date,
                "mgs_unit_cost": line.unit_cost,
                "mgs_cost_recorded": True,
            })
            move.move_line_ids.unlink()
            self.env["stock.move.line"].create({
                "move_id": move.id, "picking_id": picking.id,
                "product_id": line.product_id.id, "product_uom_id": move.product_uom.id,
                "location_id": src.id, "location_dest_id": dest.id,
                "lot_id": lot.id, "quantity": line.quantity,
            })
            move.picked = True
        result = picking.with_context(skip_expired=True).button_validate()
        if isinstance(result, dict):
            # Caso defensivo: alguna configuracion no estandar del tipo de
            # operacion pide un wizard (backorder, lotes...). Se lo pasamos
            # al usuario en vez de asumir que la recepcion quedo validada.
            return result

        # Refresca fecha de recepcion y caducidad de cada producto recibido.
        today = fields.Date.context_today(self)
        for line in self.line_ids:
            vals = {"mgs_reception_date": today}
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
    unit_cost = fields.Float("Coste por unidad", digits="Product Price", required=True)
    uom_id = fields.Many2one(related="product_id.uom_id", string="Unidad", readonly=True)
    # Para que en la propia lista de la recepción se vea de un vistazo qué
    # es alquiler y qué no, sin tener que abrir cada ficha de producto.
    rental_ok = fields.Boolean(related="product_id.mgs_rental_ok", string="Alquiler", readonly=True)

    def action_mgs_print_label(self):
        """Etiqueta solo de este producto (botón de la línea)."""
        self.ensure_one()
        return self.env["mgs.config"]._mgs_get()._mgs_print_labels(self.product_id)
