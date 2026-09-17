# -*- coding: utf-8 -*-
"""Driver ESC/POS puro (sin dependencias externas).

ESC/POS es el lenguaje que entiende la impresora termica Approx
appPOS80AM-USBLAN (y practicamente cualquier termica de 80 mm): una secuencia
de bytes con el texto mezclado con comandos de control. Aqui se construye esa
secuencia y se envia por uno de los tres transportes posibles:

  - "network": socket TCP al puerto 9100 (la boca LAN de la impresora).
  - "windows": cola de impresion de Windows en modo RAW (necesita pywin32).
  - "path"   : se escribe en una ruta: recurso compartido (\\\\PC\\POS80), un
               puerto (COM1, LPT1) o un fichero, util para probar sin hardware.

El cajon portamonedas Approx CASH01 NO recibe datos: cuelga del RJ11 de la
impresora y se abre con el pulso electrico que dispara el comando ESC p. Por
eso "abrir cajon" es, tecnicamente, imprimir 5 bytes.

Referencia: especificacion ESC/POS de Epson, que es la que clonan las
impresoras genericas de 80 mm.
"""
import logging
import socket
import unicodedata

_logger = logging.getLogger(__name__)

ESC = b"\x1b"
GS = b"\x1d"

# Paginas de codigos: codec de Python -> numero de pagina ESC/POS (comando
# ESC t n). cp858 = cp850 + simbolo del euro, que es lo que interesa aqui; si
# la impresora sacara caracteres raros se cambia desde la pantalla de
# Configuracion > Dispositivos, sin tocar codigo.
CODEPAGES = {
    "cp858": 19,
    "cp850": 2,
    "cp437": 0,
    "cp1252": 16,
    "ascii": 0,
}

# Anchura util en caracteres con la fuente A (12x24) segun el ancho del papel.
WIDTH_BY_PAPER = {"80": 48, "58": 32}

# Sustitutos para los simbolos que no existen en las paginas mas pobres
# (cp437 no tiene euro, y en modo "ascii" no hay nada de esto).
_FALLBACK = {
    "€": "EUR",
    "…": "...",
    "«": '"',
    "»": '"',
    "º": "o",
    "ª": "a",
    "·": "-",
    "—": "-",
    "–": "-",
}


def encode_text(text, codepage="cp858"):
    """Codifica respetando la pagina de codigos de la impresora.

    Los caracteres que esa pagina no tiene (una eñe en cp437, un euro en
    cp437, un emoji...) se transliteran en vez de reventar la impresion.
    """
    codec = codepage if codepage in CODEPAGES else "cp858"
    out = bytearray()
    for char in text:
        try:
            out += char.encode(codec)
            continue
        except UnicodeEncodeError:
            pass
        replacement = _FALLBACK.get(char)
        if replacement:
            out += replacement.encode(codec, "replace")
            continue
        # "á" -> "a" + tilde combinante: se queda la letra y se tira el acento.
        plain = unicodedata.normalize("NFKD", char).encode(codec, "ignore")
        if plain:
            out += plain
        elif not unicodedata.combining(char):
            out += b"?"
    return bytes(out)


def ean13_check_digit(code12):
    """Digito de control de un EAN-13 a partir de sus 12 primeras cifras."""
    total = sum((3 if i % 2 else 1) * int(digit) for i, digit in enumerate(code12))
    return str((10 - total % 10) % 10)


def is_valid_ean13(code):
    code = (code or "").strip()
    return len(code) == 13 and code.isdigit() and ean13_check_digit(code[:12]) == code[12]


