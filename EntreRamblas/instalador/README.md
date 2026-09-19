# Instalador de Gestor Stock Clavel Y Azahar (`Gestor-Stock-Clavel-Y-Azahar-Setup.exe`)

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

1. Instala Inno Setup 6: `winget install JRSoftware.InnoSetup`. Con la
   sesión sin elevar, `ISCC.exe` queda en
   `%LocalAppData%\Programs\Inno Setup 6\ISCC.exe`; elevado (o con el
   instalador oficial), en `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`.
2. Prepara el árbol de distribución (código + venv + motor Odoo +
   wkhtmltopdf) con:

   ```powershell
   .\publicar\empaquetar.ps1 -Salida ..\dist
   ```

3. Compila:

   ```powershell
   & "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" instalador\EntreRamblas-Setup.iss
   ```

   Sale `dist\Gestor-Stock-Clavel-Y-Azahar-Setup.exe`. El archivo `.iss` en sí
   conserva su nombre técnico (`EntreRamblas-Setup.iss`): solo cambia el
   nombre visible del producto y el del `.exe` generado, definidos dentro del
   propio script.

   `publicar-release.ps1` (recomendado en vez de este paso a paso) busca
   `ISCC.exe` solo en ambas rutas automáticamente.

## Configurar la copia en el SSD externo

El servicio de Windows corre con una cuenta de privilegios reducidos
(`NT AUTHORITY\LocalService`), que **no** tiene acceso a un disco externo
recién conectado aunque tu propio usuario lo vea sin problema en el
Explorador. Sin este paso, «Configuración → Copia de seguridad → Carpeta de
réplica en SSD» guarda la ruta sin quejarse, pero la réplica falla con
«El SSD o su carpeta no están disponibles» — el programa no puede
distinguir un disco desconectado de uno sin permiso, así que da el mismo
aviso para los dos casos.

1. Conecta el disco y crea en él la carpeta de copias (por ejemplo,
   `E:\CopiasEntreRamblas`).
2. Abre PowerShell **como administrador** y da acceso al servicio:

   ```powershell
   icacls "E:\CopiasEntreRamblas" /grant "*S-1-5-19:(OI)(CI)M"
   ```

   (`S-1-5-19` es `NT AUTHORITY\LocalService`; `M` es "modificar" — leer,
   escribir y borrar dentro de esa carpeta, nada más. Es el mismo comando
   que usa el instalador para dar acceso al código y a la configuración,
   `tools/windows_service.py`.)
3. Escribe esa misma ruta en «Carpeta de réplica en SSD» y pulsa
   «Probar carpeta del SSD»: confirma en el momento si existe, si se puede
   escribir en ella y si tiene sitio, sin esperar a la próxima copia
   automática.

Si el disco se cambia de puerto USB o de letra de unidad, Windows no vuelve
a pedir permiso (el `icacls` queda en el disco, no en el puerto), pero si se
formatea o se sustituye por otro, hay que repetir el paso 2.

## Lo que queda fuera del alcance de una sesión de agente

- Firmar el `.exe` con un certificado de firma de código (recomendado para que
  SmartScreen no lo bloquee).
- Probar la instalación de cero en una máquina limpia, el reinicio de Windows,
  ambos lectores, impresión, cajón, PDF y copia al SSD.
- Registrar el servicio en el SCM requiere permisos de administrador (el
  instalador los pide con UAC).
