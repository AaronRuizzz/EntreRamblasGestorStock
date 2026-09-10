# Instalador `EntreRamblas-Setup.exe`

Genera un único ejecutable para Windows 11 x64 con Inno Setup. La dueña **no
necesita** Git, ni clonar repositorios, ni escribir comandos.

## Qué hace la instalación

- Copia el **código** a `%ProgramFiles%\EntreRamblas` y deja **configuración,
  datos y copias** en `%ProgramData%\EntreRamblas` (fuera de OneDrive), con
  permisos adecuados.
- Provisiona una **instancia PostgreSQL dedicada** a la aplicación (puerto
  local propio, sólo accesible desde el equipo). No toca otras instalaciones
  de PostgreSQL.
- Registra el **servicio de Windows** con arranque automático y dependencia de
  esa instancia PostgreSQL.
- Crea un **acceso directo** que espera a que el servicio esté disponible y
  abre la aplicación en una ventana de Edge (`--app`). Sin consolas.
- Comprueba el **motor PDF** (wkhtmltopdf) y genera un informe de prueba.
- Crea una **base nueva sin demo**; deja pendiente el primer acceso (código de
  activación en `%ProgramData%\EntreRamblas\<base>-activacion.txt`).
- **Reinstalar o desinstalar NO borra** la base ni las copias.

## Cómo compilarlo (en el PC de desarrollo)

1. Instala [Inno Setup 6](https://jrsoftware.org/isdl.php).
2. Prepara el árbol de distribución (código + venv + motor Odoo +
   wkhtmltopdf) con:

   ```powershell
   .\publicar\empaquetar.ps1 -Salida ..\dist
   ```

3. Compila:

   ```powershell
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalador\EntreRamblas-Setup.iss
   ```

   Sale `dist\EntreRamblas-Setup.exe`.

## Lo que queda fuera del alcance de una sesión de agente

- Firmar el `.exe` con un certificado de firma de código (recomendado para que
  SmartScreen no lo bloquee).
- Probar la instalación de cero en una máquina limpia, el reinicio de Windows,
  ambos lectores, impresión, cajón, PDF y copia al SSD.
- Registrar el servicio en el SCM requiere permisos de administrador (el
  instalador los pide con UAC).
