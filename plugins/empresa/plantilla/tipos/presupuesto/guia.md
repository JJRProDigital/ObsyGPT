# Guía: presupuesto

## Campos mínimos del brief
- Cliente (razón social, contacto, dirección fiscal)
- Alcance: qué se entrega, con qué límites y qué queda fuera
- Conceptos con código de `datos-maestros/tarifas.md` y cantidades
- Descuento solicitado o acordado (y quién lo autoriza)
- Plazo de entrega deseado
- Fecha de emisión y número de referencia
- Condiciones especiales (si hay; requieren aprobación)

## Estructura
1. Cabecera: empresa, cliente, número, fecha y validez.
2. Resumen del alcance (3-5 líneas) y exclusiones.
3. Tabla de conceptos: código, descripción, cantidad, precio unitario, importe.
4. Totales: base imponible, descuento (si procede), IVA, total.
5. Plazos de entrega y forma de pago (de `condiciones.md`).
6. Cláusulas de texto fijo (copiadas tal cual).
7. Aceptación: espacio para fecha y firma del cliente.

## Reglas de cálculo
- Los precios unitarios se toman únicamente de `tarifas.md`.
- Importe de línea = cantidad × precio unitario. Redondeo a 2 decimales por línea.
- Descuento sobre la base, antes de impuestos, solo si está permitido en `tarifas.md`.
- IVA aplicado sobre la base con descuento.
- Si un concepto no tiene precio en `tarifas.md`: parar y preguntar.

## Formato de salida
`borrador.md` con la tabla en Markdown. Si el entorno permite crear archivos y
la empresa usa Word, PDF o Excel, indicarlo aquí: (formato final: ___).

## Checklist de revisión
- [ ] Todos los precios coinciden con `tarifas.md`
- [ ] Cada línea, subtotal, IVA y total recalculados y correctos
- [ ] Descuento dentro de lo permitido y autorizado
- [ ] Validez, plazos y forma de pago coinciden con `condiciones.md`
- [ ] Cláusulas fijas copiadas sin cambios
- [ ] Alcance y exclusiones claros
- [ ] Datos del cliente completos
- [ ] Sin compromisos fuera de las reglas duras
- [ ] Marcado para aprobación humana
