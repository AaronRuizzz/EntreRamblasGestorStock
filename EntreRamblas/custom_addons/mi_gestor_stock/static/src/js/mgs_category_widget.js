/** @odoo-module **/
/**
 * Categorías que se guardan solas.
 *
 * Un campo de texto simple (no el desplegable habitual de Odoo): al salir
 * del campo se busca una categoría existente con ese nombre —espacios y
 * mayúsculas no cuentan— y si no hay ninguna, se crea. El servidor
 * (`product.category.mgs_find_or_create`, models/product_category.py) es
 * quien decide de verdad; aquí solo se refleja "Guardando…" / "Categoría
 * guardada" / error con reintento, sin perder nunca lo escrito.
 *
 * Se usa en la ficha de producto (`categ_id`) y en la recepción
 * (`new_categ_id`) con `options="{'widget': 'mgs_category_autocreate'}"`.
 */
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { Component, useState, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Record } from "@web/model/relational_model/record";

// Guardar el producto/recepción tiene que esperar a que termine cualquier
// creación/reutilización de categoría en curso: así nunca se guarda el
// registro con una categoría a medio resolver.
const mgsPendingCategorySaves = new Set();

patch(Record.prototype, {
    async save(options) {
        if (mgsPendingCategorySaves.size) {
            await Promise.allSettled([...mgsPendingCategorySaves]);
        }
        return super.save(...arguments);
    },
});

export class MgsCategoryAutocreate extends Component {
    static template = "mi_gestor_stock.MgsCategoryAutocreate";
    static props = {
        ...standardFieldProps,
        placeholder: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ text: this._savedName(this.props), status: "idle" });
        onWillUpdateProps((nextProps) => {
            // Si el registro cambia por fuera (descartar, recargar) y no hay
            // nada en vuelo, se refleja el valor guardado de verdad.
            if (this.state.status !== "saving") {
                this.state.text = this._savedName(nextProps);
                this.state.status = "idle";
            }
        });
    }

    _savedName(props) {
        const value = props.record.data[props.name];
        return value ? value[1] : "";
    }

    onInput(ev) {
        this.state.text = ev.target.value;
        if (this.state.status !== "saving") {
            this.state.status = "idle";
        }
    }

    onBlur() {
        const text = this.state.text.trim();
        const saved = this._savedName(this.props);
        if (text === saved || (this.state.status === "saved" && text === this.state.text)) {
            return;
        }
        if (!text) {
            this.props.record.update({ [this.props.name]: false });
            this.state.status = "idle";
            return;
        }
        this._save(text);
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            ev.target.blur();
        }
    }

    _save(text) {
        this.state.status = "saving";
        const promise = this.orm
            .call("product.category", "mgs_find_or_create_rpc", [text])
            .then((result) => {
                this.props.record.update({ [this.props.name]: [result.id, result.name] });
                this.state.text = result.name;
                this.state.status = "saved";
                browser.setTimeout(() => {
                    if (this.state.status === "saved") {
                        this.state.status = "idle";
                    }
                }, 2000);
            })
            .catch((error) => {
                this.state.status = "error";
                throw error;
            })
            .finally(() => mgsPendingCategorySaves.delete(promise));
        mgsPendingCategorySaves.add(promise);
        // El estado "error" ya queda reflejado en la interfaz; el botón
        // "Reintentar" repite la llamada, así que no hace falta relanzar el
        // error aquí (evita un "unhandled rejection" en la consola).
        promise.catch(() => {});
    }

    onRetry() {
        this._save(this.state.text.trim());
    }
}

registry.category("fields").add("mgs_category_autocreate", {
    component: MgsCategoryAutocreate,
    supportedTypes: ["many2one"],
    extractProps: ({ attrs }) => ({
        placeholder: attrs.placeholder,
    }),
});
