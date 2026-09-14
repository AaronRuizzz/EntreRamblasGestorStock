# Conectar la impresora de tickets — Approx appPOS80AM(-USBLAN)

Guía paso a paso para dejar la impresora térmica de 80 mm funcionando con el
programa. No hace falta instalar nada especial: el programa ya lleva todo lo
necesario (incluido el paquete para hablar con Windows). Solo hay que decirle
**cómo está conectada tu impresora concreta**.

Si el cajón portamonedas (Approx CASH01) no abre, es el **paso 4**: cuelga de
la propia impresora, así que primero tiene que quedar bien conectada la
impresora.

## Antes de empezar

- La impresora admite dos formas de conexión a la vez: **USB** y **red
  (Ethernet/LAN)**. Solo hace falta elegir **una** en el programa; la otra
  puede quedar enchufada sin usarse.
- Recomendación para una tienda con un solo ordenador: **USB**. Es la más
  sencilla de dejar funcionando y de que un router o un cambio de red no la
  desconfigure más adelante. Usa **Red** solo si el ordenador y la impresora
  van a estar en salas distintas o si ya tienes experiencia con redes.
- Necesitas entrar como **gestora** (la propietaria) para tocar esta pantalla.

## Paso 1 — Conectar el cable y encender la impresora

Enchufa la impresora a la corriente y conéctala al ordenador con el cable que
trae (USB, o el de red si vas a usarla en modo Red). Enciéndela y comprueba
que tiene papel cargado.

## Paso 2 — Elegir la conexión USB (recomendado)

1. En Windows, abre **Configuración → Bluetooth y dispositivos → Impresoras y
   escáneres** (o **Dispositivos e impresoras** en versiones antiguas de
   Windows) y comprueba que la impresora aparece en la lista.

   **Si no aparece** (lo normal si el ordenador no tiene lector de CD: el
   mini-CD que trae la impresora no sirve de nada sin uno), descarga el driver
   de la **página oficial de Approx**, sin necesidad del CD:

   - Ficha del modelo (appPOS80AM-USBLAN):
     <https://www.aqproxtpv.es/impresoras-80mm/228-apppos80am-usblan.html>
     — sección **«Descargas»**, al final de la página.
   - Primero, en el **Administrador de dispositivos** de Windows (clic derecho
     en el botón Inicio → «Administrador de dispositivos») mira si al
     enchufar la impresora aparece algo con un **triángulo amarillo** (en
     «Otros dispositivos» o «Controladoras de bus serie universal»):
     - **Sí aparece con aviso** → instala primero **VirtualCOM.zip** (el
       driver del puerto USB en sí; sin él, Windows ni siquiera ve la
       impresora como un puerto).
     - **No aparece nada raro**, o después de instalar VirtualCOM sigue sin
       salir en «Impresoras y escáneres» → instala **«POS Printer Driver
       Setup V8.203.zip»** (el que registra la impresora en Windows).
     - Si tienes dudas de cuál te hace falta, descarga **«CD COMPLETO
       APPPOS80AM-USB&LAN»**: es una copia exacta del contenido del mini-CD
       físico, con todo junto.
   - Descomprime el `.zip` descargado y ejecuta el instalador (`setup.exe` o
     similar) como administrador. Reinicia el ordenador si el instalador lo
     pide antes de seguir con el paso 2.2.
2. Anota el **nombre exacto** con el que aparece en esa lista (por ejemplo
   `POS-80` o `Approx appPOS80AM`). Tiene que copiarse tal cual, con mayúsculas
   y espacios incluidos.
3. En el programa: **Configuración → Dispositivos**, pestaña **«Impresora y
   cajón»**.
4. En **«Conexión de la impresora»** elige **«Impresora de Windows (USB)»**.
5. En **«Nombre en Windows»** escribe el nombre exacto anotado en el paso 2.
6. Guarda.
7. Pulsa **«Imprimir ticket de prueba»**. Tiene que salir un ticket con la
   fecha, un código de barras y la frase de comprobación. Si no sale nada,
   revisa el aviso en pantalla: normalmente dice si el nombre no coincide.

