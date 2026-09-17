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
            const { limit_categories, iface_available_categ_ids } = this.pos.config;
            if (limit_categories && iface_available_categ_ids.length > 0) {
                const categoryIds = iface_available_categ_ids.flatMap((category) =>
                    category.getAllChildren().map((child) => child.id)
                );
                domain.push(["pos_categ_ids", "in", categoryIds]);
            }

            // `searchRead` actualiza los artículos ya cargados y, mediante
            // sus relaciones, carga también los botones de categoría nuevos.
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
