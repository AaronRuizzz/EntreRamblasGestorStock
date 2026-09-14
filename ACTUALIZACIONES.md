# Actualizaciones

Cómo llega una versión nueva a la tienda y cómo se aplica sin riesgo.

Dos componentes, con privilegios distintos:

- `EntreRamblas/tools/actualizador.py` — comprueba, descarga y verifica.
  Los comandos `comprobar`/`preparar`/`aceptar`/`rechazar`/`estado` los
  ejecuta el propio proceso de la app (servicio `EntreRamblasOdoo`, cuenta
  LocalService). Estado persistente en
  `<data_dir>/actualizador/estado.json`.
- `EntreRamblas/tools/update_service.py` — el servicio Windows
  **`EntreRamblasActualizador`** (cuenta LocalSystem, arranque **bajo
  demanda**: nunca se inicia solo). Es el único que puede ejecutar
  `actualizador.py aplicar` — ese comando se niega a hacer nada si no lo
  invoca este servicio (comprueba una variable de entorno que solo él pone).
  LocalService solo tiene permiso de *arrancarlo* (`sc sdset`, fijado por el
  instalador), no de pararlo, reconfigurarlo ni borrarlo.

Por qué dos servicios: el que sirve la app corre con permisos limitados y no
puede reemplazar su propio código ni su entorno Python mientras se ejecuta
desde ahí. El aplicador corre con el CPython **vendorizado** del paquete
(`<raíz>\python\python.exe`), no con el venv de la app, así que sí puede
reconstruir ese venv sin bloquearse a sí mismo.

## Publicación (lo hacéis vosotros)

Un `git push` normal **no** actualiza la tienda. Sólo se distribuyen versiones
publicadas expresamente:

1. **Una vez:** `.\publicar\generar-clave-firma.ps1 -Directorio <carpeta segura>`.
   Mueve `firma-privada.pem` a un soporte seguro fuera del repo y del PC de la
   tienda. Copia `firma-publica.pem` a `instalador\firma-publica.pem` y haz
   commit de la **pública**.
2. **Por versión:** sube el número en
   `custom_addons/mi_gestor_stock/__manifest__.py` y añade la migración si hace
   falta (`custom_addons/mi_gestor_stock/migrations/<versión>/`).
3. **Requiere PowerShell 7** (`pwsh`, no `powershell.exe` 5.1):
   `.\publicar\empaquetar.ps1 -Salida ..\dist -Firmar <ruta a firma-privada.pem>`
   — corre las pruebas, prepara el CPython vendorizado y las ruedas offline
   (`python\`, `wheels\`), arma el paquete `EntreRamblas-<versión>.zip` con la
   **unidad de versión completa** (motor Odoo, addons, tools, instalador,
   lanzadores), genera `manifest.json` y `integridad.json` (mapa de hashes del
   paquete) y firma ambos (`.sig`). Comprueba con `check_manifest_encoding.py`
   que el manifiesto se lee sin BOM antes de firmar.
4. Compila el instalador si toca (`instalador\README.md`).
5. Sube `manifest.json`, `manifest.json.sig` y el `.zip` al repositorio de
   releases **`AaronRuizzz/EntreRamblasReleases`** (público, sin secretos ni
   datos de tienda). El actualizador lee `manifest.json` de la raíz de ese repo
   (URL «raw»).
6. La URL de releases viene **precargada** por defecto
   (`mgs.update.releases_url`, `data/mgs_access_data.xml`); solo hace falta
   cambiarla si se usa un repositorio distinto.

## Recepción (en el PC de la tienda)

- Al **arrancar** y **una vez al día** el programa comprueba si hay una versión
  firmada más nueva (`actualizador.py comprobar`). Si la hay y es compatible,
  la **descarga y verifica en el acto** (`preparar`): cuando la dueña acepte,
  el paquete ya está listo, firmado y comprobado en disco.
- Aparece **«Actualización disponible»** en la pantalla de inicio y en
  **Configuración → Actualizaciones**, con la versión y los cambios.
- La dueña pulsa **«Actualizar al cerrar»**. Esto dos cosas: dejar el
  consentimiento por escrito (`aceptacion.json`, vinculado a la versión y al
  SHA-256 exactos del paquete) y **arrancar el servicio aplicador**
  (`sc start EntreRamblasActualizador`). No se instala nada hasta entonces.

## Aplicación segura (`update_service.py` → `actualizador.py aplicar`)

Al arrancar, el servicio aplicador:

0. Comprueba **espacio libre** en el destino de instalación y en el volumen de
   datos (dump + adjuntos) antes de tocar nada. Si no cabe, no empieza.
1. **Re-verifica por su cuenta** la firma Ed25519 del manifiesto guardado en
   el staging, el SHA-256 del paquete ya descargado, la compatibilidad, y que
   exista un consentimiento (`aceptacion.json`) vinculado a **esa versión y
   ese hash exactos**. No se fía de `estado.json`: lo puede escribir el
   proceso menos privilegiado de la app.
2. Entra en **mantenimiento** (parámetro `mgs.maintenance`): la app deja de
   aceptar operaciones nuevas (recepción, eventos, ramos, importación, TPV:
   abrir caja, cobrar, sincronizar ventas). Si hay una sesión de caja abierta,
   ventas sin terminar o trabajos de hardware en curso, se **drena** (espera
   un poco) y, si sigue ocupado, se aplaza y se reintenta cada pocos minutos
   durante hasta 12 horas.
3. **Copia de seguridad** del estado ya definitivo (base + adjuntos), y
   respaldo del código y la versión anteriores. Una vez completo, ese
   respaldo queda **inmutable**: si el proceso se interrumpe y se reanuda
   (el propio servicio, o un reinicio de Windows que lo vuelva a lanzar), NO
   se vuelve a tocar ni se rehace desde cero.
4. Parar el servicio de la app (**verificado**: se espera a que llegue a
   "Detenido" de verdad, no un `sleep` fijo), instalar la **unidad de versión
   completa** (motor, addons, tools, instalador, lanzadores — no solo el
   código del módulo) y **ejecutar migraciones**.
5. Comprobar arranque limpio, acceso a la base y **versión aplicada**.
6. Reabrir **sólo si** todas las comprobaciones pasan, y comprobar que el
   servicio llega de verdad a "En ejecución".

Si algo falla: primero se restaura el **código**, y solo con el código
anterior ya en su sitio se restaura la **base** — nunca al revés, para no
dejar código antiguo sirviendo una base a medio migrar. La base restaurada se
verifica arrancando (con ese código anterior) antes de activarla mediante un
cambio de nombre atómico; la migrada en problemas queda en cuarentena
(`<base>_migrada_<fecha>`), no se borra. Si la propia reversión falla, el
servicio queda **detenido** y el estado en `fallo`: no se finge una
recuperación que no ha ocurrido.

## Estado

`.\venv\Scripts\python.exe tools\actualizador.py estado` — imprime el JSON de
`<data_dir>\actualizador\estado.json`: fase, versión disponible, si está
verificada, si la dueña la aceptó, y el último mensaje. `sc query
EntreRamblasActualizador` dice si el servicio aplicador está trabajando en
ese momento.
