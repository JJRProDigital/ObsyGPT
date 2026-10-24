// Auto-extracted from App.tsx: presentational view over useApp() state.

import { useApp } from "../state/context";

export function ToolsView() {
  const { toolDefinitions } = useApp();
  return (
<section className="panel full-panel">
          <h2>Herramientas</h2>
          <p className="muted">Herramientas disponibles para los agentes. Permisos por agente en Ajustes, Administracion, Agents; politicas personales en Ajustes, Seguridad.</p>
          <div className="skill-grid">{toolDefinitions.map((tool) => <article className="skill-card" key={tool.name}>
            <div className="skill-card-head"><div><strong>{tool.name}</strong><span>{tool.permission === "safe" ? "segura" : "sensible: requiere aprobacion"}</span></div></div>
            <p>{tool.description}</p>
            <pre className="skill-md-preview">{tool.parameters}</pre>
          </article>)}</div>
        </section>
  );
}
