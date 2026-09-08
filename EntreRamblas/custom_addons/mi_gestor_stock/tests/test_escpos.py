# -*- coding: utf-8 -*-
"""Driver ESC/POS (models/mgs_escpos.py): sin base de datos, es texto y bytes
puros, pero es quien decide si el ticket sale legible y si el cajón se abre."""
from odoo.tests import TransactionCase, tagged

from odoo.addons.mi_gestor_stock.models.mgs_escpos import (
    EscposDocument, ean13_check_digit, encode_text, is_valid_ean13,
)


@tagged("post_install", "-at_install")
class TestEscposEncoding(TransactionCase):
    def test_encode_text_keeps_the_euro_in_cp858(self):
        # cp858 = cp850 + euro: es la página por defecto, pensada justo para esto.
        self.assertEqual(encode_text("3 €", "cp858"), b"3 \xd5")

    def test_encode_text_replaces_the_euro_with_eur_when_the_codepage_lacks_it(self):
        # cp437 (la más pobre, sin acentos ni euro) usa el sustituto de _FALLBACK.
        self.assertEqual(encode_text("3 €", "cp437"), b"3 EUR")

    def test_encode_text_keeps_accented_letters_in_a_codepage_that_has_them(self):
        self.assertEqual(encode_text("café", "cp437"), b"caf\x82")

    def test_encode_text_drops_the_accent_but_keeps_the_letter_when_unsupported(self):
        # Página "ascii": la eñe no existe ni transliterada por _FALLBACK, así
        # que se descompone (NFKD) y se queda solo la "n", sin tilde.
        self.assertEqual(encode_text("mañana", "ascii"), b"manana")

    def test_encode_text_falls_back_to_cp858_for_an_unknown_codepage(self):
        self.assertEqual(encode_text("3 €", "unknown-codepage"), encode_text("3 €", "cp858"))


@tagged("post_install", "-at_install")
class TestEan13(TransactionCase):
    def test_ean13_check_digit_matches_a_known_barcode(self):
        self.assertEqual(ean13_check_digit("400638133393"), "1")

    def test_is_valid_ean13_accepts_the_full_code_with_its_check_digit(self):
        self.assertTrue(is_valid_ean13("4006381333931"))

    def test_is_valid_ean13_rejects_a_wrong_check_digit(self):
        self.assertFalse(is_valid_ean13("4006381333930"))

    def test_is_valid_ean13_rejects_the_wrong_length(self):
        self.assertFalse(is_valid_ean13("123"))

    def test_is_valid_ean13_rejects_letters(self):
        # Una referencia interna alfanumérica no es un EAN-13: va por CODE128.
        self.assertFalse(is_valid_ean13("SKU-ABC12345"))


@tagged("post_install", "-at_install")
class TestEscposLayout(TransactionCase):
    def doc(self, width=10):
        document = EscposDocument(width=width)
        document._buf = bytearray()  # limpia el ESC @ / ESC t del reset() inicial
        return document

    def test_columns_pads_between_label_and_amount_to_fill_the_width(self):
        self.assertEqual(self.doc().columns("Rosa roja", "12,50").to_bytes(), b"Rosa. 12,50\n")

    def test_columns_truncates_a_label_too_long_for_the_paper_with_a_dot(self):
        line = self.doc().columns("Un nombre de producto muy largo de verdad", "1,00").to_bytes()
        self.assertEqual(line, b"Un no. 1,00\n")
        self.assertEqual(len(line), 10 + 1 + 1)  # ancho + "." + "\n"

    def test_wrapped_splits_long_text_into_lines_no_wider_than_the_paper(self):
        text = "Un texto bastante largo que debe partirse en varias lineas de ticket"
        lines = self.doc().wrapped(text).to_bytes().decode("cp858").splitlines()
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(len(line) <= 10 for line in lines))
        # Ninguna palabra se pierde por el camino, aunque cambien los saltos.
        self.assertEqual(" ".join(lines), text)


@tagged("post_install", "-at_install")
class TestEscposCutAndDrawer(TransactionCase):
    def doc(self):
        document = EscposDocument()
        document._buf = bytearray()
        return document

    def test_cut_feeds_the_paper_then_sends_a_partial_cut(self):
        # ESC d 4 (avanza 4 líneas) + GS V 66 0 (corte parcial).
        self.assertEqual(self.doc().cut().to_bytes(), b"\x1bd\x04\x1dVB\x00")

    def test_open_drawer_sends_the_pulse_with_the_default_pin_and_timing(self):
        # ESC p m t1 t2: patilla 2 (m=0), 100 ms / 200 ms en unidades de 2 ms.
        self.assertEqual(self.doc().open_drawer().to_bytes(), b"\x1bp\x002d")

    def test_open_drawer_selects_the_other_pin_and_clamps_timing_to_the_spec_limit(self):
        # pin=1 -> patilla 5 (m=1). Un tiempo absurdo se recorta a 255 (510 ms).
        pulse = self.doc().open_drawer(pin=1, on_ms=10_000, off_ms=10_000).to_bytes()
        self.assertEqual(pulse, b"\x1bp\x01\xff\xff")


@tagged("post_install", "-at_install")
class TestEscposBarcode(TransactionCase):
    def doc(self):
        document = EscposDocument()
        document._buf = bytearray()
        return document

    def test_a_valid_ean13_prints_with_the_ean13_symbology(self):
        # GS k 67 (m=67='C', la EAN13 nativa de la impresora), 12 cifras: el
        # dígito de control lo recalcula la propia impresora.
        payload = self.doc().barcode("4006381333931").to_bytes()
        self.assertIn(b"\x1dkC\x0c400638133393", payload)

    def test_an_alphanumeric_reference_prints_as_code128_instead(self):
        # GS k 73 (m=73='I', CODE128), con el prefijo "{B" del subset B.
        payload = self.doc().barcode("SKU-ABC123").to_bytes()
        self.assertIn(b"\x1dkI\x0c{BSKU-ABC123", payload)

    def test_an_empty_code_prints_nothing(self):
        self.assertEqual(self.doc().barcode("").to_bytes(), b"")
