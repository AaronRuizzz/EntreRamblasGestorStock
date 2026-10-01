# -*- coding: utf-8 -*-
"""El ticket de venta imprime el logo propio del ticket
(static/src/img/logo-ticket.jpeg), no el emblema de la empresa."""
import base64
import io
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTicketLogo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["mgs.config"]._mgs_get()
        cls.doc = cls.config._mgs_doc()

    def test_logo_is_cropped_to_the_drawing(self):
        image = self.config._mgs_ticket_logo_image()
        self.assertIsNotNone(image)
        self.assertEqual(image.mode, "L")
        # El archivo es de 1160x904 con mucho margen blanco: queda solo el dibujo.
        self.assertLess(image.width, 1100)
        self.assertLess(image.height, 850)
        self.assertGreater(image.width, 900)

    def test_bitmap_is_the_ticket_logo_sized_for_the_paper(self):
        width_bytes, height, data = self.config._mgs_logo_bitmap(self.doc)
        self.assertEqual(len(data), width_bytes * height)
        self.assertEqual(height, self.config._MGS_TICKET_LOGO_MAX_H)
        self.assertLessEqual(width_bytes * 8, self.doc.width * 12 + 7)
        self.assertTrue(any(data), "el logo no puede salir en blanco")
        # Dibujo de líneas: mucho más blanco que negro.
        black = sum(bin(byte).count("1") for byte in data)
        self.assertLess(black, width_bytes * 8 * height * 0.35)

    def test_header_sends_the_image_to_the_printer(self):
        header = self.config._mgs_company_header(self.config._mgs_doc()).to_bytes()
        self.assertIn(b"\x1dv0\x00", header)

    def test_falls_back_to_the_company_logo_without_the_ticket_file(self):
        with patch.object(type(self.config), "_mgs_ticket_logo_image", return_value=None):
            self.assertTrue(self.env.company.logo)
            bitmap = self.config._mgs_logo_bitmap(self.doc)
            self.assertIsNotNone(bitmap)
            self.assertLessEqual(bitmap[1], 220)
            self.env.company.logo = False
            self.assertIsNone(self.config._mgs_logo_bitmap(self.doc))

    def test_pdf_reprint_uses_the_same_logo(self):
        order = self.env["pos.order"].new({"company_id": self.env.company.id})
        logo = order._mgs_receipt_logo()
        from PIL import Image
        image = Image.open(io.BytesIO(base64.b64decode(logo)))
        self.assertEqual(image.size, self.config._mgs_ticket_logo_image().size)
