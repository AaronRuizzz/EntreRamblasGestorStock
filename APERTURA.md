# Puesta en marcha: catálogo y existencias iniciales

Estos dos pasos se hacen **una sola vez**, antes de empezar a vender. Después,
la mercancía entra siempre por **Recepción** y se corrige por **Recuento físico**.
Los dos menús están en **Stock** y solo los ve la propietaria.

## 1. Alta de catálogo (Stock → Alta de catálogo)

Da de alta las fichas de producto desde una hoja de cálculo. **No registra
existencias**: eso es el paso 2.

1. Pulsa **Descargar plantilla**. Se baja `plantilla-catalogo.csv` con la
   cabecera correcta y unas líneas de ayuda que empiezan por `#`.
2. Rellena una fila por producto y borra las líneas de ayuda. Guarda como CSV.
3. Vuelve a la pantalla, sube la hoja y pulsa **Comprobar hoja**.
4. Corrige lo que salga en rojo y vuelve a subirla. Cuando no quede ninguna fila
   con problemas, pulsa **Importar catálogo**.

### Columnas

| Columna | Obligatoria | Qué se escribe |
|---|---|---|
| `codigo` | No | El código de barras del producto. **Si se deja vacío**, el programa genera un código interno EAN-13 y luego imprimes su etiqueta desde la ficha del producto. |
| `nombre` | Sí | Nombre que se ve en caja. |
| `categoria` | No | Se usa para agrupar en el panel y filtrar informes. |
| `unidad` | No | `Unidades` si se deja vacío. Se aceptan también `Docenas`, `Kg`, `Gramos`, `Litros`, `Metros`, `Cm`, `Tallos`. |
| `precio_venta` | Sí | PVP con IVA incluido o no, según cómo esté configurada la tienda. Admite `2,50` y `2.50`. |
| `coste` | Sí | Lo que cuesta la unidad al comprarla. Es la base del margen de los informes. |
| `iva` | Sí | Solo `0`, `4`, `10` o `21`. |

### Por qué se comprueba todo antes

Si una sola fila está mal, **no se importa ninguna**. Es preferible corregir la
hoja a quedarse con medio catálogo dentro y tener que buscar qué entró y qué no.

La comprobación señala: nombres o códigos repetidos dentro de la hoja, nombres o
códigos que ya existen en el programa, precios o costes que no son números o son
negativos, IVA fuera de la lista y categorías o unidades que no existen.

Dos avisos se pueden aceptar a propósito, marcando su casilla:

- **Acepto precios o costes a cero.** Un cero casi siempre es una casilla que se
  quedó vacía; si de verdad hay artículos sin precio, marca la casilla.
- **Crear las categorías que no existan.** Sin marcarla, una categoría mal
  escrita se señala como error en vez de crear una categoría nueva por una errata.
  Al marcarla, el resumen dice exactamente qué categorías se van a crear.

### El IVA lo decides tú

El programa **no elige** el tipo: obliga a escribirlo en cada fila. El tipo que
corresponde a cada artículo (flor cortada, planta, jarrón, envoltorio, tarjeta)
depende de la normativa vigente y del régimen de la tienda. **Consúltalo con tu
gestoría antes de importar**: cambiar el IVA después obliga a revisar tickets ya
emitidos.

### Qué queda configurado en cada ficha

Todos los productos se crean como los crea la Recepción: almacenables, a la
venta, disponibles en el TPV, **con partidas (lotes) automáticas y control de
caducidad**. Sin eso el TPV no sabría qué partida descontar ni avisar de
caducidades.

## 2. Existencias iniciales (Stock → Existencias iniciales)

Registra la mercancía que ya está en la tienda el día que arranca el programa.

1. Crea una apertura y elige la **ubicación** (normalmente `WH/Stock`).
2. Añade una línea por partida: producto, cantidad, coste unitario y, si aplica,
   fecha de caducidad. **Marca «Revisado»** en cada línea después de comprobarla.
3. Pulsa **Aplicar apertura** y confirma.

Cada línea genera **una partida propia** (`INI-…`) con su coste y su caducidad,
y un **ajuste de inventario**. No es una compra: no aparece como gasto de
reposición en el informe mensual, porque esa mercancía ya estaba pagada.

Puntos importantes:

- **Una misma flor comprada a dos precios son dos líneas.** Así el TPV descuenta
  primero la que caduca antes y el informe calcula el margen con el coste real.
- **La caducidad se guarda al final del día**, en hora de Madrid.
- **Solo admite productos sin existencias ni movimientos anteriores.** En cuanto
  un producto ha entrado por Recepción o se ha vendido, la apertura lo rechaza:
  para eso está el Recuento físico. Si una recepción se está confirmando en ese
  mismo momento, la apertura espera a que termine y luego la rechaza; no puede
  colarse y duplicar el stock.
- **La ubicación tiene que estar dentro del almacén.** Una ubicación interna
  suelta guardaría existencias que el informe de stock ve y el resto del programa
  (avisos, panel, TPV) no.
- **Una apertura aplicada no se edita ni se borra.** Volver a pulsar aplicar no
  duplica nada. Si hay que corregirla, se hace con un recuento físico.

## Orden recomendado el día de la puesta en marcha

1. Alta de catálogo.
2. Imprime las etiquetas de los productos que se quedaron sin código.
3. Existencias iniciales, ubicación por ubicación.
4. Comprueba el panel de Stock: las cantidades tienen que cuadrar con la tienda.
5. Copia de seguridad manual antes de la primera venta.
