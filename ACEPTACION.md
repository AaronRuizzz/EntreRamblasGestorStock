# Aceptación pendiente (máquina limpia y hardware real)

Esto es lo que **no** se puede certificar desde una sesión de agente en este
PC de desarrollo: requiere una máquina Windows sin herramientas de
desarrollo, permisos de administrador para registrar servicios, y el hardware
físico de la tienda. La revisión de 2026-09-10 lo señaló como pendiente; este
documento es la lista concreta y el criterio de cierre de cada punto, para
ejecutarla cuando se disponga de esa máquina.

No marcar ningún punto como hecho sin haberlo ejecutado de verdad. "Se ha
revisado el código" no es lo mismo que "se ha probado".

## 1. Paquete e instalador

- [ ] `pwsh` (PowerShell 7) instalado en el PC de desarrollo, con Inno Setup 6.
- [ ] `.\publicar\empaquetar.ps1 -Salida ..\dist -Firmar <clave privada>` sin
      `-SaltarPruebas`: termina sin error, deja `dist\payload\python\` con un
      CPython 3.12 completo y `dist\payload\wheels\` con las ruedas del lock.
- [ ] `ISCC.exe instalador\EntreRamblas-Setup.iss` compila `EntreRamblas-Setup.exe`.
- **Criterio de cierre:** el `.exe` existe, pesa lo esperado (unos
  cientos de MB por el motor y el runtime) y `manifest.json`/`integridad.json`
  están firmados (`paquete_firma.py verificar` da VÁLIDA).

## 2. Instalación limpia en máquina sin herramientas de desarrollo

- [ ] Windows 11 limpio (VM o equipo), **sin** Git, **sin** Python, sin el
      perfil del desarrollador.
- [ ] Copiar solo `EntreRamblas-Setup.exe` y ejecutarlo. Aceptar UAC.
- [ ] Instalación completa sin error: PostgreSQL propio, servicio
      `EntreRamblasOdoo`, servicio `EntreRamblasActualizador` (bajo demanda,
      **no** debe quedar arrancado), acceso directo en el escritorio, base
      `entre_ramblas` nueva sin demo.
- [ ] `entre_ramblas-activacion.txt` en `%ProgramData%\EntreRamblas` con un
      código legible.
- **Criterio de cierre:** el acceso directo abre `/mgs/primer-acceso` en Edge
  sin haber tocado una consola. `sc qc EntreRamblasActualizador` muestra
  `START_TYPE: DEMAND_START`.

## 3. Primer acceso y recuperación, en el navegador

- [ ] Primer acceso con el código del archivo, contraseña de 12+ caracteres,
      clave de recuperación mostrada una vez.
- [ ] Confirmar custodia de la clave (checkbox + botón): sin error CSRF,
      `recovery_ack` queda `True` (Configuración → Seguridad lo muestra).
- [ ] Cerrar sesión, recuperar con la clave, contraseña nueva, clave nueva.
- [ ] La clave anterior deja de servir.
- **Criterio de cierre:** todo el recorrido se hace desde el navegador, sin
  ninguna herramienta local, y sin ningún error visible.

## 4. Servicio Windows: ciclo de vida completo

- [ ] `sc query EntreRamblasOdoo` → En ejecución tras instalar.
- [ ] Reiniciar Windows: el servicio arranca solo (con el retraso
      configurado) y la app responde.
- [ ] Parar el servicio (`net stop` o Servicios.msc): se detiene en menos de
      ~100 s, sin quedar "Deteniéndose" colgado.
- [ ] Matar el proceso a la fuerza (Administrador de tareas): Windows lo
      reinicia solo (reintentos a 120 s y 180 s configurados).
- [ ] Reinstalar (`EntreRamblas-Setup.exe` de nuevo) y desinstalar: la base y
      las copias **no** desaparecen.
- **Criterio de cierre:** los cinco puntos anteriores, cada uno observado
  directamente (no inferido del código).

## 5. Actualización real de extremo a extremo

Con una segunda versión publicada de verdad (número de versión subido,
paquete firmado y publicado en el repositorio de releases):

- [ ] La app detecta la versión nueva sola (o `Configuración → Actualizaciones
      → Comprobar ahora` si existe ese botón) y queda descargada y verificada.
- [ ] «Actualizar al cerrar»: el servicio aplicador arranca
      (`sc query EntreRamblasActualizador` → en ejecución mientras aplica).
- [ ] Con una caja abierta: la aplicación se aplaza y se ve reflejado en el
      estado; al cerrar caja, se aplica sola sin más intervención.
- [ ] Tras aplicar: versión nueva funcionando, motor y lanzadores
      actualizados (no solo el código del módulo), sin haber tocado nada a
      mano.
- [ ] **Fallo forzado:** cortar la aplicación a mitad (matar el proceso del
      servicio aplicador durante la copia o la migración) y comprobar que:
      - si fue durante la copia, se puede reanudar sin duplicar trabajo;
      - si fue durante la migración, se revierte solo: código y base
        anteriores, servicio de la app arrancando de nuevo, sin vender con
        una base a medio migrar.
- [ ] Firma inválida, descarga truncada y falta de espacio en disco: cada uno
      deja el estado en `fallo` con un mensaje claro, sin tocar el código
      instalado.
- **Criterio de cierre:** los siete puntos, cada uno con su propio ensayo
  (no basta con uno solo que "salga bien").

## 6. Igualdad entre una instalación nueva y una migrada

- [ ] Dos equipos: uno con instalación nueva, otro con una base antigua
      migrada con `-u`. `diagnostico.ps1` en ambos y
      `comparar_diagnosticos.py equipo-a.json equipo-b.json` → sin
      diferencias relevantes (el historial de versiones se ignora a
      propósito).
- **Criterio de cierre:** el comparador termina con "Sin diferencias
  relevantes." con código de salida 0.

## 7. Hardware físico

- [ ] Impresora térmica ESC/POS: ticket de venta y de devolución (con base e
      IVA en negativo en la devolución), corte de papel.
- [ ] Cajón portamonedas: apertura al cobrar en efectivo.
- [ ] Lector de códigos de barras: recepción y venta.
- [ ] SSD/disco externo para copias: réplica automática, y qué pasa si está
      desconectado al hacer la copia (debe seguir la copia local).
- [ ] Datáfono: **no** está integrado; comprobar que el cierre de caja no
      exige conciliarlo automáticamente y que el proceso manual de la tienda
      sigue siendo viable.
- **Criterio de cierre:** cada dispositivo probado con el hardware real de la
  tienda, no con un sustituto.

---

Mientras estos puntos no estén marcados y fechados con quién los ejecutó, no
presentar «instalación validada», «actualización probada en producción» ni
«hardware certificado» en ningún manual ni comunicación a la propietaria.
