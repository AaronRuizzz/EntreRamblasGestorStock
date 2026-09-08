# Recuento físico de partidas

La propietaria accede desde **Stock → Recuento físico**. Haz el recuento en un
momento sin ventas, recepciones ni otras operaciones en la ubicación elegida.

1. Crea un recuento, elige la ubicación e indica el motivo.
2. Pulsa **Preparar partidas** para consultar las existencias registradas.
3. Cuenta cada partida, introduce su cantidad real y marca **Revisado**. Si no
   queda ninguna unidad, introduce cero y marca igualmente la revisión.
4. Aplica el recuento. El programa genera ajustes únicamente para las diferencias.

Si cambian las existencias o reservas de una partida preparada, el programa
rechaza el ajuste. Recarga las partidas y vuelve a contar: la recarga borra las
cantidades anotadas y las marcas de revisión. No se admiten cantidades negativas
ni inferiores a las unidades reservadas.

El historial conserva las cantidades consultadas y contadas, el motivo, la fecha,
la persona que aplicó el recuento y los movimientos de ajuste. Volver a pulsar
aplicar no duplica los movimientos. Para corregir un ajuste aplicado, crea otro
recuento.

Puedes cancelar un recuento sin aplicar: no cambia el stock y queda registrada
la persona y fecha de cancelación. Los recuentos iniciados se conservan.

## Alcance actual

Este flujo cuenta existencias propias ya registradas en ubicaciones internas;
excluye paquetes y mercancía de terceros. Las compras reales entran por recepción.
La carga inicial de catálogo y existencias tiene sus propias pantallas
(**Stock → Alta de catálogo** y **Stock → Existencias iniciales**, ver
[APERTURA.md](APERTURA.md)): no registres compras ficticias para introducir el
stock inicial ni uses el recuento para dar de alta partidas que nunca se
registraron.
