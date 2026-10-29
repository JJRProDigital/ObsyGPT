<p class="os-kicker" markdown>Trabajar</p>
# Skills

Las skills siguen el **estándar Agent Skills**: cada una vive en `agents/skills/<nombre>/SKILL.md` con frontmatter + Markdown y recursos opcionales. Se editan desde la UI y se invocan desde el chat.

## La biblioteca

En la vista **Skills** tienes tres pestañas:

- **Biblioteca** — skills instaladas, con agentes que las tienen activadas.
- **Editor** — crea o edita skills con frontmatter (nombre, descripción, argumentos, triggers) y cuerpo en Markdown.
- **Generador** — describe lo que quieres en lenguaje natural y ObsyGPT redacta el borrador de la skill por ti.

![Skills](assets/screenshots/skills.png)

## Estructura de una skill

```markdown
---
name: revisar-pr
description: Revisa un pull request y devuelve feedback estructurado
argument-hint: <url_o_numero_del_pr>
triggers: [user, model]
---

Instrucciones para el agente...
```

- **`triggers: user`** — puede invocarse con `/revisar-pr 123`.
- **`triggers: model`** — el modelo puede usarla por su cuenta si el encaje es relevante.
- Los recursos adicionales (plantillas, scripts) viven junto al `SKILL.md`.

## Invocación

- Desde el chat: `/nombre_skill tarea` o con la **paleta de skills** (`Alt` + espacio).
- Por agente: activa o desactiva skills en **Ajustes > Agentes > Skills**.

## Organización en disco

```text
agents/skills/
  revisar-pr/
    SKILL.md
    resources/
      checklist.md
```

Las skills se recargan al guardar; no hace falta reiniciar el backend.
