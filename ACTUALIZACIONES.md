# Actualizaciones

Cómo llega una versión nueva a la tienda y cómo se aplica sin riesgo. El
actualizador es `EntreRamblas/tools/actualizador.py` (un proceso **aparte** de
Odoo, con estado propio en `<data_dir>/actualizador/estado.json`).

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
3. `.\publicar\empaquetar.ps1 -Salida ..\dist -Firmar <ruta a firma-privada.pem>`
   — corre las pruebas, arma el paquete `EntreRamblas-<versión>.zip`, genera
   `manifest.json` y lo firma (`manifest.json.sig`).
4. Compila el instalador si toca (`instalador\README.md`).
5. Sube `manifest.json`, `manifest.json.sig` y el `.zip` al repositorio de
   releases **`AaronRuizzz/EntreRamblasReleases`** (público, sin secretos ni
   datos de tienda). El actualizador lee `manifest.json` de la raíz de ese repo
   (URL «raw»).
6. En cada equipo de tienda, una sola vez, configura la URL de releases:
   Ajusta el parámetro `mgs.update.releases_url` (por consola) a la URL raw del
   repo, p. ej.
   `https://raw.githubusercontent.com/AaronRuizzz/EntreRamblasReleases/main`.

## Recepción (en el PC de la tienda)

- Al **arrancar** y **una vez al día** el programa comprueba si hay una versión
  firmada más nueva (`actualizador.py comprobar`). Sin internet, sigue
  funcionando y vuelve a mirar más adelante.
- Si la hay, aparece **«Actualización disponible»** en la pantalla de inicio y
  en **Configuración → Actualizaciones**, con la versión y los cambios.
- La dueña pulsa **«Actualizar al cerrar»**. No se instala nada hasta entonces.

## Aplicación segura (7 pasos, `actualizador.py aplicar`)

1. Descargar y comprobar **firma, integridad (SHA-256) y compatibilidad**
   antes de detener nada.
2. Esperar a que **no haya** sesión de caja abierta, ventas del TPV sin
   terminar ni impresiones/aperturas en curso. Si las hay, se **aplaza** y se
   explica por qué.
3. Entrar en **mantenimiento** (parámetro `mgs.maintenance`): no se aceptan
   operaciones nuevas.
4. **Copia de seguridad** de la base y adjuntos, verificada; se guarda también
   el código y la versión anteriores.
5. Parar el servicio, instalar la versión y **ejecutar migraciones**.
6. Comprobar arranque limpio, acceso a la base y **versión aplicada**.
7. Reabrir **sólo si** todas las comprobaciones pasan.

Si una migración falla: se **restaura la base** desde la copia y **luego** el
código anterior (nunca código antiguo sobre una base ya migrada), se sale de
mantenimiento y el estado queda en `fallo` con el motivo. El estado es
persistente: un reinicio a mitad de la instalación se recupera o revierte.

## Estado

`.\venv\Scripts\python.exe tools\actualizador.py estado` — imprime el JSON de
`<data_dir>\actualizador\estado.json`: fase, versión disponible, si está
verificada, si la dueña la aceptó, y el último mensaje.
