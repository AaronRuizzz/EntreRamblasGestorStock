# Ramos a medida, eventos y material de alquiler

Dos formas de vender que conviven en la tienda:

- **Mostrador**: alguien entra y quiere un ramo ahora. Se monta, se cobra y se va.
  Va por el **TPV**.
- **Evento o encargo**: se cierra semanas antes, lleva señal y a veces material que
  se presta y vuelve. Va por **Eventos y encargos**, no por el TPV. Vale para una
  boda, un bautizo, una comunión, un evento de empresa o cualquier encargo grande.

---

## 1. Ramo a medida en el mostrador

En el TPV, toca el producto **Ramo a medida**. Se abre una pantalla para montarlo:

1. Busca y toca las flores y el material de la izquierda. Cada toque suma una unidad.
2. Ajusta las cantidades con los botones **-** y **+**, o escribiendo el número.
3. El **precio sugerido** se calcula con el PVP de lo que lleva. **Puedes cambiarlo**:
   el ramo vale más que sus flores sueltas porque incluye el montaje.
4. **Añadir al ticket**.

En el ticket sale **una sola línea** («Ramo a medida», su precio), que es lo que ve
la clienta. Por dentro, el almacén descuenta **cada tallo de su partida**, eligiendo
siempre la que caduca antes. Así el inventario y el margen siguen siendo reales.

**Puedes crear más composiciones.** Cualquier producto con la casilla **«Ramo o
composición a medida»** marcada en su ficha se comporta igual: centro de mesa,
corona, ramo de novia. Esos productos no tienen existencias propias —sus
existencias son las de las flores que se les pongan.

### Cosas que conviene saber

- Si no hay flores suficientes, **el programa avisa antes de cobrar**, no después.
- Un ramo no puede llevar dentro otro ramo.
- **Una devolución de un ramo devuelve el dinero, pero no devuelve las flores al
  stock.** Es lo correcto: esas flores ya se cortaron y se montaron. Si alguna se
  puede aprovechar, entra por recepción o se regulariza con un recuento.

---

## 2. Eventos y encargos

**Gestor de Stock → Eventos y encargos.** Solo la propietaria.

El recorrido tiene cinco estados y no se puede saltar ninguno:

**Presupuesto → Aceptado → Entregado → Material devuelto → Cobrado**

### Presupuesto

Cliente, **fecha del evento**, **fecha de devolución del material** y las partidas.
Al elegir un producto, el programa rellena solo el precio y marca **«Se alquila»**
si esa ficha lo tiene marcado.

**Si la partida es un centro de mesa o un ramo a medida** (una composición,
no un producto con existencias propias), se indican en la propia línea **de qué
flores y material está hecho** (sección «Materiales de la composición»,
validada con el mismo criterio que el TPV): al entregar —o al cobrar en caja—
el almacén descuenta cada flor, multiplicada por cuántos centros lleva el
evento, no el centro en sí, que no tiene existencias. Una composición sin
materiales no se puede guardar: el programa la rechaza antes, para no perder
la merma de flor en silencio.

Aquí **no se compromete ni se mueve nada**: es una oferta. Puedes imprimir el
presupuesto en PDF para la clienta (botón **Imprimir**); sale con lo que se alquila
señalado y la fianza calculada.

### Aceptado

Al pulsar **Aceptar presupuesto**, el material de alquiler **queda comprometido**
para esas fechas. A partir de ahí, ese arco no se puede prometer a otro evento que
se solape, y el programa lo impide con un aviso que dice cuántas unidades quedan
libres y entre qué fechas.

**Ojo: comprometer no es sacar.** La mercancía sigue en la tienda hasta la entrega.

Un evento aceptado ya no se edita. Si hay que cambiar algo, se cancela y se hace
otro: así queda constancia de lo que se ofreció.

### Entregado

Al pulsar **Entregar**, sale el material de verdad:

- Lo que **se vende** (centros, ramos, velas) se va al cliente y deja de ser nuestro.
- Lo que **se alquila** va a la ubicación **«Alquiler en curso»**: ya no está en la
  tienda y no se puede vender, pero **sigue siendo nuestro** y tiene que volver.

