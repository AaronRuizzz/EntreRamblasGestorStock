# Facturación española: qué se ha comprobado y qué falta decidir

Consulta realizada el **6 de septiembre de 2026** sobre fuentes oficiales (AEAT y
BOE). Recoge lo que dicen las normas y lo que hace hoy el programa. Revisado el
**9 de septiembre de 2026** con una lectura del código del ticket y de los
módulos disponibles en el motor (ver §2bis).

> **Esto no es asesoramiento fiscal.** El régimen concreto de la tienda (persona
> física o sociedad, recargo de equivalencia, tipos de IVA por artículo) lo
> determina la gestoría. Lo que sigue sirve para que la conversación con ella sea
> corta y concreta.

> **VeriFactu queda fuera de esta entrega, por decisión de la propietaria.** El
> TPV se conserva tal cual, **sin activar envíos a la AEAT y sin implementar un
> SIF alternativo**. Esta entrega es técnica: instalar el programa, igualar las
> instalaciones y dejar las actualizaciones firmadas. **No acredita cumplimiento
> fiscal.** Antes de usar el TPV como facturador definitivo hay que cerrar con la
> gestoría el punto 3 de la sección 4 (régimen, domicilio fiscal, tipos de IVA,
> serie de numeración y vía de cumplimiento SIF/VeriFactu) y ponerle fecha con
> margen sobre el plazo que aplique.

> **La facturación actual no puede darse por validada legalmente.** Que la dueña
> o su gestoría presenten correctamente sus impuestos **no sustituye** los
> requisitos del RD 1007/2023 (huella encadenada, firma o remisión VeriFactu,
> registro de eventos, QR). Ninguna afirmación de este repositorio del tipo
> «basta esperar a 2027» debe tomarse como que el sistema ya cumple: solo
> significa que la **obligación del usuario** aún no ha vencido (ver los matices
> de plazos abajo, incluido el de julio de 2025 para quien produce o comercializa
> el software).

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
configurable, un QR a las reseñas de Google y a la web de la tienda (si están
configurados en Configuración → Dispositivos → «Enlace a las reseñas de
Google») y el número de ticket en código de barras. **No imprime**: huella,
número de registro de facturación, ni NIF/domicilio del cliente — eso sigue
siendo lo que distingue el ticket de una factura completa (ver más abajo).

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

## 1bis. Factura completa (cuando el ticket no basta)

Añadido en la versión 18.0.7.0.0, sobre `account.move` de contabilidad
(`models/mgs_account_move.py`), sin tocar el ticket ni activar VERI\*FACTU:

- **No se deja confirmar una factura o rectificativa a la que le falte el NIF,
  la razón social, el domicilio completo (calle, código postal, ciudad y
  país) o el plazo de pago de la tienda o del cliente** (art. 6.1 RD
  1619/2012): se comprueba en `_post()`, así que se aplica **tanto** al
  confirmar desde el backend **como** al cobrar con factura desde el TPV
  (antes solo cubría el backend: el TPV llama a `_post()` directamente, sin
  pasar por `action_post()`, y se colaba sin comprobar nada).
- El **contenido** (NIF y domicilio del emisor, desglose de base/tipo/cuota de
  IVA por cada tipo) lo sigue poniendo la plantilla **nativa** de Odoo
  (`web.external_layout` y `account.document_tax_totals`) cuando esos datos
  están rellenos: no se ha duplicado ese trabajo. Lo único que la plantilla
  nativa no señalaba de forma legible es a qué factura rectifica una
  rectificativa (llevaba la referencia técnica «Reversión de: …», que cumple
  la letra pero no salta a la vista): se añade un aviso «Rectifica la factura
  …» arriba del documento (`report/mgs_account_invoice_report.xml`).
- El botón de factura del TPV genera este PDF con `action_mgs_invoice_pdf` y
  lo guarda en la carpeta **Facturas** (Configuración → Dispositivos →
  «Carpetas de salida»), no en Descargas.
- **Forma de pago**: a los particulares se les pone «Pago inmediato» (al
  contado) por defecto al dar de alta la ficha (`models/res_partner.py`); a
  las empresas se les deja elegir. El TPV nativo forzaba
  `invoice_payment_term_id: False` en toda factura que emitía —se ha
  corregido para que tome la del cliente (`models/mgs_pos_stock.py`,
  `_prepare_invoice_vals`)—. Plazo y vencimiento también se pueden consultar
  y cambiar (mientras la factura siga en borrador) desde Informes →
  Clientes.
- **Bug real de Odoo (Community) corregido, no nuestro**: pagar con factura
  desde el TPV lanzaba `AttributeError: 'account.move.line' object has no
  attribute 'deferred_start_date'`. `account_edi_ubl_cii` incrusta SIEMPRE un
  Factur-X en el PDF de cualquier factura («Always silently generate a
  Factur-X… for inter-portability», no es opcional ni depende de ningún
  ajuste), y para construirlo lee `deferred_start_date`/`deferred_end_date`
  (periodificación de Enterprise, que esta instalación no tiene) sin
  comprobar antes si el campo existe —al contrario que otro punto del mismo
  módulo, que sí lo comprueba—. Se ha corregido con la misma comprobación,
  heredando `account.edi.cii` (`models/mgs_account_move.py`,
  `AccountEdiCii._cii_get_billing_specified_period_node`). No cambia nada
  del contenido legal de la factura: el Factur-X sigue generándose igual,
  solo que sin reventar cuando faltan esos dos campos.

