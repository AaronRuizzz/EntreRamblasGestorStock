# Manual de tienda — Entre Ramblas · Clavel & Azahar

Manual de uso diario y de recuperación. Integra los manuales por flujo, que
siguen sirviendo como detalle: [APERTURA.md](APERTURA.md), [EVENTOS.md](EVENTOS.md),
[RECUENTOS.md](RECUENTOS.md), [DEVOLUCIONES.md](DEVOLUCIONES.md),
[INFORMES.md](INFORMES.md) e [INSTALACION.md](INSTALACION.md).

> **Antes de leer nada más.** El datáfono es un aparato **independiente**. El
> programa anota que un cobro fue con tarjeta, pero **no cobra ni devuelve** por
> el datáfono. Cada cobro y cada reembolso con tarjeta se hace en el datáfono y
> se comprueba allí.

> ⚠️ **Pendiente de actualizar (9 de septiembre de 2026).** Se han **quitado del
> programa** varias secciones que este manual todavía describe: **Compras**
> (pedidos a proveedor y previsión), **Partidas**, **Recuento físico**,
> **Reposición**, **Bajas de caducados**, **Recetas de ramo**, **Tarifas de
> campaña** y **Existencias iniciales**. En su lugar:
> - El **catálogo** se da de alta con **Stock → Alta de catálogo** o creando el
>   producto en **Recepción**; el stock de arranque entra por **Recepción**.
> - Un **ramo de un evento** se compone escribiendo sus flores en la propia línea
>   del presupuesto (pestaña «Partidas» del evento), no eligiendo una receta.
> - Las secciones 3 y 8 de este índice y las menciones a Compras/Previsión/
>   Tarifas/Recetas están **pendientes de reescritura**.

## Índice

