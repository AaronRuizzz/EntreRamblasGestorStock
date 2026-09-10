# -*- coding: utf-8 -*-
"""Firma y verificación Ed25519 de los paquetes de actualización.

- La **clave privada** se genera una sola vez, sin conexión, y se guarda
  FUERA del repositorio y del PC de la tienda.
- La **clave pública** viaja con la aplicación (`instalador/firma-publica.pem`)
  y es lo único que necesita el actualizador para comprobar un paquete.
- Cada publicación firma dos cosas: el `manifest.json` (metadatos) y, dentro
  de él, el SHA-256 del `.zip`. Así una firma válida del manifiesto garantiza
  también el contenido del paquete.

Uso:
    python tools/paquete_firma.py generar-claves --directorio <carpeta segura>
    python tools/paquete_firma.py firmar   --archivo manifest.json --clave firma-privada.pem
    python tools/paquete_firma.py verificar --archivo manifest.json --firma manifest.json.sig \
                                            --clave instalador/firma-publica.pem
"""
import argparse
import base64
import hashlib
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)
from cryptography.exceptions import InvalidSignature


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_private(path):
    return serialization.load_pem_private_key(Path(path).read_bytes(), password=None)


def load_public(path):
    return serialization.load_pem_public_key(Path(path).read_bytes())


def sign_bytes(private_key, data):
    return base64.b64encode(private_key.sign(data)).decode("ascii")


def verify_bytes(public_key, data, signature_b64):
    try:
        public_key.verify(base64.b64decode(signature_b64), data)
        return True
    except (InvalidSignature, ValueError):
        return False


# --------------------------------------------------------------------------- CLI
def _generar_claves(args):
    directory = Path(args.directorio)
    directory.mkdir(parents=True, exist_ok=True)
    priv_path = directory / "firma-privada.pem"
    pub_path = directory / "firma-publica.pem"
    if priv_path.exists() or pub_path.exists():
        raise SystemExit("Ya hay claves en esa carpeta; no se sobrescriben.")
    private_key = Ed25519PrivateKey.generate()
    priv_path.write_bytes(private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    pub_path.write_bytes(private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo))
    print("Clave privada:", priv_path)
    print("Clave pública:", pub_path)
    print()
    print("IMPORTANTE:")
    print(" - Mueve firma-privada.pem a un soporte seguro FUERA del repo y del PC")
    print("   de la tienda. Sin ella no se pueden publicar actualizaciones; con")
    print("   ella, cualquiera puede.")
    print(" - Copia firma-publica.pem a instalador/firma-publica.pem y publícala.")


def _firmar(args):
    private_key = load_private(args.clave)
    data = Path(args.archivo).read_bytes()
    sig_path = Path(args.firma or (args.archivo + ".sig"))
    sig_path.write_text(sign_bytes(private_key, data) + "\n", encoding="ascii")
    print("Firma escrita en", sig_path)


def _verificar(args):
    public_key = load_public(args.clave)
    data = Path(args.archivo).read_bytes()
    signature = Path(args.firma).read_text(encoding="ascii").strip()
    ok = verify_bytes(public_key, data, signature)
    print("VÁLIDA" if ok else "NO VÁLIDA")
    sys.exit(0 if ok else 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("generar-claves")
    p.add_argument("--directorio", required=True)
    p.set_defaults(func=_generar_claves)

    p = sub.add_parser("firmar")
    p.add_argument("--archivo", required=True)
    p.add_argument("--clave", required=True)
    p.add_argument("--firma")
    p.set_defaults(func=_firmar)

    p = sub.add_parser("verificar")
    p.add_argument("--archivo", required=True)
    p.add_argument("--firma", required=True)
    p.add_argument("--clave", required=True)
    p.set_defaults(func=_verificar)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
