; Instalador de Entre Ramblas - Gestor de stock (Windows 11 x64).
;
; Compilar con Inno Setup 6:
;   1) .\publicar\empaquetar.ps1 -Salida ..\dist   (prepara dist\payload\)
;   2) ISCC.exe instalador\EntreRamblas-Setup.iss
;
; La lógica pesada (PostgreSQL dedicado, servicio, base, acceso directo) la
; hace instalador\pasos-instalacion.ps1, que este .iss ejecuta elevado.

#define AppName "Entre Ramblas - Gestor de stock"
#define AppShort "EntreRamblas"
; empaquetar.ps1 genera dist\version.iss con el AppVersion real (leído del
; __manifest__.py) para que no haya que recordar sincronizarlo a mano; sin
; ese archivo (compilación suelta del .iss) se usa este valor de reserva.
#ifexist "..\..\dist\version.iss"
  #include "..\..\dist\version.iss"
#else
  #define AppVersion "18.0.4.0.0"
#endif
#define Publisher "Entre Ramblas"
; Carpeta con el arbol ya preparado (code + venv + odoo + tools\wkhtmltox).
#ifndef PayloadDir
  #define PayloadDir "..\..\dist\payload"
#endif

[Setup]
AppId={{2814C8DA-2399-450C-A2A1-33C31BDF0616}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={commonpf}\{#AppShort}
DisableProgramGroupPage=yes
DisableDirPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputDir=..\..\dist
OutputBaseFilename=EntreRamblas-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}
; No borrar datos ni copias al desinstalar: viven en {commonappdata}\{#AppShort}
UninstallFilesDir={app}\uninstall

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
; Codigo + entorno + motor Odoo + wkhtmltopdf (todo bajo dist\payload\).
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Dirs]
Name: "{commonappdata}\{#AppShort}"; Permissions: admins-full service-modify

[Run]
; Instalacion propiamente dicha (elevada).
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\instalador\pasos-instalacion.ps1"" -CodeDir ""{app}"" -DataDir ""{commonappdata}\{#AppShort}"""; \
  StatusMsg: "Preparando la base de datos, el servicio y el motor PDF..."; \
  Flags: runhidden waituntilterminated

[UninstallRun]
; Solo se retira el servicio de la aplicacion. NO se toca PostgreSQL, ni la
; base, ni las copias: reinstalar debe reencontrarlas.
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""& { try { Stop-Service EntreRamblasOdoo -ErrorAction SilentlyContinue; & '{app}\venv\Scripts\python.exe' '{app}\tools\windows_service.py' remove --name EntreRamblasOdoo --config '{commonappdata}\{#AppShort}\odoo.local' --database entre_ramblas } catch {} }"""; \
  Flags: runhidden; RunOnceId: "RemoveOdooService"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Messages]
es.WelcomeLabel2=Esto instalará {#AppName} en este equipo.%n%nSe creará una instancia de base de datos propia y un servicio de Windows. Los datos y las copias de seguridad se guardan en {commonappdata}\{#AppShort} y NO se borran al reinstalar o desinstalar.