1. [Quién puede hacer qué](#1-quién-puede-hacer-qué)
2. [Encender y apagar](#2-encender-y-apagar)
3. [Puesta en marcha (una sola vez)](#3-puesta-en-marcha-una-sola-vez)
4. [Recibir mercancía](#4-recibir-mercancía)
5. [Vender](#5-vender)
5bis. [Eventos y encargos](#5bis-eventos-y-encargos)
6. [Devoluciones](#6-devoluciones)
7. [Mermas](#7-mermas)
8. [Recuento físico](#8-recuento-físico)
9. [Cerrar la caja](#9-cerrar-la-caja)
10. [Informes](#10-informes)
11. [Copias de seguridad](#11-copias-de-seguridad)
12. [Cuando algo va mal](#12-cuando-algo-va-mal)
13. [Mantenimiento](#13-mantenimiento)

---

## 1. Quién puede hacer qué

La tienda trabaja con **una sola cuenta, la de la propietaria**, que puede hacer
todo: vender y devolver, recibir mercancía, ver costes y márgenes, montar ramos,
eventos y encargos, alta de catálogo, informes, configuración y copias.

Por dentro el programa distingue dos niveles de permiso —«Dependienta»
(operación diaria, sin costes ni configuración) y «Propietaria» (todo)— y los
comprueba **en el servidor**, no solo escondiendo botones. Hoy la cuenta que se
usa es la de Propietaria; ese doble nivel queda por si en el futuro se añade una
cuenta aparte para una dependienta.

**El programa entra solo con contraseña**, sin elegir usuario: hay **una
cuenta, la de la propietaria**, y las dos personas de la tienda trabajan con
ella. El servidor la selecciona solo; el formulario no deja cambiar de cuenta.
El primer acceso, la recuperación con clave impresa y el cambio de contraseña
se explican en `ACCESO.md`. Desde el menú del avatar (arriba a la derecha) solo
quedan **«Cambiar contraseña»** y **«Cerrar sesión»**.

## 2. Encender y apagar

El programa arranca **solo** con el ordenador, como servicio de Windows. No hay
que abrir ninguna ventana negra.

- **Para trabajar**: abre el navegador en la dirección del programa e inicia sesión.
- **Para vender**: entra en el TPV. Se abre a pantalla completa.
- **Al terminar el día**: cierra la sesión de caja (ver [§9](#9-cerrar-la-caja))
  y apaga el ordenador con normalidad, desde Inicio → Apagar.

> **No apagues el ordenador con el botón ni desenchufándolo** con una venta a
> medias. Cierra primero la caja.

## 3. Puesta en marcha (una sola vez)

Antes de la primera venta: **Alta de catálogo** y después **Existencias
iniciales**. El procedimiento completo está en [APERTURA.md](APERTURA.md).

Resumen: se sube una hoja con los productos, se comprueba entera, se importa; se
imprimen las etiquetas de los productos sin código de barras; y luego se registra
la mercancía que ya está en la tienda, una línea por partida, con su coste y su
caducidad. A partir de ahí, la mercancía entra **siempre** por Recepción.

## 4. Recibir mercancía

**Gestor de Stock → Stock → Recepción.**

1. Elige **Producto existente** y escanea. Cada lectura suma una unidad.
   Para un artículo nuevo, cambia a **Producto nuevo**, rellena los datos y
   escanea para asignarle el código.
2. Escribe el **coste** de esta entrada y la **caducidad**, si la tiene.
3. Indica el proveedor si quieres que quede anotado.
4. Pulsa **Guardar en almacén**.

Cada entrada crea **su propia partida**, con su coste y su caducidad congelados.
Dos compras de la misma flor a distinto precio son dos partidas distintas: por
eso el margen del informe sale bien y el TPV vende antes lo que caduca antes.

- El coste de una partida ya recibida **no se puede cambiar**. Si te equivocaste,
  regulariza con un recuento y recibe de nuevo.
- Pulsar dos veces **Guardar en almacén** no duplica la entrada.
- Si el producto tenía existencias sin partida, el programa no deja activar las
  partidas hasta regularizarlas: primero un recuento.

### Pedidos a proveedor

**Gestor de Stock → Pedidos a proveedor.** Para saber qué se ha pedido y qué
sigue sin llegar. Se crea el pedido, se pulsa **Confirmar pedido** (todavía no
mueve nada) y, cuando llega la mercancía, **Recibir** abre Recepción con el
proveedor y el pedido ya enlazados. Si llega en varias veces, se recibe cada
entrega por separado y el pedido pasa a «Recibido en parte» hasta completarse.
Un pedido confirmado no se edita: si hay que cambiar algo, se cancela y se
crea otro, para que quede constancia de lo que se pidió de verdad.

**Stock → Partidas** enseña, de cada partida recibida, de qué proveedor vino,
cuándo y con qué albarán — lo que antes solo se podía consultar mirando la
base de datos.

**Stock → Previsión de compra** ayuda a decidir cuánto pedir para una fecha
fuerte: ver [INFORMES.md](INFORMES.md).

## 5. Vender

**Gestor de Stock → Vender** abre el TPV directamente, sin pantallas de por
medio: con una sola caja en la tienda no hace falta elegir nada. Si no hay una
sesión abierta, el propio botón la abre.

En el TPV: escanea o toca el producto, cobra y valida.

- **El programa elige la partida sola**: primero la que caduca antes y, a
  igualdad, la más antigua.
- **No deja vender caducado ni más unidades de las que hay.** Si salta el aviso,
  revisa la mercancía en la estantería antes de insistir.
- **Efectivo**: el cajón se abre solo al cobrar y al dar cambio.
- **Tarjeta**: cobra en el datáfono, comprueba que ha ido bien y **después**
  registra el cobro como tarjeta en el TPV. El programa te lo pregunta al validar.
- **Pago mixto** (parte efectivo, parte tarjeta): se registran los dos importes.
- **El ticket sale solo** por la impresora térmica al cobrar. Si necesitas otra
  copia, usa la reimpresión; no vuelvas a cobrar.

Si al validar el resultado queda **incierto** (se fue la luz, se cayó la red), el
programa conserva el pedido y **no vuelve a cobrar solo**. Comprueba en el
datáfono y en el ticket qué pasó antes de repetir nada.

### Tarifas de campaña y descuentos

**Stock → Nueva tarifa de campaña**: para que la rosa cueste distinto en San
Valentín sin editar la ficha del producto a mano. Se indican las fechas, si
es un descuento o un precio fijo (sirve también para subir el precio) y,
opcionalmente, una sola categoría. En el TPV se elige la tarifa activa antes
de cobrar; fuera de esas fechas, el precio vuelve a ser el normal solo.
**Stock → Tarifas de campaña** las lista para revisarlas o desactivarlas.

Un descuento suelto en una venta concreta no necesita tarifa: la tecla **%**
del TPV ya lo aplica línea a línea, y el ticket lo imprime.

### Un ramo a medida

Toca **Ramo a medida** y monta el ramo: busca las flores, tócalas para añadirlas y
ajusta las cantidades. El precio sugerido sale del PVP de lo que lleva, y **puedes
cambiarlo** (el montaje también se cobra). Al añadirlo, el ticket enseña **una sola
línea**, pero el almacén descuenta **cada tallo de su partida**, la que caduca antes.

Si el ramo se repite (una composición que se vende a menudo igual), toca una
de las **recetas** de arriba del todo para precargarlo: sigue pudiéndose
ajustar antes de cobrar, no es una receta cerrada. Las recetas se gestionan
en **Stock → Recetas de ramo**, solo la propietaria.

Detalle completo, y cómo crear otras composiciones, en [EVENTOS.md](EVENTOS.md).

## 5bis. Eventos y encargos

**Gestor de Stock → Eventos y encargos.** Un evento no se hace en el TPV: se cierra
semanas antes, lleva señal y a veces material que se presta y vuelve. Vale para una
boda, un bautizo, una comunión, un evento de empresa o cualquier encargo grande.

El recorrido es: **Presupuesto → Aceptado → Entregado → Material devuelto → Cobrado**.

- Se prepara el **presupuesto** con las partidas y las dos fechas (la del evento y
  la de devolución del material). Se puede imprimir en PDF para la clienta.
- Al **aceptarlo**, el material de alquiler queda comprometido para esas fechas:
  ese arco ya no se puede prometer a otro evento que se solape. La mercancía **sigue
  en la tienda** hasta la entrega.
- Al **entregar**, lo que se vende se va al cliente y lo que se alquila pasa a
  «Alquiler en curso»: fuera de la tienda, pero todavía nuestro.
- Al volver, se anota por línea **cuántas vuelven enteras y cuántas rotas**. Las
  rotas se dan de baja como merma automáticamente. Lo que no vuelve queda a la
  vista para poder reclamarlo.
- **Cerrar evento** exige que no quede nada por cobrar ni material sin devolver.

> **El dinero de un evento no pasa por la caja del TPV**: no abre el cajón ni sale
> en el arqueo del día. Se registra en la pestaña **Cobros** del propio evento. El
> datáfono sigue siendo independiente.

Procedimiento completo en [EVENTOS.md](EVENTOS.md).

## 6. Devoluciones

Detalle completo en [DEVOLUCIONES.md](DEVOLUCIONES.md).

En el TPV: **Pedidos → Pagado**, busca el ticket, elige producto y cantidad,
**Reembolso**, **Pago**, método de devolución y **Validar**.

Al validar, el programa pregunta por **cada línea** en qué estado vuelve:

- **Recuperable** → vuelve a su partida original y se puede volver a vender.
- **Deteriorada** → se registra la devolución y, a la vez, una merma vinculada.

La elección vale para toda la cantidad de esa línea. **Si de tres rosas dos están
bien y una está rota, haz dos devoluciones parciales del mismo ticket**: una de
dos unidades como recuperable y otra de una unidad como deteriorada. El programa
lleva la cuenta de lo que queda por devolver.

Después de confirmar **no se puede cambiar** la marca de deterioro. Y recuerda:
la devolución del dinero con tarjeta se tramita en el datáfono.

## 7. Mermas

**Gestor de Stock → Mermas.** Para flor que se estropea, se rompe o caduca.

Elige producto, **partida**, cantidad y motivo. El coste que se apunta es el de
esa partida, no el precio de venta. Las mermas restan en el informe mensual, en
el «margen después de mermas».

No registres a mano la merma de una devolución deteriorada: esa ya la crea el
propio TPV.

## 8. Recuento físico

Detalle en [RECUENTOS.md](RECUENTOS.md). Resumen: crea el recuento con su motivo,
**Preparar partidas**, cuenta y anota cada una marcando **Revisado**, y aplica.
Solo se ajustan las diferencias.

Hazlo **en un momento sin ventas ni recepciones**. Si algo se mueve mientras
cuentas, el programa rechaza el ajuste y hay que recargar y volver a contar.

## 9. Cerrar la caja

1. En el TPV, **Cerrar sesión**.
2. Cuenta el efectivo del cajón y escribe el importe real.
3. Si no cuadra, anota el motivo antes de cerrar.

Al cerrar la caja el programa **marca que toca copia de seguridad**. Si aparece
un aviso de copia pendiente, no lo ignores: ver [§11](#11-copias-de-seguridad).

Para revisar un cierre de un día anterior (efectivo contado, diferencia, quién
cerró): **Informes → Cierres de caja**. Solo la propietaria.

## 10. Informes

Detalle en [INFORMES.md](INFORMES.md). **Informes → Informe mensual (PDF)**:
elige fechas (se cuentan los dos días incluidos, en hora de Madrid), y genera el
PDF, el CSV de ventas o el **ZIP de estadísticas**.

Dos avisos que conviene tener claros:

- **El stock que sale es el de hoy**, aunque el informe sea de un mes pasado.
- **La mercancía recibida no es un pago al proveedor**: es el valor de lo que
  entró, a coste.
- **Los eventos van en su propio apartado**, por fecha del evento, y no están
  sumadas en las ventas de mostrador: su dinero se cobra en otras fechas y
  mezclarlo no cuadraría con el arqueo de caja.

## 11. Copias de seguridad

El programa guarda una copia completa cada pocas horas y al cerrar la caja, y la
replica en el **disco externo** cuando está conectado. Cada copia es un `.zip`
acompañado de su `.zip.sha256`, que sirve para comprobar que no está dañada.

**Lo que tienes que hacer tú:**

- Tener el **disco externo conectado**. Si el aviso de copia pendiente no
  desaparece, es que no se está pudiendo copiar: revisa el disco y el espacio.
- **Guardar juntos el `.zip` y su `.sha256`.** Uno sin el otro no sirve.
- De vez en cuando, llevarte una copia fuera de la tienda.

Recuperar una copia es cosa de la persona que administra el programa
([INSTALACION.md](INSTALACION.md)): se recupera **siempre en una base nueva**,
nunca encima de la que está en uso. La base recuperada arranca con las tareas
automáticas y la impresión desactivadas a propósito, para que no imprima ni
mande nada mientras se comprueba.

## 12. Cuando algo va mal

| Qué pasa | Qué hacer |
|---|---|
| **No abre el programa en el navegador** | Espera un minuto tras encender: el servicio tarda en arrancar. Si sigue, reinicia el ordenador. |
| **El lector no lee** | Comprueba que está encendido y emparejado. Prueba a escanear en un campo de texto: si escribe números, el lector va bien y el problema es de la pantalla. |
| **El lector se salta caracteres** (Bluetooth) | Configuración → Dispositivos: sube el *retardo máximo entre teclas* a 250 ms y haz **Ctrl+F5**. |
| **No sale el ticket** | Comprueba papel, encendido y cable/red de la impresora. Después usa la reimpresión. **No vuelvas a cobrar.** |
| **No se abre el cajón** | El cajón cuelga de la impresora: si la impresora está apagada o sin red, no hay pulso. Ábrelo con la llave. |
| **Salen símbolos raros en el ticket** | Configuración → Dispositivos: cambia el juego de caracteres o activa **Sin acentos**. |
| **El datáfono cobró y el TPV no** | Registra el cobro en el TPV como tarjeta. El importe del día tiene que cuadrar con el datáfono. |
| **El TPV cobró y el datáfono no** | No entregues la mercancía. Anula en el TPV y repite el cobro en el datáfono. |
| **Se fue la luz a mitad de venta** | Al volver, abre el mismo pedido. No crees otro: el programa conserva lo que quedó a medias. |
| **Dice que no hay stock y sí lo hay** | Es que en el programa no está registrado: revisa si esa entrada se recibió. Regulariza con un recuento, no con una compra ficticia. |
| **Dice que está caducado** | Retira esa partida y regístrala como merma. Si la fecha está mal puesta, corrígela con un recuento. |
| **Aviso de copia pendiente que no se va** | Revisa el disco externo y el espacio libre. Avisa a quien administra el programa. |

**Regla general ante cualquier duda de dinero**: comprueba primero el datáfono y
el ticket, y solo después toca el programa. Nunca repitas un cobro «por si acaso».

## 13. Mantenimiento

### Acceso y contraseña

Todo lo del acceso está en **`ACCESO.md`**: primer acceso con código de
activación, «He olvidado mi contraseña» con la clave impresa, regenerar la
clave (Configuración → Seguridad) y, para la pérdida total, la herramienta
local `recuperar-acceso.ps1` (administrador de Windows).

**Cambiar la contraseña del día a día**: menú del avatar → «Cambiar
contraseña».

**Si hiciera falta una cuenta separada para una dependienta** (hoy no la hay):
es tarea de consola, con el servidor **parado**, desde `EntreRamblas`:

```powershell
.\venv\Scripts\python.exe odoo\odoo-bin shell -c odoo.local --no-http
```

```python
env['res.users'].create({
    'name': 'Nombre de la dependienta',
    'login': 'dependienta',
    'password': 'una-provisional-de-12+',
    'groups_id': [(6, 0, [env.ref('mi_gestor_stock.group_mgs_user').id])],
})
env.cr.commit()
```

Ten en cuenta que **el formulario de acceso sólo atiende a la propietaria**: dar
de alta otra cuenta hoy no basta para que pueda entrar por la web (haría falta
un cambio en la pantalla de acceso).

- **Cada día**: cerrar la caja al terminar y apagar bien el ordenador.
- **Cada semana**: mirar el panel de Stock (avisos y caducidades) y comprobar que
  las copias del disco externo están al día.
- **Cada mes**: informe mensual y recuento de las categorías con más movimiento.
- **Cada cierto tiempo**: llevarse una copia fuera de la tienda y comprobar que
  de verdad se puede recuperar (se prueba en una base nueva, nunca en la de uso).

### Lo que este programa **no** hace

- No cobra ni devuelve por el datáfono.
- No cobra ni devuelve la fianza del material de alquiler: la calcula y la enseña,
  pero el dinero lo mueves tú.
- No trabaja en la nube: todo está en el ordenador de la tienda y en sus copias.
- No sustituye la asesoría fiscal: las obligaciones de facturación y sus plazos
  hay que confirmarlas con la gestoría (ver el estado en
  [TRASPASO_IA.md](TRASPASO_IA.md)).
