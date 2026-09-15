# Devoluciones en tienda

Desde el menú del TPV (☰) abre **Ventas y devoluciones** (antes «Pedidos»),
pestaña **Historial de tickets**, y busca el ticket original. Elige
**Devolver todo** o **Elegir productos** (tocando cada línea y poniendo la
cantidad con el numpad). El programa muestra el **importe que se va a
devolver** y pide **Confirmar devolución** antes de seguir. Después entra en
**Pago** y registra el método por el que se devuelve el importe.

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

El datáfono es independiente: registrar tarjeta en el programa no devuelve el
dinero en el terminal. Tramita el reembolso en el datáfono y comprueba su resultado.
