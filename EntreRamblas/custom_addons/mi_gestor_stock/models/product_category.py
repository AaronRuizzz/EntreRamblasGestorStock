# -*- coding: utf-8 -*-
"""Categorías de producto: una sola lista para el almacén y para la caja.

Odoo lleva DOS clasificaciones distintas y sin relación entre ellas:

  * `product.category` — la del almacén. Es la que se elige al dar de alta un
    producto en Recepción, la que agrupa el panel de Stock y la que sale en
    los informes.
  * `pos.category`     — la del TPV. Es la que dibuja los botones de la
    pantalla de venta; `pos_categ_ids` del producto decide bajo qué botón
    aparece cada artículo.

Para la tienda eso serían dos listas que mantener a mano, y la del TPV viene
vacía: sin ningún botón, la pantalla de venta enseña el catálogo entero en una
sola parrilla y hay que buscar cada cosa por el nombre.

Aquí manda la del almacén: cada categoría activa tiene su **espejo** en el TPV
(`mgs_pos_categ_id`), que se crea, se renombra, se recoloca y se retira solo.
La dueña sigue creando categorías donde siempre — Recepción → «Producto nuevo»
→ escribir la categoría y «Crear» — y el botón aparece en la caja sin tocar
nada más. Los botones salen por orden alfabético (`pos.category` ordena por
`sequence, name` y todos los espejos nacen con la misma secuencia), el mismo
orden con el que la dueña ve las categorías en el panel de Stock.

Un producto en una categoría **sin** espejo (las de fábrica, archivadas en
data/ux_defaults.xml) no desaparece de la caja: sigue en la parrilla general y
en el buscador, solo que sin botón propio.
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Las categorías genéricas que Odoo precarga. No significan nada en una
# floristería: son las que se archivan para que no estorben (ver
# `_mgs_archive_factory_categories`).
FACTORY_CATEGORIES = (
    "product.product_category_all",          # «Todo»
    "product.product_category_1",            # «Todo / Vendible»
    "product.cat_expense",                   # «Todo / Gastos»
    "point_of_sale.product_category_pos",    # «Todo / Vendible / TPV»
)


class ProductCategory(models.Model):
    _inherit = "product.category"

    # Odoo no trae categorías archivables. La floristería no quiere ver las
    # categorías de fábrica («Todo», «Todo/Vendible», «Todo/Gastos»,
    # «Todo/TPV»): son ruido para la dependienta y no significan nada en la
    # tienda. Con `active` se archivan en data/ux_defaults.xml y desaparecen
    # de todos los desplegables; la dueña crea las suyas sobre la marcha
    # (recepción → «Producto nuevo» → escribir la categoría y «Crear»).
    active = fields.Boolean(default=True)

    mgs_pos_categ_id = fields.Many2one(
        "pos.category", string="Botón equivalente en el TPV",
        copy=False, readonly=True, ondelete="set null",
        help="Categoría del TPV que corresponde a esta del almacén. Se "
             "mantiene sola: no hace falta tocarla.")

    # ==================================================================
    # Espejo en el TPV
    # ==================================================================
    @api.model_create_multi
    def create(self, vals_list):
        categories = super().create(vals_list)
        categories._mgs_sync_pos_categories()
        return categories

    def write(self, vals):
        res = super().write(vals)
        # Solo lo que cambia el espejo: cómo se llama el botón, si existe
        # (`active`) y de quién cuelga. Guardar el enlace (`mgs_pos_categ_id`)
        # es la propia sincronización: no vuelve a entrar aquí.
        if {"name", "active", "parent_id"} & set(vals):
            self._mgs_sync_pos_categories()
        return res

    def unlink(self):
        # El botón se va con la categoría. Va ANTES del borrado: si hay una
        # sesión de TPV abierta, `pos.category` lo impide con su propio aviso
        # y no se borra tampoco la categoría, en vez de dejar en la caja un
        # botón huérfano que ya nadie sabría a qué pertenecía.
        self.mgs_pos_categ_id.sudo().unlink()
        return super().unlink()

    def _mgs_sync_pos_categories(self):
        """Pone al día el botón de TPV de estas categorías.

        Idempotente: se puede llamar tantas veces como haga falta — cada alta,
        cada cambio de nombre y el repaso completo de cada `-u`.

        Con una caja abierta, Odoo no deja retirar categorías del TPV (la venta
        en curso las tiene cargadas). Eso no se trata como un error: la baja se
        aplaza al siguiente repaso y se sigue adelante. Archivar categorías es
        parte de la actualización del módulo, y una venta a medias no puede
        abortarla.
        """
        PosCategory = self.env["pos.category"].sudo()
        # De padres a hijos: `complete_name` es la ruta completa, así que
        # «Flores» va antes que «Flores / Rosas» y el espejo del padre ya
        # existe cuando le toca al hijo.
        categories = self.sudo().sorted(lambda categ: categ.complete_name or "")
        # Un botón que ya es espejo de otra categoría no lo puede adoptar una
        # segunda. `active_test=False` a propósito: una categoría archivada
        # cuya baja quedó aplazada (caja abierta) sigue apuntando a su botón, y
        # una categoría nueva que se llame igual no debe quedarse con él —
        # cuando por fin se retire, se llevaría por delante el de la nueva.
        claimed = self.with_context(active_test=False).sudo().search(
            [("mgs_pos_categ_id", "!=", False)]).mgs_pos_categ_id
        session_open = self._mgs_pos_session_open()
        relinked = self.browse()

        for category in categories:
            mirror = category.mgs_pos_categ_id

            # --- Archivada: el botón se retira de la caja ---
            if not category.active:
                if not mirror:
                    continue
                if session_open:
                    _logger.info(
                        "mi_gestor_stock: la categoría «%s» se archiva con una sesión "
                        "de TPV abierta; su botón se retira en la próxima actualización.",
                        category.display_name)
                    continue
                category.mgs_pos_categ_id = False
                mirror.unlink()
                relinked |= category
                continue

            # --- Activa: tiene que haber botón ---
            if not mirror:
                # Adopta uno que ya exista con ese nombre (una caja preparada a
                # mano, o un escenario de ejemplo del TPV) en vez de duplicarlo.
                mirror = PosCategory.search(
                    [("name", "=", category.name), ("id", "not in", claimed.ids)], limit=1)
                if not mirror:
                    mirror = PosCategory.create({"name": category.name})
                claimed |= mirror
                category.mgs_pos_categ_id = mirror
                relinked |= category

            parent_mirror = category.parent_id.sudo().mgs_pos_categ_id
            values = {}
            if mirror.name != category.name:
                values["name"] = category.name
            if mirror.parent_id != parent_mirror:
                # Un padre archivado no tiene espejo: el hijo se queda como
                # botón de primer nivel en vez de colgar de la nada.
                values["parent_id"] = parent_mirror.id
            if values:
                mirror.write(values)

        # Los productos de las categorías cuyo botón acaba de aparecer (o de
        # irse) tienen que seguirlo: si no, el botón saldría vacío.
        if relinked:
            self.env["product.template"].with_context(active_test=False).search(
                [("categ_id", "in", relinked.ids)])._mgs_apply_pos_category()

    @api.model
    def _mgs_archive_factory_categories(self):
        """Archiva las cuatro categorías genéricas de Odoo.

        En Python y no con un `<record>` en data/ux_defaults.xml, aunque se lea
        peor: las cuatro viven en bloques `noupdate="1"` de `product` y de
        `point_of_sale`, y Odoo **salta** un `<record>` sobre un xml_id marcado
        así cuando el módulo se ACTUALIZA (odoo/models.py, `_load_records`:
        `if not (update and d_noupdate)`). Con `<record>` se archivaban solo en
        la instalación inicial: en una base ya instalada seguían vivas para
        siempre, apareciendo en el desplegable de categoría y —desde que las
        categorías llegan al TPV— como un botón «All» con el catálogo entero
        dentro. Es el mismo motivo por el que la salida del TPV se reapunta con
        `<function>` en ese archivo, y `base.main_company` desde res_company.py.
        """
        for xmlid in FACTORY_CATEGORIES:
            category = self.env.ref(xmlid, raise_if_not_found=False)
            if category and category.active:
                category.active = False
                _logger.info("mi_gestor_stock: categoría de fábrica «%s» archivada.", xmlid)

    @api.model
    def _mgs_sync_all_pos_categories(self):
        """Repaso completo. Lo llama data/ux_defaults.xml en cada `-u`, después
        de archivar las categorías de fábrica: deja la caja con exactamente los
        botones de las categorías vivas del almacén, también en las bases que
        ya venían llenas de antes."""
        self.with_context(active_test=False).search([])._mgs_sync_pos_categories()

    @api.model
    def _mgs_pos_session_open(self):
        """¿Hay una caja abierta ahora mismo? `pos.category` no deja borrar
        categorías mientras la haya (una venta a medias las tiene cargadas)."""
        return bool(self.env["pos.session"].sudo().search_count([("state", "!=", "closed")]))
