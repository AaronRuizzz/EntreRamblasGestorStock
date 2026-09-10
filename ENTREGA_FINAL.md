# Entrega final — ejecución del plan `PlanFinalizarGestor.md`

Rama de trabajo: **`finalizar-entrega`**. Este documento es el rastro vivo de la
ejecución: qué queda hecho en código, qué se verifica con la suite y qué sigue
necesitando una persona (hardware, consola de administrador, gestoría, claves).

Origen del plan: `../PlanFinalizarGestor.md` (fuera del repo).

## Estado por bloque

| Bloque | Tema | Estado |
|---|---|---|
| 1 | Documentación y decisión VeriFactu | ✅ hecho |
| 2 | Acceso solo con contraseña + recuperación | ✅ hecho (suite verde) |
| 3 | Misma aplicación en todos los equipos | 🔶 en curso |
| 4 | Instalador y actualizaciones firmadas | ☐ pendiente |
| 5 | Pruebas y condiciones de entrega | 🔶 en curso |

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

### Bloque 2 — Acceso ✅

Ver `ACCESO.md`. Commit `53abe5b`.
- Cuenta de propietaria separada de `base.user_admin` (gestión de tienda, sin
  admin técnico). Instalador + migración `18.0.3.0.0`, historial conservado.
- Login solo contraseña; servidor fija la cuenta; «Entrar»; «He olvidado…».
- Primer acceso con código de activación de un solo uso → contraseña (12+) →
  clave de recuperación (mostrada una vez, sólo se guarda la huella).
- `/mgs/recuperar` con la clave; invalida sesiones; rota la clave; sin correo.
- `mgs.auth.throttle`: límite persistente por (ámbito, IP). CSRF. Nada de
  secretos en el log.
- Configuración → Seguridad (regenerar clave, pide contraseña actual) +
  Restablecimientos de acceso (rastro inmodificable).
- `recuperar-acceso.ps1` (administrador de Windows) para la pérdida total.
- Menú de usuario filtrado al construirse (patch de `UserMenu.getElements`).
- 17 pruebas nuevas.

### Bloque 3 — Misma aplicación 🔶

Hecho:
- **Arranque normal aplica la actualización pendiente**: `start-odoo.ps1` +
  `tools/check_pending_upgrade.py` comparan versión de código vs. aplicada y
  ejecutan `-u` controlado antes de servir; si falla (sesión de caja abierta,
  etc.) aborta, no sirve una base a medio migrar.
- **Integridad del motor**: `start-odoo.ps1` comprueba `git diff --quiet HEAD`
  además del commit.
- **Orden de instalación**: la caja de tienda se crea ANTES de aplicar los
  ajustes comunes del TPV (`data/branding.xml` reordenado).
- **Fallo visible**: `install_database.py` aborta y conserva `.pending` si la
  caja de tienda no se creó (plan contable, etc.).
- **Fuente única del nombre de base**: `bootstrap.ps1` fija `db_name` en la
  config; `start-odoo.ps1` y `reset-catalogo.ps1` lo leen de ahí.
- **Nombre comercial ≠ razón social**: editables por separado en
  Configuración → Dispositivos; un `-u` no pisa el nombre legal.
- **Diagnóstico exportable sin secretos**: `mgs.diagnostic` +
  Configuración → Diagnóstico + `diagnostico.ps1` (versión, motor, config
  común, módulos). Para comparar equipos.
- **Contraseña PostgreSQL por defecto** fuera de `odoo.conf`.
- Mensaje «Ajustes → Punto de venta» corregido.

Pendiente en este bloque:
- Manifiesto de versión formal con migraciones aplicadas (el diagnóstico ya
  cubre versión y estado; falta el histórico de migraciones).
- Refresco explícito de assets/caché tras migración correcta.
- Repaso de manuales (`MANUAL_TIENDA.md`, `INSTALACION.md`) — en curso.
- Checkout limpio del motor «aparte» (va con el instalador, Bloque 4).

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
