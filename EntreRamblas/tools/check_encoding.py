"""Guardian contra UTF-8 codificado dos veces (mojibake).

Un fichero de texto guardado como UTF-8 y luego reinterpretado y vuelto a
guardar como si fuera cp1252 (el caso tipico: `Set-Content` de PowerShell
5.1 sobre un fichero UTF-8 ya existente) produce texto que sigue siendo
UTF-8 valido -- por eso `str.decode('utf-8')` no lo detecta -- pero cuyo
contenido es basura: "recepcion" se convierte en "recepciÃ³n". Este script
no decodifica: busca directamente los digramas que deja ese patron.

Se ejecuta sobre el addon completo antes de las pruebas (ver test.ps1).
Salida != 0 y lista de ficheros y lineas si encuentra alguno.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "custom_addons"
EXTENSIONS = {".py", ".xml", ".csv", ".js", ".scss", ".po", ".md"}

# Digramas que solo aparecen cuando UTF-8 (acentos, comillas angulares,
# guion medio, flecha) se ha vuelto a codificar como cp1252/latin-1.
# No son texto valido en espanol: si aparecen, el fichero esta mal.
SUSPECT = [
    "Ã¡", "Ã©", "Ã­", "Ã³", "Ãº", "Ã±", "Ã‘",
    "Ã€", "Ã‰", "Ã", "Ã“", "Ãš",
    "Â«", "Â»", "Â·", "Â¿", "Â¡",
    "â€™", "â€œ", "â€", "â€“", "â€”", "â†’",
]


def scan():
    problems = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in EXTENSIONS:
            continue
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            problems.append((path, 0, f"no es UTF-8 valido: {exc}"))
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            hit = next((s for s in SUSPECT if s in line), None)
            if hit:
                problems.append((path, lineno, f"contiene {hit!r}"))
    return problems


def main():
    problems = scan()
    if not problems:
        print("check_encoding: sin mojibake en custom_addons/.")
        return 0
    print(f"check_encoding: {len(problems)} linea(s) con posible UTF-8 doblemente "
          f"codificado:", file=sys.stderr)
    for path, lineno, why in problems:
        rel = path.relative_to(ROOT.parent.parent)
        print(f"  {rel}:{lineno}: {why}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
