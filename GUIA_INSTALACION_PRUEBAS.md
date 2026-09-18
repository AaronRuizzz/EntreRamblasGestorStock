# Guía paso a paso: instalar y probar Gestor Stock Clavel Y Azahar

Instalación desde el paquete publicado (`Gestor-Stock-Clavel-Y-Azahar-Setup.exe`)
y pruebas funcionales sobre esa instalación. Para el procedimiento manual de
desarrollo/mantenimiento, ver [INSTALACION.md](INSTALACION.md).

## 0. Qué hay publicado ahora mismo

- Repositorio de releases: [AaronRuizzz/EntreRamblasReleases](https://github.com/AaronRuizzz/EntreRamblasReleases)
  (público, sin secretos ni datos de tienda).
- Última versión publicada: **v18.0.6.0.2** (2026-09-18), con dos assets en la
  release:
  - `Gestor-Stock-Clavel-Y-Azahar-Setup.exe` — instalador para el PC de la
    tienda (instalación nueva).
  - `Gestor-Stock-Clavel-Y-Azahar-18.0.6.0.2.zip` — paquete que usa el
    actualizador interno; no hace falta para una instalación nueva.
- `manifest.json` en la raíz del repo apunta a esa versión y está firmado
  (`manifest.json.sig`); el actualizador de cada tienda lo verifica antes de
  aceptar la versión.

**Importante:** según [ACEPTACION.md](ACEPTACION.md), ningún punto de la
aceptación real (instalación en máquina limpia, ciclo del servicio Windows,
actualización de extremo a extremo, hardware físico) está marcado todavía. Esta
guía es la oportunidad de ir marcándolos: no dar por «validado en producción»
solo porque el `.exe` existe.

### ⚠️ La firma de esta release no verifica contra la clave del repo

Comprobado el 2026-09-18: el `manifest.json` / `manifest.json.sig` publicados
en `AaronRuizzz/EntreRamblasReleases` para v18.0.6.0.2 **no** verifican contra
`EntreRamblas/instalador/firma-publica.pem` (la pública que sigue en este repo
desde el commit `2dd898a`, la «de arranque» descrita en
[ENTREGA_FINAL.md](ENTREGA_FINAL.md)):

```powershell
python EntreRamblas/tools/paquete_firma.py verificar `
  --archivo manifest.json --firma manifest.json.sig `
  --clave EntreRamblas/instalador/firma-publica.pem
# → NO VÁLIDA
```

(Confirmado que la herramienta funciona: firmando el mismo `manifest.json` con
una clave de prueba y verificando con su pública sí da `VÁLIDA`.)

Esto significa que quien publicó esta release usó una clave privada distinta
de la que corresponde a la pública versionada aquí — probablemente generó ya
la clave «real» con `generar-clave-firma.ps1` pero no actualizó/comiteó su
pública en `instalador/firma-publica.pem`. Consecuencia práctica: cualquier
`.exe` compilado desde este checkout llevará la clave pública equivocada
embebida y su actualizador **rechazará** esta release y las siguientes
firmadas con la clave real, sin avisar más que con un estado de «firma
inválida». El §1 de [ACEPTACION.md](ACEPTACION.md) (manifiesto firmado,
`verificar` → `VÁLIDA`) no está cerrado para esta release tal y como está el
repo ahora.

**Antes de publicar nada de verdad (§7-8 de esta guía) o de probar el §5 de
[ACEPTACION.md](ACEPTACION.md)**: averiguar qué clave privada se usó para
publicar, comprobar que su pública coincide con `instalador/firma-publica.pem`,
y si no coincide, actualizar ese fichero (o regenerar la clave y volver a
publicar) antes de compilar el instalador que se vaya a instalar en la tienda.

**Pendiente ahora mismo (2026-09-18):** decidido preguntar primero a Aaron
(`AaronRuizzz`) qué clave privada usó para firmar la release `v18.0.6.0.2` y
dónde la tiene guardada. Si la localiza, solo hace falta sacar su pública y
sustituir `instalador/firma-publica.pem` (no hay que republicar la release de
hoy). Si no aparece, la alternativa es generar una clave nueva con
`generar-clave-firma.ps1`, custodiarla bien y volver a publicar firmado con
ella.

## 1. Descargar el instalador

En el equipo de pruebas — idealmente uno **limpio**, sin Git ni Python
instalados, para validar también el punto 2 de la aceptación:

```powershell
Invoke-WebRequest -Uri "https://github.com/AaronRuizzz/EntreRamblasReleases/releases/download/v18.0.6.0.2/Gestor-Stock-Clavel-Y-Azahar-Setup.exe" -OutFile "$env:USERPROFILE\Downloads\Gestor-Stock-Clavel-Y-Azahar-Setup.exe"
```

## 2. Ejecutar el instalador

1. Doble clic en `Gestor-Stock-Clavel-Y-Azahar-Setup.exe`. Aceptar el UAC.
2. El instalador hace todo solo, sin necesitar conexión a internet: copia el
   código a `%ProgramFiles%\EntreRamblas`, deja configuración y datos en
   `%ProgramData%\EntreRamblas`, provisiona un PostgreSQL propio (puerto local
   dedicado, sin tocar otras instalaciones), registra el servicio
   `EntreRamblasOdoo`, crea el acceso directo y comprueba el motor PDF.
3. Al terminar, **no abrir la app todavía** — primero verificar la instalación
   (paso 3).

## 3. Verificar la instalación

```powershell
Get-Service EntreRamblasOdoo, EntreRamblasActualizador
sc.exe qc EntreRamblasActualizador
Test-Path "$env:ProgramData\EntreRamblas\entre_ramblas-activacion.txt"
```

- `EntreRamblasOdoo` → **Running**.
- `EntreRamblasActualizador` → `START_TYPE: DEMAND_START` (no debe arrancar solo).
- Debe existir el fichero de activación con el código de un solo uso.

Esto cubre el §2 de [ACEPTACION.md](ACEPTACION.md).

## 4. Primer acceso (navegador, sin consola)

1. Usar el acceso directo del escritorio: espera a que el servicio esté listo
   y abre Edge en modo app en `/mgs/primer-acceso`.
2. Introducir el código de `entre_ramblas-activacion.txt`.
3. Elegir una contraseña de **12+ caracteres**.
4. Apuntar la **clave de recuperación** que se muestra una sola vez (guardarla
   fuera del PC; no se vuelve a mostrar).
5. Marcar la casilla de «ya la he guardado» y entrar.

Detalle completo en [ACCESO.md](ACCESO.md). Probar también «he olvidado mi
contraseña» con esa clave de recuperación para validar el flujo completo antes
de que lo necesite la dueña de verdad.

## 5. Configurar antes de abrir caja

En **Configuración → Dispositivos → «Datos de la tienda»**: nombre comercial,
datos fiscales reales, régimen/tipos de IVA (consultarlo con la gestoría, ver
[FACTURACION.md](FACTURACION.md)), métodos de pago, impresora y SSD de copias.
La impresión automática queda desactivada hasta configurar los dispositivos.

Después, alta de catálogo y existencias iniciales vía **Stock → Alta de
catálogo** + **Recepción** (el flujo antiguo de «Existencias iniciales» está
obsoleto; ver nota en [APERTURA.md](APERTURA.md)).

## 6. Pruebas funcionales (checklist de aceptación)

Seguir [ACEPTACION.md](ACEPTACION.md) §3 a §7 marcando cada punto según se
ejecuta de verdad — «se ha revisado el código» no cuenta como probado:

- **§3 Acceso**: primer acceso, recuperación con clave, que la clave vieja
  deje de servir.
- **§4 Servicio Windows**: reiniciar Windows y comprobar que el servicio
  arranca solo; parar/matar el proceso y comprobar los reintentos;
  reinstalar/desinstalar y comprobar que la base y las copias **no**
  desaparecen.
- **§5 Actualización real**: al publicar una versión siguiente, comprobar que
  la app la detecta, se aplica al cerrar caja, se aplaza si hay caja abierta,
  y probar un fallo forzado (matar el proceso a mitad de copia/migración) para
  ver que revierte solo.
- **§6 Diagnóstico**: `diagnostico.ps1` en dos equipos y comparar con
  `comparar_diagnosticos.py`.
- **§7 Hardware físico**: impresora ESC/POS, cajón, lector de códigos, SSD de
  copias, datáfono manual.

## 7. Cómo publicamos una actualización (equipo de desarrollo)

Esto es lo que hacemos **nosotros** cada vez que hay una versión nueva que
llevar a la tienda. El detalle completo está en
[ACTUALIZACIONES.md](ACTUALIZACIONES.md) y
[publicar/PUBLICAR.md](EntreRamblas/publicar/PUBLICAR.md); aquí va el resumen
operativo con los comandos reales.

0. **Requisito previo, una sola vez**: resolver el aviso de la firma (§0 de
   esta guía). Sin una clave privada real cuya pública coincida con
   `EntreRamblas/instalador/firma-publica.pem`, cualquier release que
   publiquemos será rechazada en silencio por las tiendas — sin aviso a la
   dueña, sin error visible, nada (ver el porqué al final de esta sección).
1. Con las pruebas en verde, subir el número de versión en
   `EntreRamblas/custom_addons/mi_gestor_stock/__manifest__.py`. Si hay
   cambios de datos, añadir
   `EntreRamblas/custom_addons/mi_gestor_stock/migrations/<versión>/post-migrate.py`.
2. **Requiere PowerShell 7** (`pwsh`, no `powershell.exe` 5.1):
   ```powershell
   .\publicar\empaquetar.ps1 -Salida ..\dist -Firmar "<ruta a firma-privada.pem>"
   ```
   Corre las pruebas (`test.ps1 -Restore`), comprueba la integridad del motor
   Odoo, arma `dist\payload\` con el CPython vendorizado y las ruedas
   offline, genera `EntreRamblas-<versión>.zip`, `manifest.json` e
   `integridad.json`, y firma ambos con la clave privada indicada en
   `-Firmar`. Usar `-SaltarPruebas` solo si ya se corrieron en otro paso.
3. Si es para instalaciones nuevas, compilar el instalador con Inno Setup
   (`instalador/README.md`):
   ```powershell
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalador\EntreRamblas-Setup.iss
   ```
4. Antes de subir nada, **verificar la firma localmente**:
   ```powershell
   python EntreRamblas/tools/paquete_firma.py verificar `
     --archivo dist\manifest.json --firma dist\manifest.json.sig `
     --clave EntreRamblas\instalador\firma-publica.pem
   # tiene que decir VÁLIDA — si no, no se publica
   ```
5. En un clon de `AaronRuizzz/EntreRamblasReleases`, copiar `manifest.json`,
   `manifest.json.sig` y el `.zip` (y el `.exe` si aplica) a la raíz,
   `git commit && git push`.
6. Comprobar desde un equipo de tienda (o el de pruebas ya instalado):
   ```powershell
   .\venv\Scripts\python.exe tools\actualizador.py comprobar --releases-url https://raw.githubusercontent.com/AaronRuizzz/EntreRamblasReleases/main
   ```
   Tiene que imprimir `disponible <versión>`, no `rechazado: ...`.

## 8. Cómo se entera y avisa la dueña, desde la app

- La URL de releases viene **precargada** por defecto en cada instalación
  (`mgs.update.releases_url`, apuntando a
  `https://raw.githubusercontent.com/AaronRuizzz/EntreRamblasReleases/main`) —
  no hay que configurar nada en la tienda para esto.
- Un cron interno (`Gestor de stock: comprobar actualizaciones`) comprueba
  **una vez al día** si hay versión nueva y firmada; el arranque del servicio
  también comprueba. Si la hay y es compatible, la descarga y verifica
  (firma + SHA-256) **en el acto**: cuando la dueña acepte, el paquete ya está
  listo en disco.
- Si todo verifica, aparece el aviso **«Actualización disponible: versión
  X»** en la pantalla de inicio y en **Configuración → Actualizaciones**, con
  el botón **«Actualizar al cerrar»**. Al pulsarlo, se registra el
  consentimiento (versión + SHA-256 exactos) y arranca bajo demanda el
  servicio `EntreRamblasActualizador`, que aplica la actualización al cerrar
  caja, sin más intervención.
- **Si la firma no verifica, la dueña no ve absolutamente nada**: lo comprobé
  leyendo `mgs_update.py` — cuando `comprobar` falla por firma inválida, el
  estado (`fase`) no cambia, así que el resumen que lee la pantalla de inicio
  sigue devolviendo `available: False` sin ningún mensaje. El error solo
  queda en `estado.json` (`mensaje: "La firma del manifiesto no es válida..."`)
  y en el log del servicio, nada visible en la interfaz. Por eso el paso 0 de
  esta sección es bloqueante: publicar con la clave equivocada no da error a
  nadie, simplemente la actualización nunca llega ni se avisa.
- Para comprobar a mano que el aviso llegó de verdad, en el PC de tienda:
  ```powershell
  .\venv\Scripts\python.exe tools\actualizador.py estado
  ```
  Buscar `"fase": "disponible"` o `"preparado"` con la versión esperada.

---

No presentar «instalación validada», «actualización probada en producción» ni
«hardware certificado» ante la propietaria hasta cerrar los puntos de
[ACEPTACION.md](ACEPTACION.md) con fecha y quién los ejecutó — es la propia
norma del proyecto.
