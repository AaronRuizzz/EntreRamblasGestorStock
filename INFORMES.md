# Informes y exportaciones

La propietaria abre **Informes → Informe mensual (PDF)**, selecciona las fechas
y, opcionalmente, una categoría. Las fechas incluyen ambos días y se interpretan
en la zona Europe/Madrid. Se puede generar el PDF, descargar solo las ventas CSV
o pulsar **Exportar estadísticas (ZIP de CSV)**.

El ZIP contiene resumen, ventas por producto, ventas diarias, mermas y stock
actual. Incluye cobros cuando se consultan todas las categorías. Cada archivo
puede importarse en una hoja de cálculo usando UTF-8, separador punto y coma y
decimales con punto. Los nombres que podrían convertirse en fórmulas llevan un
apóstrofo de protección.

Las ventas netas descuentan devoluciones. El margen bruto resta el coste histórico
vendido; el margen después de mermas resta además el coste de las mermas del
periodo. El resumen avisa de registros sin coste histórico: revisa los datos
antiguos antes de interpretar sus márgenes.

Los cobros se agrupan por fecha del pago, que puede ser distinta de la venta.
Las salidas incluyen cambio y reembolsos. La cuenta de cliente aparece separada
y no se suma al efectivo cobrado. Con filtro de categoría se omite este archivo,
porque un pago mixto no tiene un reparto exacto entre categorías.

**El stock es el que existe al consultar el informe**, incluso si las fechas son
de un mes anterior. El resumen del ZIP incluye el momento de consulta en UTC.
Las entradas de proveedor representan mercancía recibida a coste, no pagos a
proveedores ni un resultado contable.

**El valor de stock se separa en vendible y caducado.** El caducado sigue
contando en el valor total (hasta que se dé de baja, ver más abajo), pero
aparece aparte para no confundir "lo que tengo" con "lo que puedo vender".

## Consumo de flor

**Informes → Consumo de flor** responde «cuántas rosas gasto de verdad»,
tallo a tallo: un ramo de 12 rosas cuenta como 12 rosas, no como «1 unidad de
Ramo a medida». Junta lo vendido suelto, lo que llevan los ramos y lo
entregado en eventos. Es informativo — ese coste ya está contado en el margen
de arriba, dentro de la línea que se cobró, así que no se suma dos veces. Las
mermas no se incluyen aquí: ya tienen su propio apartado, con sus motivos.

## Bajas de caducados

**Stock → Bajas de caducados**. El programa revisa cada día lo que ha
caducado más allá del margen configurado (Configuración → Dispositivos,
por defecto 2 días) y prepara una **propuesta** con el coste que se va a dar
de baja, a la vista. **No se confirma sola**: hay que revisarla y pulsar
**Dar de baja**. No se puede deshacer — un error se corrige con un recuento
físico, igual que el resto de ajustes de esta familia.

## Previsión de compra

**Stock → Previsión de compra**: elige la campaña (San Valentín, Día de la
Madre, Todos los Santos o fechas libres), cuántos años mirar atrás y un
margen de seguridad, y pulsa **Calcular**. Mira el consumo real de flor del
mismo periodo en años anteriores y propone comprar el máximo histórico con
margen, menos lo que ya hay sin caducar. **Crear pedido** rellena un pedido a
proveedor en borrador, agrupado por el proveedor habitual de cada producto;
lo que no tenga proveedor conocido se queda fuera, avisando cuál es.
El primer año que se usa una campaña no hay historial: la pantalla lo dice,
no inventa una cifra.