## Paso 3 — Alternativa: conexión por Red (Ethernet/LAN)

Solo si has decidido usar red en vez de USB.

1. La impresora necesita una **IP fija** dentro de tu red (por ejemplo
   `192.168.1.50`). Si cambia de IP al reiniciar el router, el programa deja
   de encontrarla. Dos formas de conseguirlo:
   - Reservar esa IP para la impresora desde el router (búscalo como «DHCP
     reservation» o «IP reservada» en el panel del router), usando la
     dirección física (MAC) que trae la etiqueta de la impresora.
   - O configurar una IP fija directamente en la impresora, con la utilidad
     que trae en el CD/USB (suele llamarse algo como «Network Config Tool»).
2. En el programa: **Configuración → Dispositivos**, pestaña **«Impresora y
   cajón»**.
3. En **«Conexión de la impresora»** elige **«Red (Ethernet/LAN, TCP 9100)»**.
4. En **«Dirección IP»** escribe esa IP fija. Deja el **«Puerto»** en `9100`
   (es el que usa esta impresora salvo que se haya cambiado a propósito).
5. Guarda y pulsa **«Imprimir ticket de prueba»**.

## Paso 4 — Comprobar el cajón portamonedas

El cajón **no se conecta al ordenador**: va enchufado con un cable RJ11 a la
propia impresora, y esta le manda un pulso eléctrico para abrirlo. Por eso,
si la impresora está apagada, sin papel da igual, pero si está apagada o mal
conectada, **el cajón tampoco abre**.

1. En la misma pestaña, comprueba que **«Cajón conectado a la impresora»**
   está marcado.
2. Pulsa **«Abrir el cajón»**. Si no abre, sube **«Duración del pulso (ms)»**
   a 200 y prueba de nuevo; si sigue sin abrir, revisa el cable RJ11 entre
   impresora y cajón.

## Paso 5 — Ajustes finos (opcionales)

- **«Ancho del papel»**: déjalo en 80 mm salvo que la impresora sea de rollo
  estrecho de 58 mm.
- **«Juego de caracteres»**: si en el ticket salen símbolos raros en vez de
  acentos o del símbolo del euro, prueba con otro juego de la lista; **«Sin
  acentos»** siempre funciona, aunque quita las tildes.
- **«Imprimir el ticket del TPV automáticamente»**: con esto marcado (viene
  así por defecto), el ticket sale solo al cobrar, sin ningún diálogo de
  impresión del navegador. Si algún día cambias de impresora y quieres volver
  a imprimir el PDF por el navegador mientras la resuelves, desmárcalo o pon
  la conexión en **«Sin impresora»**.

## Si algo no funciona

| El programa dice… | Qué revisar |
|---|---|
| «No se pudo conectar con la impresora en `IP:puerto`» | La impresora está apagada, sin red, o la IP anotada ya no es la suya (revisa el paso 3.1: no tiene IP fija). |
| «Windows no encuentra la impresora «`nombre`»» | El nombre en «Nombre en Windows» no coincide letra por letra con el de «Impresoras y escáneres». Cópialo de nuevo desde ahí. |
| «Falta la dirección IP de la impresora» / «Falta el nombre de la impresora de Windows» | El campo correspondiente al modo elegido está vacío. |
| No pasa nada al pulsar «Imprimir ticket de prueba» pero tampoco hay error | Comprueba el papel y que el cable no se haya soltado; vuelve a pulsar. |
| El ticket sale con símbolos raros en vez de acentos o el euro | Paso 5: cambia el «Juego de caracteres». |

Si tras seguir estos pasos sigue sin salir el ticket, anota el mensaje exacto
que muestra el programa (aparece arriba a la derecha al pulsar el botón de
prueba) y compártelo con quien mantenga el equipo: ese texto ya dice, en la
mayoría de los casos, cuál de los pasos anteriores falta.

Una vez que «Imprimir ticket de prueba» funcione, las ventas del TPV
imprimirán el ticket solas al cobrar, sin ningún paso adicional: ver
«5. Vender» en [MANUAL_TIENDA.md](MANUAL_TIENDA.md).
