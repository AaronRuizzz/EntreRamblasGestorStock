# Entrega final — ejecución del plan `PlanFinalizarGestor.md`

Rama de trabajo: **`finalizar-entrega`**. Este documento es el rastro vivo de la
ejecución: qué queda hecho en código, qué se verifica con la suite y qué sigue
necesitando una persona (hardware, consola de administrador, gestoría, claves).

Origen del plan: `../PlanFinalizarGestor.md` (fuera del repo).

## Estado por bloque

| Bloque | Tema | Estado |
|---|---|---|
| 1 | Documentación y decisión VeriFactu | ✅ hecho |
| 2 | Acceso solo con contraseña + recuperación | ☐ pendiente |
| 3 | Misma aplicación en todos los equipos | ☐ pendiente |
| 4 | Instalador y actualizaciones firmadas | ☐ pendiente |
| 5 | Pruebas y condiciones de entrega | ☐ pendiente |

## Registro de avance

### Bloque 1 — Documentación ✅

- [x] `FACTURACION.md`: dos avisos nuevos arriba (VeriFactu fuera de la entrega
      por decisión de la dueña; la facturación actual no puede darse por
      validada). Tabla de plazos con la fila de **productores/comercializadores
      de SIF** (29-07-2025, no ampliado por el RDL 15/2025) y el matiz
      «desarrollo propio vs. comercializado». §2 y §4 reescritos. Fuentes AEAT +
      Orden HAC/1177/2024 añadidas.
- [x] `TRASPASO_IA.md` §5.3, `IMPLEMENTACION.md` (bloque 2026-09-06) y
      `README.md` §0bis: corregidos con la misma aclaración y puntero a
      `FACTURACION.md` §2.

### Bloque 2 — Acceso

_(pendiente)_

### Bloque 3 — Misma aplicación

_(pendiente)_

### Bloque 4 — Instalador y actualizaciones

_(pendiente)_

### Bloque 5 — Pruebas

_(pendiente)_

## Lo que necesita una persona (no es código)

- Consola de administrador de Windows: registrar el servicio en el SCM y
  comprobar reinicio, apagado y recuperación ante fallo.
- Hardware físico: lectores, impresora 80 mm, cajón, datáfono, SSD externo.
- Repositorio público `AaronRuizzz/EntreRamblasReleases`: crearlo y subir la
  primera publicación (el pipeline queda hecho, la creación del repo no).
- Clave privada Ed25519 de firma: generarla y custodiarla fuera del repo y del
  PC de la tienda (la herramienta de generación y la verificación quedan hechas).
- Gestoría: régimen fiscal, tipos de IVA por familia, serie de numeración y vía
  de cumplimiento SIF/VeriFactu.
- Catálogo real y datos fiscales de la empresa.
