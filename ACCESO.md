# Acceso a la aplicación

Resumen de cómo se entra, cómo se recupera el acceso y qué pasa si se pierde
todo. El código está en `EntreRamblas/custom_addons/mi_gestor_stock/models/mgs_access.py`
y `.../controllers/mgs_auth.py`.

## Una sola cuenta: la propietaria

- El uso diario va con **una cuenta de propietaria** (`propietaria`), con
  permisos de **gestión de tienda** (grupo «Propietaria»): stock, TPV,
  eventos, informes, configuración de dispositivos y copias. **No** tiene
  administración técnica de Odoo (usuarios y compañías, modo desarrollador,
  ajustes generales).
- La cuenta `admin` sigue existiendo como **cuenta técnica de rotura de
  cristal**: sin contraseña utilizable, sólo se restablece con la herramienta
  local (abajo) o por consola. No entra por el formulario web.
- Dar de alta una dependienta o cambiarle la contraseña es tarea de consola
  (`odoo-bin shell`), ver `MANUAL_TIENDA.md` §13. Es una consecuencia
  aceptada de quitar «Ajustes».

## El formulario de acceso

- Sólo **contraseña**, botón **«Entrar»** y enlace **«He olvidado mi
  contraseña»**. Una vez la dueña ha fijado su contraseña, el servidor
  autentica **siempre** su cuenta: no hay campo de usuario y no se puede
  cambiar de cuenta manipulando el formulario.
- Se puede **pegar** la contraseña y mostrarla temporalmente con la casilla
  «Mostrar la contraseña».
- Intentos limitados: tras 5 fallos seguidos desde el mismo equipo, el acceso
  se bloquea un rato (y el bloqueo crece si se insiste). El contador
  **sobrevive a un reinicio**.

## Primer acceso

1. El instalador deja un archivo `<base>-activacion.txt` con un **código de
   activación de un solo uso** (en el programa sólo se guarda su huella
   SHA-256, nunca el código).
2. Al abrir el programa por primera vez, la pantalla de acceso lleva al
   asistente de primer acceso: se escribe el código y se elige la contraseña
   (**mínimo 12 caracteres**).
3. El programa muestra **una vez** la **clave de recuperación** (una tira de
   letras y números, ~160 bits). Hay que **imprimirla o copiarla a papel** y
   guardarla fuera del PC. No se vuelve a mostrar; sólo se guarda su huella.
4. Se marca la casilla de que se ha guardado y se entra.

## He olvidado la contraseña

- Enlace «He olvidado mi contraseña» → se escribe la **clave de
  recuperación** y una contraseña nueva.
- Al hacerlo: se cambia la contraseña, **se cierran todas las sesiones
  abiertas**, la clave usada **deja de servir** y el programa entrega una
  **clave nueva** (otra vez, una sola vez) que hay que volver a guardar.
- No hay recuperación por correo.

## Regenerar la clave de recuperación

- **Configuración → Seguridad → «Generar / regenerar la clave»**. Pide la
  **contraseña actual**. La clave anterior deja de servir al instante.
- Ahí mismo se ve si hay clave creada y cuándo, y una huella corta para
  cotejar cuál se tiene guardada.

## Se ha perdido también la clave de recuperación

- Herramienta local, en el PC de la tienda, **como administrador de Windows**:

  ```powershell
  .\recuperar-acceso.ps1 -Config "<ruta a odoo.local>" -Database <base>
  ```

  Reinicia el primer acceso con un código de activación nuevo (archivo
  `<base>-activacion.txt`). La dueña vuelve a elegir contraseña y recibe una
  clave nueva.
- `-Admin` en el mismo script restablece la contraseña de la cuenta técnica
  `admin` (mantenimiento profundo); la enseña una sola vez.
- **No hay contraseña maestra compartida.** Cada uso de la herramienta queda
  registrado en **Configuración → Restablecimientos de acceso**.

## Rastro

Cada primer acceso, recuperación con clave, regeneración y uso de la
herramienta local deja una línea en **Configuración → Restablecimientos de
acceso** (`mgs.access.event`): fecha, usuario y vía. No se puede editar ni
borrar.
