# Publicar una versión

Resumen operativo. El detalle de la aplicación segura está en
`../../ACTUALIZACIONES.md`.

## Repositorio de releases

`AaronRuizzz/EntreRamblasReleases` — **público**, dedicado, sin secretos ni
datos de tienda. La rama `main` contiene **solo**:

```
manifest.json
manifest.json.sig
```

El `.zip` del paquete (motor Odoo, addons, tools, instalador, CPython propio
y ruedas: unidad de versión completa, no solo el módulo) y el
`Gestor-Stock-Clavel-Y-Azahar-Setup.exe` (opcional, para instalaciones
nuevas) **no van al árbol git**: GitHub bloquea archivos normales de más de
100 MiB y el paquete completo los supera con holgura. Van como *release
assets* de una release de GitHub (hasta 2 GiB cada uno), en
`https://github.com/AaronRuizzz/EntreRamblasReleases/releases/download/v<versión>/<archivo>`
— una URL predecible por convención (tag `v<versión>`, mismo nombre de
archivo), que `empaquetar.ps1` ya calcula y deja en `manifest.json` como
`download_url`.

El propio `.zip` incluye `integridad.json`/`integridad.json.sig`: el mapa de
hashes que usa el equipo de tienda para verificar el código instalado sin
Git.

> Este repositorio **todavía no existe**: hay que crearlo con la cuenta
> `AaronRuizzz`. La cuenta de GitHub configurada en el PC de desarrollo puede
> ser otra; inicia sesión con `gh auth login` (o `gh auth switch`) como
> `AaronRuizzz` antes de publicar.

## Publicar (automatizado)

```
.\publicar\publicar-release.ps1 -Firmar "<ruta a firma-privada.pem>"
```

Hace, en este orden exacto — y publica `manifest.json` el **último**, para
que ningún cliente vea nunca un manifiesto que apunte a una release que
todavía no existe:

1. Comprueba árbol git limpio y que la versión sea mayor que la última
   publicada.
2. `empaquetar.ps1` (pruebas, paquete, firma, `download_url` ya calculado).
3. Compila el instalador con Inno Setup (`instalador\README.md`).
4. Crea la release en GitHub (`gh release create v<versión>`) y sube el
   `.zip` y el `.exe` como assets.
5. Comprueba que esos assets responden antes de seguir.
6. Clona/actualiza `EntreRamblasReleases`, copia `manifest.json` +
   `manifest.json.sig` a la raíz, y hace `git commit && git push` a `main`.

Requiere `gh` (GitHub CLI) autenticado como `AaronRuizzz` — el script
comprueba `gh auth status` antes de tocar nada y aborta con un mensaje claro
si no lo está.

## Pasos manuales (si hace falta publicar sin el script)

1. `git` en el repo de desarrollo con las pruebas en verde.
2. Sube el número de versión en
   `EntreRamblas/custom_addons/mi_gestor_stock/__manifest__.py`.
   Si hay cambios de datos, añade
   `EntreRamblas/custom_addons/mi_gestor_stock/migrations/<versión>/post-migrate.py`.
3. **Requiere PowerShell 7** (`pwsh`, no `powershell.exe` 5.1 — el script
   trae `#Requires -Version 7` y falla explícitamente si no lo es):
   `.\publicar\empaquetar.ps1 -Salida ..\dist -Firmar "<ruta a firma-privada.pem>"`
4. Compila `Gestor-Stock-Clavel-Y-Azahar-Setup.exe` con Inno Setup
   (`instalador\README.md`), usando `dist\payload\` y `dist\version.iss`
   que acaba de dejar `empaquetar.ps1`.
5. `gh release create v<versión> dist\Gestor-Stock-Clavel-Y-Azahar-<versión>.zip dist\Gestor-Stock-Clavel-Y-Azahar-Setup.exe --repo AaronRuizzz/EntreRamblasReleases --title <versión>`
6. Solo entonces, en un clon de `EntreRamblasReleases`: copia
   `manifest.json` y `manifest.json.sig` a la raíz y haz
   `git commit && git push`.
7. Comprueba desde un equipo de tienda:
   `.\venv\Scripts\python.exe tools\actualizador.py comprobar --releases-url <URL raw>`

## Qué NO se publica

Secretos, `odoo.local`, `.odoo_data`, la clave privada de firma, cualquier dato
de tienda (productos, ventas, clientes, NIF). `empaquetar.ps1` ya excluye
`*.secret`, `odoo.local`, `filestore/`, `sessions/`, `*.log`.
