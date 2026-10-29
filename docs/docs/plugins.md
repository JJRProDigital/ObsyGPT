<p class="os-kicker" markdown>Extender</p>
# Plugins

Un **plugin** es un paquete compartible que agrupa skills, servidores MCP y definiciones de sub-agentes para instalarlos de una vez.

## Formato

Cada plugin vive en una carpeta con su manifiesto `plugin.json` que declara qué incluye. El catálogo local del repo está en `plugins/`.

## Instalación

**Ajustes > Administración > Plugins**:

- **Catálogo local** — plugins incluidos con el repo, un clic.
- **Marketplaces git** — añade la URL de un repositorio que sirva plugins, refresca el índice e instala desde ahí.

Si un plugin necesita un conector que aún no has configurado, la UI te lo avisa antes de instalar.

## Desinstalar

Desde la misma pantalla puedes desinstalar cualquier plugin instalado: se retiran sus skills, MCPs y sub-agentes asociados sin tocar el resto de tu configuración.

## Crear tu propio plugin

1. Crea una carpeta con `plugin.json` declarando skills, MCPs y sub-agentes.
2. Copia las skills siguiendo el [formato estándar](skills.md#estructura-de-una-skill).
3. Súbela a tu marketplace git o añádela al catálogo local `plugins/`.

## Plantillas de proyecto

Un plugin puede incluir una carpeta de plantilla para crear proyectos completos desde la interfaz: carpeta de trabajo, archivos e instrucciones.

```json
{
  "templates": [
    {
      "name": "empresa",
      "title": "Empresa",
      "description": "Kit de redacción listo para usar.",
      "path": "plantilla",
      "instructions": "AGENTS.md"
    }
  ]
}
```

- `path` es la carpeta dentro del plugin que se copia al proyecto.
- `instructions` es el archivo de esa carpeta que se usa como instrucciones del proyecto (opcional).

Los proyectos creados desde plantilla aparecen en **Proyectos > Crear desde una plantilla** y su carpeta vive en el workspace del usuario. Para que el catálogo local funcione en Docker, el servicio `backend` debe montar `./plugins:/plugins`.
