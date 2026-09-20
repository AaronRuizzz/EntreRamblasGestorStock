# -*- coding: utf-8 -*-
"""Ticket simplificado: el recibo (pantalla / impresión por navegador) no
enseña base imponible, cuota ni porcentaje de IVA, solo los productos con su
precio final y el TOTAL. `pos_receipt.xml` quita por XPath el bloque nativo
`pos-receipt-taxes` de point_of_sale.OrderReceipt.

No hay un runner JS en esta suite: se verifica que el XPath de la herencia
realmente ENCUENTRA el nodo nativo (si no casa con nada, un `position="replace"`
no hace nada y Odoo no avisa) y que tras aplicarlo no queda ninguna referencia
al desglose, mientras el TOTAL (con `order_sign`, para devoluciones) sigue."""
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
class TestPosReceiptSimplified(TransactionCase):
    def test_tax_block_is_removed_and_total_keeps_its_sign(self):
        self.assertTrue(_NATIVE.is_file(), "no se encuentra order_receipt.xml nativo")
        native = etree.parse(str(_NATIVE)).getroot()
        override = etree.parse(str(_OVERRIDE)).getroot()

        self.assertTrue(native.xpath("//div[contains(@class,'pos-receipt-taxes')]"),
                        "la plantilla nativa ya no tiene el bloque pos-receipt-taxes")
        _apply_extension_replacements(native, override)

        self.assertFalse(native.xpath("//div[contains(@class,'pos-receipt-taxes')]"))
        for needle in ("base_amount_currency", "tax_amount_currency", "tax_group"):
            self.assertFalse(
                native.xpath("//*[contains(@t-esc,'%s') or contains(@t-out,'%s')]" % (needle, needle)),
                "el recibo sigue mostrando %s" % needle)
        total = native.xpath("//span[contains(@t-esc,'taxTotals.order_sign * taxTotals.order_total')]")
        self.assertTrue(total, "el TOTAL debe seguir, con su signo")

    def test_before_footer_anchor_exists_for_the_marketing_qr_xpath(self):
        """El QR de reseña/web se cuelga con position="after" del marcador
        `before-footer` que la propia plantilla nativa deja preparado. Si una
        versión futura de Odoo se lo quita, esta prueba lo detecta pronto."""
        native = etree.parse(str(_NATIVE)).getroot()
        override = etree.parse(str(_OVERRIDE)).getroot()
        self.assertTrue(native.xpath("//div[@class='before-footer']"),
                         "la plantilla nativa ya no tiene el marcador before-footer")

        [xpath_node] = [x for x in override.iter("xpath")
                        if x.get("expr") == "//div[@class='before-footer']"]
        self.assertEqual(xpath_node.get("position"), "after")
        self.assertTrue(xpath_node.xpath(".//img[@t-att-src]"),
                         "el bloque insertado debería llevar el <img> del QR")