**Esto sigue sin ser un sistema conforme al RD 1007/2023** (sin huella
encadenada, sin firma, sin QR tributario, sin declaración responsable del
fabricante): mejora el CONTENIDO de la factura, no cambia nada de lo que
dice la §2 sobre VERI\*FACTU y el plazo de julio de 2025 para quien
comercializa el software.

## 2. Sistemas informáticos de facturación (SIF) y VERI\*FACTU

El Reglamento aprobado por el **RD 1007/2023** fija los requisitos que debe
cumplir el software de facturación: registro de facturación de alta y de
anulación, **huella o «hash» encadenada** con el registro anterior, **firma
electrónica** si el sistema no es VERI\*FACTU, **registro de eventos**, **código QR
en todas las facturas, también las simplificadas**, y **declaración responsable**
del fabricante del software.

**Plazos vigentes**. Los de los **usuarios** se ampliaron por el **Real
Decreto-ley 15/2025, de 2 de diciembre** (según la nota informativa de la AEAT).
El de **productores y comercializadores** de software **no se movió**:

| Obligado | Debe tener el SIF adaptado antes de |
|---|---|
| **Productores y comercializadores** de sistemas de facturación (deben *ofrecer* el producto ya adaptado) | **29 de julio de 2025** — 9 meses desde la Orden HAC/1177/2024; el RDL 15/2025 **no** amplió este plazo |
| Entidades que presentan Impuesto sobre Sociedades | **1 de enero de 2027** |
| Resto de obligados tributarios | **1 de julio de 2027** |

**Por qué importa la primera fila aquí.** Un sistema hecho a medida y usado solo
por quien lo desarrolla se rige por el plazo del usuario («sistema de desarrollo
propio»). Pero si el programa **se entrega o se comercializa a un tercero** —aquí,
la floristería— la AEAT lo trata como producto comercializado, y entonces
aplican la declaración responsable del fabricante y el plazo de julio de 2025.
**Cuál de los dos casos es este no está resuelto** y hay que plantearlo
expresamente a la gestoría y a quien conste como responsable del software. No dar
por hecho que, por ser «a medida», el plazo es 2027.

### Estado real del programa

**Este programa NO es hoy un SIF conforme al RD 1007/2023.** No genera registros
de facturación encadenados por huella, no firma electrónicamente, no lleva
registro de eventos, no imprime QR de verificación y no cuenta con declaración
responsable. El módulo propio `mi_gestor_stock` y `l10n_es` a secas **no aportan
por sí solos** ese cumplimiento.

Qué significa en la práctica:

- El programa **funciona** y emite tickets simplificados, pero hacerlo **no
  equivale a cumplir** el RD 1007/2023. La única lectura correcta de «los plazos
  de usuario son 2027» es que la AEAT todavía no puede sancionar al usuario por
  ello; no que el sistema esté conforme ni «validado».
- Si el programa se considera **comercializado** (entregado a la floristería como
  producto), el plazo del fabricante para ofrecerlo adaptado **ya venció**
  (29-07-2025). Ese punto hay que aclararlo antes de seguir usándolo como
  facturador; ver la primera fila de la tabla de plazos.
- **Antes de las fechas que apliquen** hay que decidir una de estas vías, con la
  gestoría y con quien conste como responsable del programa (detalle técnico en
  §2bis):
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
   sobre el plazo que aplique. Incluir en esa conversación **si el programa se
   considera de desarrollo propio o comercializado** (afecta al plazo y a la
   declaración responsable — ver §2). Esta entrega **no** activa VeriFactu: es
   una decisión aplazada a propósito, no un descuido.
4. Volver a comprobar plazos y normas en las fuentes oficiales antes de ejecutar
   esa decisión.

## Fuentes

- [AEAT — Sistemas Informáticos de Facturación (SIF) y VERI\*FACTU](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu.html)
- [AEAT — Nota informativa: ampliación del plazo de adaptación de los SIF](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/nota-informativa-ampliacion-plazo-adaptacion-facturacion.html)
- [AEAT — Cuestiones generales SIF/VERI\*FACTU](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/cuestiones-generales.html)
- [AEAT — FAQ: cuestiones generales, ámbitos de aplicación (desarrollo propio vs. comercializado, plazo de productores/comercializadores 29-07-2025)](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/preguntas-frecuentes/cuestiones-generales-ambitos-aplicacion.html)
- [AEAT — Manual práctico IVA 2025: sistemas informáticos de facturación](https://sede.agenciatributaria.gob.es/Sede/ayuda/manuales-videos-folletos/manuales-practicos/manual-iva-2025/capitulo-01-novedades-destacar-2025/verifactu.html)
- [BOE — Orden HAC/1177/2024 (desarrolla el RD 1007/2023; plazo de 9 meses para productores/comercializadores)](https://www.boe.es/buscar/act.php?id=BOE-A-2024-22138)
- [BOE — Real Decreto 1007/2023](https://www.boe.es/buscar/act.php?id=BOE-A-2023-24840)
- [BOE — Real Decreto 1619/2012 (Reglamento de facturación)](https://www.boe.es/buscar/act.php?id=BOE-A-2012-14696)
- [AEAT — Facturas simplificadas](https://sede.agenciatributaria.gob.es/Sede/ayuda/manuales-videos-folletos/manuales-practicos/folleto-actividades-economicas/5-impuesto-sobre-valor-anadido/5_10-facturas/5_10_6-facturas-simplificadas.html)
- [BOE — Real Decreto 238/2026 (factura electrónica B2B)](https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-7295)