class EscposDocument:
    """Acumula comandos ESC/POS y los devuelve como bytes con to_bytes()."""

    def __init__(self, width=48, codepage="cp858"):
        self.width = width or 48
        self.codepage = codepage if codepage in CODEPAGES else "cp858"
        self._buf = bytearray()
        self.reset()

    # -- primitivas -------------------------------------------------------
    def raw(self, data):
        self._buf += data
        return self

    def reset(self):
        """ESC @ (inicializa) + ESC t n (fija la pagina de codigos)."""
        return self.raw(ESC + b"@").raw(ESC + b"t" + bytes([CODEPAGES[self.codepage]]))

    def align(self, mode="left"):
        return self.raw(ESC + b"a" + bytes([{"left": 0, "center": 1, "right": 2}[mode]]))

    def bold(self, on=True):
        return self.raw(ESC + b"E" + bytes([1 if on else 0]))

    def size(self, width=1, height=1):
        """GS ! n: multiplica el tamaño del caracter (1 a 8)."""
        n = ((max(1, min(width, 8)) - 1) << 4) | (max(1, min(height, 8)) - 1)
        return self.raw(GS + b"!" + bytes([n]))

    def text(self, value=""):
        return self.raw(encode_text(str(value), self.codepage))

    def ln(self, value="", count=1):
        return self.text(value).raw(b"\n" * count)

    def feed(self, lines=1):
        return self.raw(ESC + b"d" + bytes([max(0, min(lines, 255))]))

    def rule(self, char="-"):
        return self.ln(char * self.width)

    # -- composicion de lineas -------------------------------------------
    def columns(self, left, right, indent=0):
        """Una linea con texto a la izquierda e importe pegado a la derecha."""
        left, right = str(left), str(right)
        room = self.width - len(right) - indent
        if len(left) > room:
            left = left[: max(0, room - 1)] + "."
        pad = self.width - indent - len(left) - len(right)
        return self.ln(" " * indent + left + " " * max(1, pad) + right)

    def wrapped(self, value, indent=0):
        """Parte un texto largo en varias lineas del ancho del papel.

        Una palabra suelta mas larga que el hueco disponible (una URL, una
        referencia larga...) se trocea a la fuerza en vez de truncarse: antes
        se perdia el resto de la palabra sin avisar.
        """
        room = max(8, self.width - indent)
        line = ""
        for word in str(value).split():
            while len(word) > room:
                if line:
                    self.ln(" " * indent + line)
                    line = ""
                self.ln(" " * indent + word[:room])
                word = word[room:]
            candidate = ("%s %s" % (line, word)).strip()
            if len(candidate) > room:
                if line:
                    self.ln(" " * indent + line)
                line = word
            else:
                line = candidate
        if line:
            self.ln(" " * indent + line)
        return self

    def title(self, value):
        return (
            self.align("center").bold(True).size(2, 2)
            .ln(value)
            .size().bold(False).align("left")
        )

    # -- codigos de barras / QR ------------------------------------------
    def barcode(self, code, height=64, width=2, hri=True):
        """Imprime el codigo. La impresora dibuja las barras: solo se manda el texto.

        EAN-13 valido -> simbologia EAN13 (m=67), que es lo que llevan los
        productos de proveedor. Cualquier otra cosa (codigos internos con
        letras, referencias) -> CODE128 (m=73), que admite alfanumerico.
        """
        code = (code or "").strip()
        if not code:
            return self
        self.raw(GS + b"h" + bytes([max(1, min(height, 255))]))
        self.raw(GS + b"w" + bytes([max(2, min(width, 6))]))
        self.raw(GS + b"H" + bytes([2 if hri else 0]))  # texto legible debajo
        self.raw(GS + b"f" + b"\x00")
        if is_valid_ean13(code):
            # Se mandan 12 cifras: el digito de control lo calcula la impresora
            # (y sale el mismo, porque ya lo hemos validado).
            data = code[:12].encode("ascii")
            self.raw(GS + b"k" + bytes([67, len(data)]) + data)
        else:
            data = b"{B" + encode_text(code, "ascii")
            self.raw(GS + b"k" + bytes([73, len(data)]) + data)
        return self.raw(b"\n")

    def qr(self, data, module=6):
        """QR nativo de la impresora (GS ( k)."""
        payload = encode_text(str(data), "ascii")
        if not payload:
            return self
        self.raw(GS + b"(k\x04\x00\x31\x41\x32\x00")                     # modelo 2
        self.raw(GS + b"(k\x03\x00\x31\x43" + bytes([max(1, min(module, 16))]))
        self.raw(GS + b"(k\x03\x00\x31\x45\x31")                         # correccion M
        length = len(payload) + 3
        self.raw(GS + b"(k" + bytes([length % 256, length // 256]) + b"\x31\x50\x30" + payload)
        return self.raw(GS + b"(k\x03\x00\x31\x51\x30")                  # imprimir

    def raster_image(self, width_bytes, height, data):
        """GS v 0: imprime un mapa de bits ya convertido a 1 bit por pixel
        (1 = punto negro), fila a fila, `width_bytes` bytes por fila.

        La conversion de una imagen (PNG del logo) a estos bytes vive fuera
        de este modulo, en mgs_config.py, con Pillow: este fichero sigue
        "puro" (ver docstring de arriba), solo entiende bytes ya preparados.
        """
        if width_bytes <= 0 or height <= 0 or len(data) != width_bytes * height:
            return self
        header = GS + b"v0" + bytes([0]) + bytes([
            width_bytes & 0xFF, (width_bytes >> 8) & 0xFF,
            height & 0xFF, (height >> 8) & 0xFF,
        ])
        return self.raw(header + bytes(data))

    # -- final del ticket -------------------------------------------------
    def cut(self, feed=4):
        """Avanza el papel y hace corte parcial (GS V 66 n)."""
        return self.feed(feed).raw(GS + b"V" + bytes([66, 0]))

    def open_drawer(self, pin=0, on_ms=100, off_ms=200):
        """ESC p m t1 t2: pulso de 12 V por el RJ11 hacia el cajon.

        `pin` 0 = patilla 2 (lo estandar), 1 = patilla 5. Los tiempos van en
        unidades de 2 ms y la especificacion los limita a 255 (510 ms).
        """
        t1 = max(1, min(int(on_ms / 2), 255))
        t2 = max(1, min(int(off_ms / 2), 255))
        return self.raw(ESC + b"p" + bytes([1 if pin else 0, t1, t2]))

    def to_bytes(self):
        return bytes(self._buf)


# ----------------------------------------------------------------------
# Transportes
# ----------------------------------------------------------------------
class PrinterError(Exception):
    """Fallo al hablar con la impresora (el modelo lo traduce a UserError)."""


def send_network(payload, host, port=9100, timeout=5):
    if not host:
        raise PrinterError("Falta la dirección IP de la impresora.")
    try:
        with socket.create_connection((host, int(port or 9100)), timeout=timeout) as sock:
            sock.sendall(payload)
    except OSError as err:
        raise PrinterError(
            "No se pudo conectar con la impresora en %s:%s (%s)." % (host, port, err)
        ) from err


def send_windows(payload, printer_name, doc_name="Ticket"):
    if not printer_name:
        raise PrinterError("Falta el nombre de la impresora de Windows.")
    try:
        import win32print  # dependencia opcional, solo Windows
    except ImportError as err:
        raise PrinterError(
            "Para imprimir por la cola de Windows hace falta el paquete pywin32 "
            "(venv\\Scripts\\pip install pywin32), o usa el modo de conexión "
            "«Red (TCP 9100)»."
        ) from err
    try:
        handle = win32print.OpenPrinter(printer_name)
    except Exception as err:  # noqa: BLE001 - la API lanza pywintypes.error
        raise PrinterError(
            "Windows no encuentra la impresora «%s» (%s)." % (printer_name, err)
        ) from err
    try:
        # "RAW" = los bytes pasan tal cual al puerto, sin que el driver los
        # reinterprete: es lo que necesita ESC/POS.
        job = win32print.StartDocPrinter(handle, 1, (doc_name, None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, payload)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
        _logger.debug("mi_gestor_stock: trabajo %s enviado a %s", job, printer_name)
    except Exception as err:  # noqa: BLE001
        raise PrinterError("Error al imprimir en «%s»: %s" % (printer_name, err)) from err
    finally:
        win32print.ClosePrinter(handle)


def send_path(payload, path):
    if not path:
        raise PrinterError("Falta la ruta o el puerto de la impresora.")
    try:
        with open(path, "wb") as port:
            port.write(payload)
    except OSError as err:
        raise PrinterError("No se pudo escribir en «%s»: %s" % (path, err)) from err
