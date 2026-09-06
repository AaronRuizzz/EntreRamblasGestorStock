"""Validación previa de una copia, antes de crear una base de recuperación."""
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath


def validate_archive(filename, allow_legacy=False):
    path = Path(filename).resolve(strict=True)
    checksum_file = Path(str(path) + ".sha256")
    if checksum_file.is_file():
        expected = checksum_file.read_text(encoding="ascii").split()[0]
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if expected != actual:
            raise ValueError("La copia no coincide con su SHA-256; no se restaurará")
    elif not allow_legacy:
        raise ValueError("Falta el archivo .sha256. Para una copia antigua usa --allow-legacy explícitamente")
    with zipfile.ZipFile(path) as archive:
        names = set()
        for entry in archive.infolist():
            name = entry.filename.replace("\\", "/")
            parts = PurePosixPath(name)
            if parts.is_absolute() or ".." in parts.parts or ":" in name or name in names:
                raise ValueError("Ruta no válida o repetida en la copia")
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("La copia contiene un enlace simbólico")
            if name not in ("dump.sql", "manifest.json") and not name.startswith("filestore/"):
                raise ValueError("Contenido no esperado en la copia: " + name)
            names.add(name)
        if not {"dump.sql", "manifest.json"}.issubset(names) or not archive.getinfo("dump.sql").file_size:
            raise ValueError("Falta la base de datos o el manifiesto")
        manifest = json.loads(archive.read("manifest.json"))
        if str(manifest.get("major_version")) != "18.0":
            raise ValueError("Esta herramienta requiere una copia de Odoo 18.0")
        if archive.testzip():
            raise ValueError("La comprobación de integridad ZIP ha fallado")
    return manifest
