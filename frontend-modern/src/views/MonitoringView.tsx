// Auto-extracted from App.tsx: presentational view over useApp() state.
import { MetricsBarChart } from "../components/shared";
import { useApp } from "../state/context";

type ToolStat = { name: string; calls: number; failed: number };

function failureRate(row: { calls?: number; runs?: number; failed: number }): string {
  const total = row.calls ?? row.runs ?? 0;
  if (!total) return "0%";
  return `${Math.round((row.failed / total) * 100)}%`;
}

function StatTable({ headers, rows }: { headers: string[]; rows: Array<{ key: string; cells: Array<string | number>; bad: boolean }> }) {
  return (
    <table className="metrics-table">
      <thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className={row.bad ? "row-bad" : ""}>
            {row.cells.map((cell, index) => <td key={index}>{cell}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function MonitoringView() {
  const { metricsDays, setMetricsDays, loadMetrics, metrics } = useApp();
  const summary = metrics?.summary;
  const successRate = summary && summary.runs > 0 ? Math.round((summary.completed / summary.runs) * 100) : null;
  return (
<section className="full-panel monitor-view">
          <div className="monitor-head">
            <h2>Monitoring</h2>
            <div className="subtabs">
              {[7, 14, 30].map((days) => <button key={days} className={metricsDays === days ? "active" : ""} onClick={() => { setMetricsDays(days); void loadMetrics(days); }}>{days} días</button>)}
            </div>
          </div>
          {!metrics || !summary ? <p className="muted">Cargando métricas...</p> : <>
            <div className="kpi-grid">
              <div className="kpi-card kpi-info"><strong>{summary.runs}</strong><span>runs</span></div>
              <div className="kpi-card kpi-ok"><strong>{summary.completed}</strong><span>completados</span></div>
              <div className="kpi-card kpi-bad"><strong>{summary.failed}</strong><span>fallidos</span></div>
              {successRate !== null && <div className="kpi-card kpi-ok"><strong>{successRate}%</strong><span>tasa de éxito</span></div>}
              <div className="kpi-card kpi-neutral"><strong>{summary.avg_duration_seconds.toFixed(1)}s</strong><span>duración media</span></div>
              <div className="kpi-card kpi-neutral"><strong>{summary.active_users}</strong><span>usuarios activos</span></div>
              <div className="kpi-card kpi-warn"><strong>{metrics.provider_fallbacks}</strong><span>fallbacks de proveedor</span></div>
            </div>
            <div className="monitor-charts">
              <div className="panel monitor-card">
                <h3>Runs por día</h3>
                <MetricsBarChart rows={metrics.runs_per_day.map((row) => ({ label: row.day, segments: [
                  { value: row.completed, color: "#7aa860", label: "completados" },
                  { value: row.failed, color: "#c96a5f", label: "fallidos" },
                  { value: row.other, color: "#d5b06d", label: "otros" }
                ] }))} />
              </div>
              <div className="panel monitor-card">
                <h3>Llamadas a herramientas por día</h3>
                <MetricsBarChart rows={metrics.tool_calls_per_day.map((row) => ({ label: row.day, segments: [
                  { value: row.total - row.failed, color: "#7fbfb4", label: "ok" },
                  { value: row.failed, color: "#c96a5f", label: "fallidas" }
                ] }))} />
              </div>
            </div>
            <div className="monitor-tables">
              <div className="panel monitor-card">
                <h3>Top herramientas</h3>
                <StatTable
                  headers={["Tool", "Llamadas", "Fallidas", "Tasa"]}
                  rows={metrics.top_tools.map((tool: ToolStat) => ({
                    key: tool.name,
                    cells: [tool.name, tool.calls, tool.failed, failureRate(tool)],
                    bad: tool.calls > 0 && tool.failed / tool.calls > 0.1
                  }))}
                />
              </div>
              <div className="panel monitor-card">
                <h3>Actividad por agente</h3>
                <StatTable
                  headers={["Agente", "Runs", "Fallidos", "Tasa"]}
                  rows={metrics.agent_activity.map((row: { agent: string; runs: number; failed: number }) => ({
                    key: row.agent,
                    cells: [row.agent, row.runs, row.failed, failureRate(row)],
                    bad: row.runs > 0 && row.failed / row.runs > 0.1
                  }))}
                />
              </div>
            </div>
            <div className="panel monitor-card">
              <h3>Uso por categoría de tool</h3>
              <div className="chip-row">{Object.entries(metrics.tool_categories).map(([category, calls]) => <span className="chip" key={category}>{category}: {calls as number}</span>)}</div>
            </div>
            {metrics.mcp_calls.length > 0 && (
              <div className="panel monitor-card">
                <h3>Llamadas MCP</h3>
                <StatTable
                  headers={["Método/Tool", "Llamadas", "Fallidas", "Tasa"]}
                  rows={metrics.mcp_calls.map((row: { name: string; calls: number; failed: number }) => ({
                    key: row.name,
                    cells: [row.name, row.calls, row.failed, failureRate(row)],
                    bad: row.calls > 0 && row.failed / row.calls > 0.1
                  }))}
                />
              </div>
            )}
            <details className="otlp-note"><summary>Export OTLP opcional</summary><p className="muted">Configura OTEL_EXPORTER_OTLP_ENDPOINT en backend/.env. Eventos: user_prompt, assistant_response, tool_result, api_error. Contenido redactado por defecto con OTEL_CONTENT_CAPTURE.</p></details>
          </>}
        </section>
  );
}
