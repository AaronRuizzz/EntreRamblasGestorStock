# Entrega final — ejecución del plan `PlanFinalizarGestor.md`

> **Addendum 2026-09-13.** `REVISION_2026-09-10.md` encontró 24 defectos
> (15 P1 bloqueantes) sobre el estado descrito más abajo: instalación limpia
> rota, paquete dependiente del PC del desarrollador, actualizador sin
> componente que lo aplique, CSRF en la confirmación de custodia, menú
> Seguridad inaccesible para la propietaria, secretos en claro, entre otros.
> Los 24 quedan corregidos en código y cubiertos por pruebas (suite verde,
> 225+ pruebas). Lo que sigue pendiente por depender de máquina limpia o
> hardware físico está en `../ACEPTACION.md`, no en este documento (que
> describe una entrega anterior). Detalle del actualizador (ahora con un
> servicio dedicado con privilegios propios) en `../ACTUALIZACIONES.md`.

Rama de trabajo: **`finalizar-entrega`**. Este documento es el rastro vivo de la
ejecución: qué queda hecho en código, qué se verifica con la suite y qué sigue
necesitando una persona (hardware, consola de administrador, gestoría, claves).

Origen del plan: `../PlanFinalizarGestor.md` (fuera del repo).

## Estado por bloque

| Bloque | Tema | Estado |
|---|---|---|
| 1 | Documentación y decisión VeriFactu | ✅ hecho |
| 2 | Acceso solo con contraseña + recuperación | ✅ hecho (suite verde) |
| 3 | Misma aplicación en todos los equipos | ✅ código hecho (suite verde) |
| 4 | Instalador y actualizaciones firmadas | 🔶 código hecho; falta build/repo/claves/servicio |
| 5 | Pruebas y condiciones de entrega | 🔶 suite verde; falta la matriz física |

Commits en `finalizar-entrega`: `14d474d` (docs), `53abe5b` (acceso),
`a00f9ab` (misma app), `2dd898a` (instalador+actualizador), `1f22db0`
(manifiesto+manuales).

## Cómo continuar

1. Revisar la rama y fusionar a `main` si conforme.
2. `publicar\generar-clave-firma.ps1` → clave privada a custodia offline,
   pública a `instalador/firma-publica.pem` (sustituye la de arranque).
3. Crear `AaronRuizzz/EntreRamblasReleases` (decidir cuenta) y fijar
   `mgs.update.releases_url` en cada equipo.
4. Instalar Inno Setup, `publicar\empaquetar.ps1`, compilar el `.exe`,
   probar instalación limpia + reinicio + hardware (plan §5).
5. Consola de administrador: comprobar el servicio en el SCM (el instalador
   lo registra; falta la aceptación de reinicio/apagado/recuperación).
6. Gestoría: régimen, IVA por familia, serie, vía SIF/VeriFactu.

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
- **Integridad del motor**: `tools/verificar_motor.py` (lo usan `start-odoo.ps1`,
  el diagnóstico y `publicar/empaquetar.ps1`) comprueba el commit fijado y que
  ningún fichero **versionado** del motor esté modificado o añadido. La ausencia
  de documentación, empaquetado (`debian/`, `setup/`) o ficheros de datos de
  pruebas **no bloquea el arranque**: no cambia cómo se ejecuta Odoo y en un
  equipo de tienda es normal no tenerlos (queda como aviso). Distingue además las
  «bajas fantasma» del índice (OneDrive evacuando carpetas frías + un `git add`),
  que no son modificaciones reales.
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

Incidencia resuelta (equipo de desarrollo): el checkout de `EntreRamblas/odoo`
tenía ~2200 bajas en el índice (OneDrive + `git add`) y 15 ficheros de prueba
sin extraer por el límite de ruta de Windows (260+ caracteres). `start-odoo.ps1`
rechazaba el arranque con «El motor Odoo tiene ficheros modificados». **Ningún
fichero del motor estaba modificado** (`git diff --diff-filter=ACMRT HEAD` = 0);
era ruido del índice. Hecho: `git -C EntreRamblas/odoo config core.longpaths
true` + `git -C EntreRamblas/odoo restore --staged .` (deshace las bajas
fantasma) y la verificación pasó a `tools/verificar_motor.py`, que ya no bloquea
por documentación/empaquetado ausente. Para dejar el checkout idéntico al
commit: `git -C EntreRamblas/odoo checkout -- .` (restaura `doc/`, `debian/`,
`setup/` y los 15 ficheros de prueba largos).

