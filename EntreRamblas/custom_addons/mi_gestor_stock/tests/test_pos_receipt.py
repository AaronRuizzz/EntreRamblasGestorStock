# -*- coding: utf-8 -*-
"""Hallazgo 23: el recibo (pantalla / impresión por navegador) mostraba base e
IVA en positivo con el total en negativo en una devolución. La plantilla
nativa (point_of_sale.OrderReceipt) aplica `taxTotals.order_sign` al TOTAL
pero no al desglose de base/cuota; `pos_receipt.xml` lo hereda por XPath y
aplica el mismo signo ahí.

No hay un runner JS en esta suite: se verifica que el XPath de la herencia
realmente ENCUENTRA los nodos nativos (si el XPath no casa con nada, un
`position="replace"` no hace nada y esto lo detecta) y que el resultado lleva
`order_sign *` en los tres sitios — el mismo criterio que aplica el total."""
from pathlib import Path

from lxml import etree

from odoo.tests import TransactionCase, tagged

_NATIVE = (Path(__file__).resolve().parents[3] / "odoo" / "addons" / "point_of_sale" /
          "static" / "src" / "app" / "screens" / "receipt_screen" / "receipt" / "order_receipt.xml")
_OVERRIDE = Path(__file__).resolve().parents[1] / "static" / "src" / "xml" / "pos_receipt.xml"


def _apply_extension_replacements(native_root, override_root):
    """Reimplementación mínima de t-inherit-mode="extension" + position="replace"
    para los <xpath> del override, suficiente para esta comprobación."""
    for xpath_node in override_root.iter("xpath"):
        if xpath_node.get("position") != "replace":
            continue
        targets = native_root.xpath(xpath_node.get("expr"))
        for target in targets:
            parent = target.getparent()
            index = list(parent).index(target)
            parent.remove(target)
            for i, new_child in enumerate(xpath_node):
                parent.insert(index + i, new_child)


@tagged("post_install", "-at_install")
class TestPosReceiptSign(TransactionCase):
    def test_xpath_targets_exist_and_apply_the_sign_everywhere_the_total_does(self):
        self.assertTrue(_NATIVE.is_file(), "no se encuentra order_receipt.xml nativo")
        native = etree.parse(str(_NATIVE)).getroot()
        override = etree.parse(str(_OVERRIDE)).getroot()

        # El total nativo (sin tocar) ya lleva order_sign: es la referencia.
        total_span = native.xpath(
            "//span[contains(@t-esc,'taxTotals.order_sign * taxTotals.order_total')]")
        self.assertTrue(total_span, "el total nativo debería llevar order_sign (referencia)")

        # Antes de aplicar el override, el desglose NO lo lleva (es el bug).
        base_before = native.xpath(
            "//span[contains(@t-esc,'subtotal.base_amount_currency')]")
        self.assertTrue(base_before)
        self.assertNotIn("order_sign", base_before[0].get("t-esc"))

        _apply_extension_replacements(native, override)

        for needle in ("subtotal.base_amount_currency", "tax_group.base_amount_currency",
                      "tax_group.tax_amount_currency"):
            spans = native.xpath("//span[contains(@t-esc,'%s')]" % needle)
            self.assertTrue(spans, "el XPath del override no encontró %s: revisa la expresión" % needle)
            self.assertIn("taxTotals.order_sign *", spans[0].get("t-esc"),
                          "%s no lleva order_sign tras aplicar el override" % needle)

    def test_before_footer_anchor_exists_for_the_marketing_qr_xpath(self):
        """El QR de reseña/web (hallazgo posterior al de arriba) se cuelga con
        position="after" del marcador `before-footer` que la propia plantilla
        nativa deja preparado para esto — ver su comentario "prevents missing
        receipt elements in modules like...". Si un futuro cambio de Odoo le
        quita esa clase, nuestro <xpath> deja de encontrar nada y el override
        no aplica nada (Odoo no avisa): esta prueba lo detecta pronto."""
        native = etree.parse(str(_NATIVE)).getroot()
        override = etree.parse(str(_OVERRIDE)).getroot()
        self.assertTrue(native.xpath("//div[@class='before-footer']"),
                         "la plantilla nativa ya no tiene el marcador before-footer")

        [xpath_node] = [x for x in override.iter("xpath")
                        if x.get("expr") == "//div[@class='before-footer']"]
        self.assertEqual(xpath_node.get("position"), "after")
        self.assertTrue(xpath_node.xpath(".//img[@t-att-src]"),
                         "el bloque insertado debería llevar el <img> del QR")
