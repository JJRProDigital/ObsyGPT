// Auto-extracted from App.tsx: presentational view over useApp() state.
import { MetricsBarChart } from "../components/shared";
import { useApp } from "../state/context";

export function MonitoringView() {
  const { metricsDays, setMetricsDays, loadMetrics, metrics } = useApp();
  return (
<section className="panel full-panel">
          <h2>Monitoring</h2>
          <div className="audit-filters">
            {[7, 14, 30].map((days) => <button key={days} className={metricsDays === days ? "active" : ""} onClick={() => { setMetricsDays(days); void loadMetrics(days); }}>{days} dÃ­as</button>)}
          </div>
          {!metrics ? <p className="muted">Cargando mÃ©tricas...</p> : <>
            <div className="metrics-summary">
              <div className="metric-card"><strong>{metrics.summary.runs}</strong><span>runs</span></div>
              <div className="metric-card"><strong>{metrics.summary.completed}</strong><span>completados</span></div>
              <div className="metric-card"><strong>{metrics.summary.failed}</strong><span>fallidos</span></div>
              <div className="metric-card"><strong>{metrics.summary.avg_duration_seconds.toFixed(1)}s</strong><span>duraciÃ³n media</span></div>
              <div className="metric-card"><strong>{metrics.summary.active_users}</strong><span>usuarios activos</span></div>
              <div className="metric-card"><strong>{metrics.provider_fallbacks}</strong><span>fallbacks de proveedor</span></div>
            </div>
            <h3>Runs por dÃ­a</h3>
            <MetricsBarChart rows={metrics.runs_per_day.map((row) => ({ label: row.day, segments: [
              { value: row.completed, color: "#7aa860", label: "completados" },
              { value: row.failed, color: "#c96a5f", label: "fallidos" },
              { value: row.other, color: "#d5b06d", label: "otros" }
            ] }))} />
            <h3>Llamadas a herramientas por dÃ­a</h3>
            <MetricsBarChart rows={metrics.tool_calls_per_day.map((row) => ({ label: row.day, segments: [
              { value: row.total - row.failed, color: "#7fbfb4", label: "ok" },
              { value: row.failed, color: "#c96a5f", label: "fallidas" }
            ] }))} />
            <h3>Top herramientas</h3>
            <div className="chip-row">{Object.entries(metrics.tool_categories).map(([category, calls]) => <span className="chip" key={category}>{category}: {calls}</span>)}</div>
            <table className="metrics-table"><thead><tr><th>Tool</th><th>Llamadas</th><th>Fallidas</th></tr></thead><tbody>{metrics.top_tools.map((tool) => <tr key={tool.name}><td>{tool.name}</td><td>{tool.calls}</td><td>{tool.failed}</td></tr>)}</tbody></table>
            <h3>Actividad por agente</h3>
            <table className="metrics-table"><thead><tr><th>Agente</th><th>Runs</th><th>Fallidos</th></tr></thead><tbody>{metrics.agent_activity.map((row) => <tr key={row.agent}><td>{row.agent}</td><td>{row.runs}</td><td>{row.failed}</td></tr>)}</tbody></table>
            {metrics.mcp_calls.length > 0 && <>
              <h3>Llamadas MCP</h3>
              <table className="metrics-table"><thead><tr><th>MÃ©todo/Tool</th><th>Llamadas</th><th>Fallidas</th></tr></thead><tbody>{metrics.mcp_calls.map((row) => <tr key={row.name}><td>{row.name}</td><td>{row.calls}</td><td>{row.failed}</td></tr>)}</tbody></table>
            </>}
            <p className="muted">Export OTLP opcional: configura OTEL_EXPORTER_OTLP_ENDPOINT en backend/.env (eventos user_prompt, assistant_response, tool_result, api_error; contenido redactado por defecto con OTEL_CONTENT_CAPTURE).</p>
          </>}
        </section>
  );
}
