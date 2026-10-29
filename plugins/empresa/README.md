# Harness de Empresa

Plugin de redacción para ObsyGPT: emails, presupuestos y contenido con la voz de la empresa, precios y condiciones de una única fuente, y revisión humana obligatoria antes de entregar nada.

Instala 4 skills y un agente:

| Skill | Invocación | Qué hace |
|---|---|---|
| `brief` | `/empresa-brief <tipo> <encargo>` | Convierte el encargo en un brief aprobable |
| `redactar` | `/empresa-redactar <slug>` | Escribe el borrador de un brief aprobado |
| `revisar` | `/empresa-revisar <slug>` | Revisa con la checklist del tipo y emite veredicto |
| `onboarding` | `/empresa-onboarding` | Entrevista para rellenar `empresa/` y `datos-maestros/` |

## Instalación

1. En ObsyGPT: **Ajustes > Administración > Plugins > Catálogo local** e instala **Harness de Empresa**.
2. En **Ajustes > Administración > Agentes > Redactor de Empresa**: asigna proveedor y modelo, y habilita solo estas herramientas:
   - `read_file`
   - `list_dir`
   - `write_file`
   - `edit_file`
3. En **Proyectos > Crear desde una plantilla > Empresa**: un clic crea el proyecto con su carpeta, los archivos de `plantilla/` y las instrucciones de `AGENTS.md`.

No hace falta copiar carpetas ni usar la terminal. Cada usuario puede repetir el paso 3 para tener su propio proyecto.

## Uso

```
/empresa-brief email Responder a un cliente que pide rebaja del 20 %
```

El brief queda en `trabajos/AAAA-MM-DD-email-<asunto>/brief.md`. Resolvé las preguntas abiertas y cambiá a mano `estado: borrador` por `estado: aprobado` con tu nombre y la fecha. Después:

```
/empresa-redactar 2026-10-28-email-rebaja-cliente
/empresa-revisar 2026-10-28-email-rebaja-cliente
```

Cada `write_file` abre una aprobación en el chat: ObsyGPT pausa el agente hasta que aceptás. El agente nunca envía ni publica nada.

Abrí un chat dentro del proyecto y elegí **Redactor de Empresa** en el selector de agente.

## Reglas del diseño

- **Los números salen de `datos-maestros/`.** Si falta un precio o plazo, el agente pregunta; nunca lo inventa.
- **El brief se aprueba antes de redactar.** `empresa-redactar` aborta si `estado` no es `aprobado`.
- **Todo borrador queda pendiente de revisión humana.** El estado lo cambia una persona.
- **Cada corrección humana repetida se convierte en una regla o un ejemplo.** Se anota en `empresa/errores-vistos.md`.

## Límites conocidos

- Las skills son globales y se asignan por agente, no por proyecto: usá el agente **Redactor de Empresa** dentro del proyecto **Empresa**.
- El agente instalado no trae proveedor ni modelo: sin asignarlos no aparece usable en el chat.
- `write_file` y `edit_file` no vienen habilitados por defecto: sin el permiso del paso 3 el agente no puede crear briefs ni borradores.
- `resources` de las skills va vacío a propósito: los datos viven en la carpeta del proyecto, no dentro de la skill.
- No tiene conectores ni terminal a propósito: el harness no debe tener forma de enviar, publicar ni tocar nada fuera de su carpeta.

## Mantenimiento

| Qué | Quién | Cuándo |
|---|---|---|
| Tarifas y condiciones (`datos-maestros/`) | Comercial / administración | En cada cambio y revisión trimestral |
| Voz y estilo, ejemplos (`empresa/`, `ejemplos/`) | Marketing / comunicación | Trimestral |
| Reglas duras (`empresa/reglas-duras.md`) | Legal / dirección | Cada cambio normativo y anualmente |
| Errores vistos (`empresa/errores-vistos.md`) | Quien revisa | Continuo |
