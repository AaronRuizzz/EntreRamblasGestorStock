# Publicar una versión

Resumen operativo. El detalle de la aplicación segura está en
`../../ACTUALIZACIONES.md`.

## Repositorio de releases

`AaronRuizzz/EntreRamblasReleases` — **público**, dedicado, sin secretos ni
datos de tienda. Contenido de la raíz de la rama `main`:

```
manifest.json
manifest.json.sig
EntreRamblas-<versión>.zip     (motor, addons, tools, instalador,
                                 CPython propio y ruedas: unidad de
                                 versión completa, no solo el módulo)
EntreRamblas-Setup.exe        (opcional; para instalaciones nuevas)
```

El propio `.zip` incluye `integridad.json`/`integridad.json.sig`: el mapa de
hashes que usa el equipo de tienda para verificar el código instalado sin
Git.

> Este repositorio **todavía no existe**: hay que crearlo con la cuenta
> `AaronRuizzz`. La cuenta de GitHub configurada en el PC de desarrollo es otra
> (`UM-Ruben`); decide con cuál se publica antes de automatizar el `push`.

## Pasos

1. `git` en el repo de desarrollo con las pruebas en verde.
2. Sube el número de versión en
   `EntreRamblas/custom_addons/mi_gestor_stock/__manifest__.py`.
   Si hay cambios de datos, añade
   `EntreRamblas/custom_addons/mi_gestor_stock/migrations/<versión>/post-migrate.py`.
3. **Requiere PowerShell 7** (`pwsh`, no `powershell.exe` 5.1 — el script
   trae `#Requires -Version 7` y falla explícitamente si no lo es):
   `.\publicar\empaquetar.ps1 -Salida ..\dist -Firmar "<ruta a firma-privada.pem>"`
4. (Nuevas instalaciones) `.\publicar\empaquetar.ps1` deja `dist\payload\`;
   compila `EntreRamblas-Setup.exe` con Inno Setup (`instalador\README.md`).
5. En un clon de `EntreRamblasReleases`, copia `manifest.json`,
   `manifest.json.sig` y el `.zip` (y el `.exe` si aplica) a la raíz y haz
   `git commit && git push`.
6. Comprueba desde un equipo de tienda:
   `.\venv\Scripts\python.exe tools\actualizador.py comprobar --releases-url <URL raw>`

## Qué NO se publica

Secretos, `odoo.local`, `.odoo_data`, la clave privada de firma, cualquier dato
de tienda (productos, ventas, clientes, NIF). `empaquetar.ps1` ya excluye
`*.secret`, `odoo.local`, `filestore/`, `sessions/`, `*.log`.
