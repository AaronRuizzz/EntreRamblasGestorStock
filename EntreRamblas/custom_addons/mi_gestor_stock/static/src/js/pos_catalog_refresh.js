/** @odoo-module **/
/**
 * La caja carga el catálogo al abrirse. Una recepción posterior ya crea el
 * producto con `available_in_pos`, pero la parrilla de una sesión abierta no
 * conoce ese registro hasta que se le piden expresamente los cambios. Esta
 * acción usa el mismo cargador nativo de Odoo que la búsqueda del TPV: añade
 * productos, sus categorías y sus reglas de precio al catálogo ya abierto,
 * sin recargar la página ni tocar el pedido que la dependienta está haciendo.
 */
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { Navbar } from "@point_of_sale/app/navbar/navbar";

patch(Navbar.prototype, {
    async mgsRefreshCatalog() {
        if (this.mgsCatalogRefreshInProgress) {
            return;
        }
        this.mgsCatalogRefreshInProgress = true;
        try {
            const domain = [
                ["available_in_pos", "=", true],
                ["sale_ok", "=", true],
            ];
            // `searchRead` actualiza los artículos ya cargados y, mediante
            // sus relaciones, carga también los botones de categoría nuevos.
            // No se reutiliza el filtro de categorías de `this.pos.config`:
            // una caja que ya estaba abierta puede conservar el antiguo
            // «Food/Drinks» aunque el servidor lo haya retirado. El catálogo
            // de esta floristería siempre debe mostrar todas sus categorías.
            const products = await this.pos.data.searchRead("product.product", domain);
            await this.pos.processProductAttributesByProducts(products);
            await this.pos._loadMissingPricelistItems(products);
            this.pos.computeProductPricelistCache();
            this.notification.add(_t("Catálogo actualizado."), { type: "success" });
        } catch {
            this.notification.add(
                _t("No se pudo actualizar el catálogo. Comprueba la conexión con el servidor."),
                { type: "danger" }
            );
        } finally {
            this.mgsCatalogRefreshInProgress = false;
        }
    },
});
