<p class="os-kicker" markdown>Extender</p>
# Harness de Empresa

Plugin de redacción con la voz de la empresa: emails, presupuestos y contenido, con precios y condiciones de una única fuente y **revisión humana obligatoria** antes de entregar nada.

## Qué instala

| Skill | Invocación | Qué hace |
|---|---|---|
| `brief` | `/empresa-brief <tipo> <encargo>` | Convierte el encargo en un brief aprobable |
| `redactar` | `/empresa-redactar <slug>` | Escribe el borrador de un brief aprobado |
| `revisar` | `/empresa-revisar <slug>` | Revisa con la checklist del tipo y emite veredicto |
| `onboarding` | `/empresa-onboarding` | Entrevista para rellenar `empresa/` y `datos-maestros/` |

Y un agente, **Redactor de Empresa**, con las cuatro skills asignadas.

## Instalación

1. **Ajustes > Administración > Plugins > Catálogo local** e instala **Harness de Empresa**.
2. **Ajustes > Administración > Agentes > Redactor de Empresa**: asigna proveedor y modelo, y habilita `read_file`, `list_dir`, `write_file` y `edit_file`.
3. **Proyectos > Crear desde una plantilla > Empresa**: un clic crea el proyecto con su carpeta, los archivos de la plantilla y las instrucciones.

Repetible: cada usuario puede crear su propio proyecto desde la misma plantilla sin tocar archivos ni la terminal.

## Flujo

```text
/empresa-brief email Responder a un cliente que pide rebaja del 20 %
  → trabajos/AAAA-MM-DD-email-<asunto>/brief.md  (estado: borrador)
  → una persona resuelve las Preguntas abiertas y pone estado: aprobado
/empresa-redactar <slug>   → borrador.md  (pendiente de revisión humana)
/empresa-revisar <slug>    → informe con checklist y veredicto
  → una persona lee, ajusta y envía
```

Cada `write_file` abre una aprobación en el chat: el agente se pausa hasta que la aceptás.

Abrí un chat dentro del proyecto y elegí el agente **Redactor de Empresa** en el selector superior: las skills se invocan con `/`.

## Estructura de la carpeta del proyecto

```text
AGENTS.md                 instrucciones del proyecto (pegar en Instrucciones)
empresa/                  perfil, voz y estilo, reglas duras, errores vistos
datos-maestros/           tarifas y condiciones: única fuente de precios
tipos/                    guía por tipo: email, presupuesto, contenido
ejemplos/                 piezas reales aprobadas
trabajos/                 briefs, borradores y revisiones por encargo
```

## Reglas del diseño

- Los números salen de `datos-maestros/`; si falta un dato, el agente pregunta.
- El brief se aprueba antes de redactar; `empresa-redactar` aborta si no está `aprobado`.
- Todo borrador queda pendiente de revisión humana y el agente nunca envía ni publica.
- Cada corrección repetida se anota en `empresa/errores-vistos.md`.

## Límites

- Las skills son por agente, no por proyecto: usá **Redactor de Empresa** dentro del proyecto.
- Sin proveedor/modelo asignado y sin `write_file` habilitado, el flujo no funciona.
- Sin conectores ni terminal a propósito: no hay forma de enviar ni de salir de la carpeta del proyecto.
