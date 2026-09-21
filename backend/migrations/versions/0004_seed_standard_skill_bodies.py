"""Seed standard SKILL.md content for built-in skills.

Revision ID: 0004_seed_standard_skill_bodies
Revises: 0003_agent_skill_standard
Create Date: 2026-09-15
"""

from alembic import op


revision = "0004_seed_standard_skill_bodies"
down_revision = "0003_agent_skill_standard"
branch_labels = None
depends_on = None


SKILLS = {
    "web_search": {
        "argument_hint": "Search query and optional result constraints.",
        "triggers": "ARRAY['user','model']::varchar[]",
        "body": """# Instrucciones principales
1. Convierte la tarea del usuario en una consulta de busqueda concreta.
2. Prioriza fuentes recientes, oficiales o verificables.
3. Resume los resultados por relevancia e incluye enlaces cuando existan.
4. Senala incertidumbre, fechas y posibles sesgos de las fuentes.

## Restricciones
* No inventes URLs, titulos ni datos.
* No uses busqueda web para informacion sensible si el usuario no lo pidio.
* No presentes resultados no verificados como hechos definitivos.""",
        "resources": "examples/search-query.md",
    },
    "read_url": {
        "argument_hint": "URL publica para leer y sintetizar.",
        "triggers": "ARRAY['user','model']::varchar[]",
        "body": """# Instrucciones principales
1. Valida que la entrada contiene una URL publica.
2. Extrae el contenido principal y descarta navegacion, anuncios y boilerplate.
3. Devuelve un resumen fiel, puntos clave y cualquier dato accionable.
4. Cita la URL original en la respuesta.

## Restricciones
* No leas URLs privadas, locales o potencialmente internas.
* No inventes contenido que no aparezca en la pagina.
* Si la pagina no se puede leer, explica el fallo y pide otra fuente.""",
        "resources": "examples/read-url.md",
    },
    "extract_pdf": {
        "argument_hint": "PDF adjunto o referencia a un archivo ya subido.",
        "triggers": "ARRAY['user']::varchar[]",
        "body": """# Instrucciones principales
1. Identifica el PDF adjunto que el usuario quiere procesar.
2. Extrae texto, metadatos visibles y estructura basica del documento.
3. Conserva secciones, tablas o paginas relevantes cuando sea posible.
4. Devuelve un resultado organizado por pagina o seccion.

## Restricciones
* No asumas texto que no se haya extraido.
* Si el PDF esta escaneado o incompleto, indicalo claramente.
* No expongas datos sensibles salvo que sean necesarios para la tarea.""",
        "resources": "examples/pdf-extraction.md",
    },
    "summarize_document": {
        "argument_hint": "Texto extraido, documento adjunto o seleccion de contenido.",
        "triggers": "ARRAY['user','model']::varchar[]",
        "body": """# Instrucciones principales
1. Identifica objetivo, audiencia y extension deseada del resumen.
2. Resume tesis principal, puntos clave, decisiones, riesgos y siguientes pasos.
3. Mantiene la terminologia del documento original.
4. Incluye una seccion de dudas o informacion faltante si aplica.

## Restricciones
* No cambies el sentido del documento.
* No anadas conclusiones que no esten respaldadas por el contenido.
* No ocultes contradicciones o limitaciones importantes.""",
        "resources": "templates/document-summary.md",
    },
    "analyze_image": {
        "argument_hint": "Imagen adjunta y pregunta concreta sobre la imagen.",
        "triggers": "ARRAY['user']::varchar[]",
        "body": """# Instrucciones principales
1. Describe primero los elementos visuales observables.
2. Responde la pregunta del usuario usando solo evidencia visible.
3. Diferencia observaciones de inferencias.
4. Si hace falta OCR, transcribe el texto visible y marca baja confianza.

## Restricciones
* No identifiques personas reales ni atributos sensibles.
* No afirmes detalles no visibles.
* No uses analisis de imagen si el modelo activo no soporta vision.""",
        "resources": "examples/image-analysis.md",
    },
    "critic_review": {
        "argument_hint": "Borrador o respuesta intermedia a revisar.",
        "triggers": "ARRAY['user','model']::varchar[]",
        "body": """# Instrucciones principales
1. Evalua exactitud, completitud, claridad y riesgos de la respuesta.
2. Identifica afirmaciones no justificadas, contradicciones y omisiones.
3. Propone correcciones concretas y priorizadas.
4. Devuelve una version revisada si el usuario lo pide.

## Restricciones
* No reescribas por estilo si hay errores factuales sin resolver.
* No suavices riesgos importantes.
* No apruebes una respuesta si faltan evidencias clave.""",
        "resources": "templates/critic-review.md",
    },
    "final_answer": {
        "argument_hint": "Contexto, hallazgos y borradores previos.",
        "triggers": "ARRAY['user','model']::varchar[]",
        "body": """# Instrucciones principales
1. Integra contexto, resultados de agentes y restricciones del usuario.
2. Produce una respuesta final clara, accionable y directamente util.
3. Ordena la respuesta de lo mas importante a lo accesorio.
4. Incluye supuestos, limites y siguientes pasos solo cuando aporten valor.

## Restricciones
* No incluyas trazas internas ni razonamiento privado.
* No cites fuentes o herramientas que no se hayan usado.
* No inventes consenso si los agentes discrepan.""",
        "resources": "templates/final-answer.md",
    },
}


def upgrade() -> None:
    for name, skill in SKILLS.items():
        op.execute(
            f"""
            UPDATE skills
            SET argument_hint = '{skill['argument_hint'].replace("'", "''")}',
                triggers = {skill['triggers']},
                body = $body${skill['body']}$body$,
                resources = '{skill['resources'].replace("'", "''")}'
            WHERE name = '{name}';
            """
        )


def downgrade() -> None:
    op.execute("UPDATE skills SET argument_hint = '', triggers = ARRAY['user']::varchar[], resources = '';")
