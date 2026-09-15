# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

from .mgs_permissions import require_operator

# Colapsa cualquier secuencia de espacios (incluidos tabulaciones/saltos) en
# uno solo, después de quitar los de los extremos.
_WHITESPACE_RE = re.compile(r"\s+")


class ProductCategory(models.Model):
    _inherit = "product.category"

    # Odoo no trae categorías archivables. La floristería no quiere ver las
    # categorías de fábrica («Todo», «Todo/Vendible», «Todo/Gastos»,
    # «Todo/TPV»): son ruido para la dependienta y no significan nada en la
    # tienda. Con `active` se archivan en data/ux_defaults.xml y desaparecen
    # de todos los desplegables; la dueña crea las suyas sobre la marcha
    # (recepción → «Producto nuevo», ficha de producto → escribir la
    # categoría y esperar a que se guarde sola, ver mgs_category_widget.js).
    active = fields.Boolean(default=True)

    # Nombre normalizado (espacios colapsados y en minúsculas) para poder
    # buscar y evitar duplicados con `=` en vez de `ilike`: "Rosas",
    # "rosas " y "ROSAS" tienen que resolver a la MISMA categoría. Se
    # recalcula solo al escribir/crear (no depende de collation de BD).
    #
    # OJO: aposta NO hay una restricción única de base de datos sobre este
    # campo. Odoo no exige (ni en el núcleo, ni en sus propios datos de
    # prueba) que dos categorías tengan nombres distintos — hay
    # instalaciones y tests que crean varias categorías de nivel superior
    # con el mismo nombre sin que sea un error. Bloquear eso a nivel de
    # esquema rompería cosas ajenas a esta tienda. La deduplicación que
    # importa aquí es solo la de `mgs_find_or_create`, protegida con un
    # bloqueo consultivo (ver más abajo), no con un `_sql_constraints`.
    mgs_name_normalized = fields.Char(compute="_compute_mgs_name_normalized", store=True, index=True)

    @api.depends("name")
    def _compute_mgs_name_normalized(self):
        for category in self:
            category.mgs_name_normalized = category._mgs_normalize(category.name)

    @api.model
    def _mgs_normalize(self, name):
        return _WHITESPACE_RE.sub(" ", (name or "").strip()).casefold()

    @api.model
    def mgs_find_or_create(self, name):
        """Reutiliza una categoría de nivel superior existente por nombre
        normalizado o crea una nueva (sin padre: esta tienda no anida
        categorías). Pensado para llamarse al salir del campo de categoría
        en el TPV/recepción/ficha de producto (`mgs_category_widget.js`):
        idempotente ante doble clic o reintento.

        Dos peticiones casi simultáneas para el MISMO nombre se serializan
        con un bloqueo consultivo de PostgreSQL (`pg_advisory_xact_lock`,
        con la clave = hash del nombre normalizado): la segunda espera a que
        la primera termine y confirme, y entonces la encuentra por búsqueda
        en vez de crear un duplicado. El bloqueo se libera solo al terminar
        la transacción, y no afecta a ninguna otra categoría del sistema."""
        require_operator(self.env)
        normalized = self._mgs_normalize(name)
        if not normalized:
            raise UserError(self.env._("Escribe un nombre de categoría."))
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [normalized])
        domain = [("mgs_name_normalized", "=", normalized), ("parent_id", "=", False)]
        existing = self.search(domain, limit=1)
        if existing:
            return existing
        return self.create({"name": (name or "").strip(), "parent_id": False})

    @api.model
    def mgs_find_or_create_rpc(self, name):
        """Misma operación que `mgs_find_or_create`, en forma segura para
        RPC: un recordset no se serializa de forma útil hacia el navegador,
        así que aquí se devuelve un diccionario plano (id + nombre ya
        guardado)."""
        category = self.mgs_find_or_create(name)
        return {"id": category.id, "name": category.display_name}
