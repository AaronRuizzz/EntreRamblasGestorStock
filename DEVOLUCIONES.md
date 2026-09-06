# Devoluciones en tienda

Desde el menú del TPV abre **Pedidos**, selecciona **Pagado** y busca el ticket
original. Selecciona el producto y la cantidad a devolver, pulsa **Reembolso**
y entra en **Pago**. Registra el método por el que se devuelve el importe.

Al pulsar **Validar**, el programa pregunta por el estado de cada línea de stock:

- **Recuperable: vuelve al stock** devuelve las unidades a sus partidas originales.
- **Deteriorada: registrar merma** registra la devolución y una baja vinculada;
  esas unidades no quedan disponibles para otra venta.

La elección se aplica a toda la cantidad de esa línea. Si parte es recuperable
y parte está deteriorada, realiza dos devoluciones parciales del ticket original.
El programa controla la cantidad pendiente de devolución.

Puedes cerrar el selector para volver a revisar sin validar. Después de confirmar
no se puede cambiar la marca de deterioro. Las mermas automáticas aparecen en
**Stock → Mermas** con motivo **Devolución no recuperable**, referencia del ticket,
movimiento devuelto y persona que lo registró. No registres otra merma manual
por esa misma mercancía.

Si se pierde la conexión después de validar, restablece el servidor y vuelve a
validar el mismo pedido; no crees otro reembolso ni repitas la entrega de dinero.
Los reintentos conservan la operación y no duplican la merma.

El datáfono es independiente: registrar tarjeta en Odoo no devuelve el dinero en
el terminal. Tramita el reembolso en el datáfono y comprueba su resultado.
