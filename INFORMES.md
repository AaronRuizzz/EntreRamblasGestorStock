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
