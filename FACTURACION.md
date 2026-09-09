# Facturación española: qué se ha comprobado y qué falta decidir

Consulta realizada el **6 de septiembre de 2026** sobre fuentes oficiales (AEAT y
BOE). Recoge lo que dicen las normas y lo que hace hoy el programa. Revisado el
**9 de septiembre de 2026** con una lectura del código del ticket y de los
módulos disponibles en el motor (ver §2bis).

> **Esto no es asesoramiento fiscal.** El régimen concreto de la tienda (persona
> física o sociedad, recargo de equivalencia, tipos de IVA por artículo) lo
> determina la gestoría. Lo que sigue sirve para que la conversación con ella sea
> corta y concreta.

## 1. Ticket de venta = factura simplificada

La venta al por menor se documenta con **factura simplificada** (el ticket). Se
puede usar cuando el importe no pasa de **400 €** con IVA, y hasta **3.000 €** con
IVA en ventas al por menor, entre otros supuestos. Las **rectificativas** también
pueden ser simplificadas.

Contenido obligatorio (artículo 7 del RD 1619/2012) y estado en el programa:

| Requisito | ¿Lo imprime el ticket? |
|---|---|
| Número y, en su caso, serie | Sí — el número de pedido del TPV |
| Fecha de expedición (y de la operación, si difiere) | Sí |
| NIF y nombre del expedidor | Sí, si están rellenos en la ficha de la empresa |
| Descripción de los bienes | Sí |
| **Tipo impositivo** (y opcionalmente «IVA incluido») | Sí — se imprime el porcentaje, p. ej. `IVA 21%` |
| Contraprestación total | Sí |
| En rectificativas, referencia a la factura rectificada | Sí — línea `Rectifica el ticket …` |
| NIF y domicilio del **destinatario** | **No automático** |

Sobre la última fila: esos datos solo hacen falta cuando el cliente es empresario
o profesional que quiere deducir el IVA, o un particular que exige factura para
ejercer un derecho tributario. **Si un cliente pide factura con sus datos, hay que
emitirla desde el programa con el cliente identificado**, no basta el ticket. Conviene
acordar ese procedimiento con la gestoría antes de abrir.

**Cómo lo hace el programa, tras leer el código** (`models/mgs_config.py`,
`_mgs_pos_ticket`, y `models/mgs_escpos.py`): el ticket que sale por la impresora
térmica lo construye el servidor en ESC/POS, no el navegador. Imprime, en orden:
nombre de la tienda, dirección y `NIF:` (solo si la ficha de la empresa los tiene
rellenos), teléfono, número de ticket y fecha/hora, `Cliente:` si la venta lleva
cliente, la línea `Rectifica el ticket …` en las devoluciones, las líneas con
cantidad y precio, el TOTAL, el **desglose de IVA** por tipo (base y cuota,
recalculado desde los subtotales reales), los pagos con el cambio, un pie
configurable y el número de ticket en código de barras. **No imprime**: QR,
huella, número de registro de facturación, ni NIF/domicilio del cliente.

- **El NIF solo aparece si `company.vat` está relleno.** Hoy la empresa de la base
  no tiene los datos fiscales reales puestos: hasta que se rellenen, el ticket
  sale sin NIF (punto 2 de la §4).

**Pendiente de confirmar con la gestoría:**

- Que la **numeración** del TPV (una serie por caja/sesión) le vale como serie
  correlativa. Si prefiere otra serie, se configura antes de la primera venta:
  cambiarla después complica la trazabilidad.
- Los **tipos de IVA** por artículo (flor cortada, planta viva, jarrón,
  envoltorio, tarjeta). El programa **no elige el tipo**: obliga a indicarlo
  producto a producto en el alta de catálogo.
- Si la tienda está en **recargo de equivalencia**, cómo afecta a las compras y
  qué se espera del programa (hoy no lo contempla de forma específica).

## 2. Sistemas informáticos de facturación (SIF) y VERI\*FACTU

El Reglamento aprobado por el **RD 1007/2023** fija los requisitos que debe
cumplir el software de facturación: registro de facturación de alta y de
anulación, **huella o «hash» encadenada** con el registro anterior, **firma
electrónica** si el sistema no es VERI\*FACTU, **registro de eventos**, **código QR
en todas las facturas, también las simplificadas**, y **declaración responsable**
del fabricante del software.

**Plazos vigentes**, ampliados por el **Real Decreto-ley 15/2025, de 2 de
diciembre** (según la nota informativa de la AEAT):

| Obligado | Debe tener el SIF adaptado antes de |
|---|---|
| Entidades que presentan Impuesto sobre Sociedades | **1 de enero de 2027** |
| Resto de obligados tributarios | **1 de julio de 2027** |

### Estado real del programa

**Este programa NO es hoy un SIF conforme al RD 1007/2023.** No genera registros
de facturación encadenados por huella, no firma electrónicamente, no lleva
registro de eventos, no imprime QR de verificación y no cuenta con declaración
responsable. El módulo propio `mi_gestor_stock` y `l10n_es` a secas **no aportan
por sí solos** ese cumplimiento.

Qué significa en la práctica:

- Para **abrir la tienda ahora**, con tickets simplificados, esto no impide
  facturar; la obligación tiene las fechas de arriba.
- **Antes de esas fechas** hay que decidir una de estas vías, con la gestoría y
  con quien mantenga el programa (ver el detalle técnico en §2bis):
  1. **Activar los módulos de VERI\*FACTU que ya trae el motor** (`l10n_es_edi_verifactu`
     y `l10n_es_edi_verifactu_pos`) y añadir al ticket térmico lo que esos
     módulos ponen solo en el recibo de pantalla. Es la vía con menos código
     nuevo, pero **no resuelve la declaración responsable del fabricante**.
  2. Implementar VERI\*FACTU en el propio módulo, con su declaración responsable.
  3. Emitir a través de un sistema ya conforme (otro TPV/facturador homologado).