### Material devuelto

Cuando vuelve el material, en las partidas se anota por cada línea:

- **Vuelven enteras**: regresan al almacén y quedan otra vez disponibles.
- **Vuelven rotas**: regresan y **se dan de baja como merma**, con motivo *rotura*
  y su coste real. No quedan disponibles para otro evento.

Se pulsa **Registrar devolución**. Se puede hacer **en varias veces**: si vuelven
tres de cinco, se anotan esas tres y el aviso sigue hasta que vuelva el resto.

**Lo que no vuelve se queda a la vista** en «Alquiler en curso». Ni se pierde ni se
da por bueno: sigue contando como material fuera para poder reclamarlo.

### Cobrado

**Cerrar evento** exige dos cosas: que no quede nada por cobrar y que no quede
material sin devolver. Si falta algo, el programa dice cuál de las dos cosas es.

### Los cobros

En la pestaña **Cobros**, con el botón **Registrar cobro**: la señal cuando se
acepta y el resto cuando se entrega. Cada cobro guarda importe, forma de pago,
fecha y quién lo registró, y **no se puede modificar después** — si hay un error,
se registra otro cobro.

> **La señal, la fianza y el alquiler no pasan por la caja del TPV.** No abren el
> cajón ni salen en el arqueo del día, y el **datáfono sigue siendo
> independiente**: registrar «tarjeta» aquí no cobra nada en el terminal.

### Cobrar en caja lo que se vende

Para un encargo sencillo —un ramo, un centro para una comunión— que el cliente
paga al recoger, el botón **Cobrar en caja** (visible en Presupuesto y Aceptado)
abre el TPV con las flores y ramos del encargo ya cargados, el cliente puesto y
el importe listo: se cobra en efectivo o con datáfono y sale el ticket, como una
venta normal. El stock de las flores se descuenta ahí (no hace falta pulsar
«Entregar» para esas partidas) y el encargo anota el cobro; si con eso queda
pagado y no hay alquiler, se cierra solo.

**El material de alquiler no va a la caja**: se sigue reservando con «Aceptar
presupuesto», entregando con «Entregar» y cobrando (fianza incluida) con
«Registrar cobro».

### La fianza

Si el material de alquiler tiene fianza en su ficha, el evento la calcula y la
enseña. Es **informativa**: sirve para saber cuánto pedir y qué descontar si algo
no vuelve. El programa no la cobra ni la devuelve solo.

---

## 3. Marcar un artículo como de alquiler

En la ficha del producto (**Stock → Productos**):

- **Se alquila para eventos**: sale y vuelve. Exige que el producto lleve control de
  existencias, porque hay que saber cuántas unidades hay y dónde están.
- **Fianza por unidad**: lo que se pide en depósito por cada una.

Un mismo catálogo puede tener las dos cosas: el arco se alquila, el jarrón que se
lleva la novia se vende. Es una marca por artículo, no por categoría.

---

## 4. Qué sale en el informe mensual

Los eventos tienen su **propio apartado**, por fecha del evento, con el total, lo
cobrado y lo pendiente de cada uno.

**No están sumados en las ventas de mostrador**, y es a propósito: el dinero de un
evento se cobra por señal y cobro final, en fechas distintas de la del evento, y
mezclarlo con la caja del día daría cifras que no cuadrarían con el arqueo.

Lo que **sí** aparece donde siempre: el material de alquiler que volvió roto, que
sale en las mermas del periodo como cualquier otra merma.

Si filtras el informe por categoría, el apartado de eventos desaparece: un evento
mezcla categorías y repartirlo entre ellas sería inventar.

---

## 5. El número que ve la clienta

El presupuesto y el resto de documentos se numeran `EVENTO/2026/0001`. Si tu tienda
ya tenía presupuestos emitidos con el prefijo antiguo (`BODA/2026/0001`), esos
conservan su número: solo cambia el prefijo de los que se emitan a partir de ahora,
nunca se renumera lo ya emitido.