### Bloque 4 — Instalador y actualizaciones 🔶

Ver `ACTUALIZACIONES.md` y `EntreRamblas/instalador/README.md`.

Hecho (código, probado donde se puede):
- **Firma Ed25519** (`tools/paquete_firma.py`): generar claves, firmar y
  verificar manifiesto. Clave **pública** en `instalador/firma-publica.pem`
  (versionada); la privada NUNCA en el repo.
- **Actualizador** (`tools/actualizador.py`), independiente de Odoo, con
  estado persistente: `comprobar` (descarga manifiesto, **verifica firma**,
  compara versión y compatibilidad — probado, incluido el rechazo de un
  manifiesto manipulado), `preparar` (descarga + SHA-256 + firma), `aplicar`
  (los 7 pasos: preconds → mantenimiento → copia → parar/instalar/migrar →
  comprobar → reabrir; reversión de base y luego código si algo falla).
- **En la app**: pantalla de inicio y Configuración → Actualizaciones muestran
  «Actualización disponible»; botón **«Actualizar al cerrar»**. Cron diario de
  comprobación (`mgs.update._cron_check`, sin `mgs.update.releases_url` no hace
  nada).
- **Instalador Inno Setup** (`instalador/EntreRamblas-Setup.iss` +
  `pasos-instalacion.ps1` + `abrir-app.ps1`): PostgreSQL dedicado (cluster e
  instancia propios, solo local), servicio de Windows con arranque automático
  y dependencia de esa instancia, acceso directo que espera al servicio y abre
  Edge en modo app, comprobación del motor PDF, base nueva sin demo,
  reinstalar/desinstalar conserva base y copias.
- **Pipeline de publicación** (`publicar/empaquetar.ps1`,
  `generar-clave-firma.ps1`, `PUBLICAR.md`): pruebas → árbol de distribución →
  `.zip` + `manifest.json` + firma. Un `git push` normal no publica.

Necesita una persona (fuera del alcance del agente):
- **Crear el repositorio** `AaronRuizzz/EntreRamblasReleases` y decidir con qué
  cuenta se publica (la de `gh` aquí es `UM-Ruben`).
- **Generar la clave privada de firma de verdad**, offline, y custodiarla
  fuera del repo y del PC (ahora hay una de arranque; ver notas al final).
- **Instalar Inno Setup** y **compilar el `.exe`**; probar la instalación de
  cero en una máquina limpia.
- **Registrar el servicio en el SCM** (consola de administrador) y probar
  reinicio, apagado y recuperación ante fallo.
- Firmar el `.exe` con un certificado de firma de código (SmartScreen).

### Bloque 5 — Pruebas 🔶

- Suite Odoo del módulo: **verde** (0 fallos, 0 errores) tras cada bloque.
  Pruebas nuevas: acceso (activación, recuperación, throttle, propietaria sin
  admin técnico, rastro), diagnóstico, firma Ed25519 y ventana de
  actualización.
- `test.ps1` ahora incluye `--db-filter=^mgs_validation$` para HttpCase.
- Pendiente (no es código): matriz física completa del plan §5 — acceso real
  en navegador, reproducibilidad base nueva vs. actualizada, interfaz en dos
  equipos, jornada con hardware, actualización con paquete alterado / disco
  lleno / corte a mitad, restauración real desde SSD.

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

## Nota sobre la clave de firma

Para que el pipeline funcione hoy de punta a punta, hay una pareja de claves
Ed25519 «de arranque»: la **pública** está en
`EntreRamblas/instalador/firma-publica.pem` (versionada); la **privada** está
sólo en el scratchpad de esta sesión (`.../scratchpad/claves-firma/firma-privada.pem`),
NO en el repo. **Antes de publicar nada de verdad**, genera tu propia pareja
con `publicar\generar-clave-firma.ps1` (así nadie más ha visto nunca la
privada) y sustituye `instalador/firma-publica.pem`. Si decides quedarte con la
de arranque, muévela ya a custodia segura offline y bórrala del scratchpad.