- La AEAT ofrece además un **formulario web gratuito** para quien no tenga sistema
  propio de facturación; no encaja con un TPV que emite tickets en mostrador, pero
  conviene conocerlo como salida de emergencia.

**No dar por hecho que las fechas siguen igual**: ya se han ampliado dos veces.
Vuelve a mirar la nota informativa de la AEAT antes de planificar.

## 2bis. VERI\*FACTU: qué hay ya en el motor y qué faltaría (revisión del 9-sep-2026)

Este Odoo 18 Community **ya incluye en el motor** (carpeta `odoo/addons/`, todos
LGPL-3) los módulos oficiales de la localización española para VERI\*FACTU:

| Módulo | Qué aporta |
|---|---|
| `l10n_es_edi_verifactu` | Registro de facturación encadenado por **huella SHA-256** con el registro anterior, secuencia de cadena por compañía, bloqueo de borrado de documentos encadenados, y generación del **QR** tributario. |
| `l10n_es_edi_verifactu_pos` | Lleva lo anterior al TPV: campos en `pos.order` (estado VERI\*FACTU, avisos, `l10n_es_edi_verifactu_qr_code`), soporte de **tickets no facturados** (que es el caso de una floristería de mostrador), y popup de motivo en las devoluciones. `auto_install = True`: se instala solo en cuanto están sus dependencias, que aquí ya están (`l10n_es` + `point_of_sale` + `certificate`). |

Lo que **NO** queda resuelto solo con activarlos, y habría que hacer:

1. **El QR en el papel.** `l10n_es_edi_verifactu_pos` inyecta el QR en la
   plantilla `point_of_sale.OrderReceipt`, que es el recibo **de pantalla**. El
   ticket que de verdad sale por la impresora térmica lo construye
   `_mgs_pos_ticket` en Python (`models/mgs_config.py`) y **no pasa por esa
   plantilla**: instalar el módulo pondría el QR en la pantalla pero **no en el
   papel**. Hay que añadir en `_mgs_pos_ticket` una llamada a `doc.qr(...)` —
   primitiva **ya implementada y hoy sin usar** en `models/mgs_escpos.py`
   (`def qr`, comando `GS ( k`)— alimentada con el dato del registro VERI\*FACTU,
   más la leyenda «VERI\*FACTU» y el identificador del registro.
2. **La declaración responsable del fabricante del software**, que exige el
   RD 1007/2023 y que ningún módulo del motor aporta. Es un documento formal de
   quien desarrolla/mantiene el programa, no código.
3. **Configurar el certificado** de la empresa en el módulo `certificate` y dar
   de alta los datos fiscales reales (§4).
4. **Probarlo de punta a punta**: emisión, huella encadenada entre tickets
   consecutivos, devolución con su motivo, y cotejo del QR.

Conclusión: el salto es **más corto de lo que decía este documento** (hay una
implementación oficial en el propio código instalado, no solo «módulos de
terceros»), pero **sigue siendo un proyecto con su propia planificación**, sobre
todo por la declaración responsable y por el QR en el ticket térmico.

## 3. Factura electrónica obligatoria entre empresas (B2B)

El **Real Decreto 238/2026, de 25 de marzo** desarrolla la factura electrónica
obligatoria **entre empresarios y profesionales**. Dos cosas importantes para esta
tienda:

- **No se aplica a las ventas a consumidor final (B2C)**, que es la práctica
  totalidad de una floristería de mostrador.
- **Exceptúa las facturas simplificadas del comercio minorista**, salvo las
  «cualificadas» del RD 1619/2012.

Los plazos se cuentan desde una **orden ministerial** aún pendiente: 12 meses
para quien factura más de 8 millones de euros al año y 24 meses para el resto. Es
decir: relevante solo si la tienda empieza a facturar a otras empresas de forma
habitual.

## 4. Qué hacer antes de producción

1. Llevar este documento a la gestoría y cerrar: régimen de la tienda, tipos de
   IVA por familia de producto, serie de numeración y procedimiento cuando un
   cliente pide factura completa.
2. Rellenar en el programa el **NIF, nombre y domicilio** de la tienda: sin ellos el
   ticket sale incompleto.
3. Decidir la vía de cumplimiento SIF/VERI\*FACTU y ponerle fecha, con margen
   sobre el plazo que aplique.
4. Volver a comprobar plazos y normas en las fuentes oficiales antes de ejecutar
   esa decisión.

## Fuentes

- [AEAT — Sistemas Informáticos de Facturación (SIF) y VERI\*FACTU](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu.html)
- [AEAT — Nota informativa: ampliación del plazo de adaptación de los SIF](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/nota-informativa-ampliacion-plazo-adaptacion-facturacion.html)
- [AEAT — Cuestiones generales SIF/VERI\*FACTU](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/cuestiones-generales.html)
- [BOE — Real Decreto 1007/2023](https://www.boe.es/buscar/act.php?id=BOE-A-2023-24840)
- [BOE — Real Decreto 1619/2012 (Reglamento de facturación)](https://www.boe.es/buscar/act.php?id=BOE-A-2012-14696)
- [AEAT — Facturas simplificadas](https://sede.agenciatributaria.gob.es/Sede/ayuda/manuales-videos-folletos/manuales-practicos/folleto-actividades-economicas/5-impuesto-sobre-valor-anadido/5_10-facturas/5_10_6-facturas-simplificadas.html)
- [BOE — Real Decreto 238/2026 (factura electrónica B2B)](https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-7295)
