// Small shared presentational components.
import { FormEvent, ReactNode } from "react";
import type { HealthResponse, ModelCheckResponse } from "../types";

export function ConfigForm({ children, onSubmit, submitLabel }: { children: ReactNode; onSubmit: (event: FormEvent) => void; submitLabel: string }) {
  return (
    <form className="config-form" onSubmit={onSubmit}>
      {children}
      <button type="submit">{submitLabel}</button>
    </form>
  );
}

export function HealthLine({ health }: { health: HealthResponse | null }) {
  if (!health) return <p className="muted">Checking backend...</p>;
  const database = health.database ? `, DB ${health.database}` : "";
  return <p className="muted">Backend {health.status}{database}</p>;
}

export function ModelCheckResult({ result }: { result: ModelCheckResponse }) {
  let summary = "Ready";
  if (!result.enabled) summary = "Model disabled";
  else if (!result.provider_enabled) summary = "Provider disabled";
  else if (!result.api_key_configured) summary = `Missing API key: ${result.api_key_env ?? "provider key"}`;
  else if (!result.ready) summary = "Not ready";

  return (
    <div className="skill-result">
      <strong>{summary}</strong>
      <pre>{JSON.stringify(result, null, 2)}</pre>
    </div>
  );
}

export function MetricsBarChart({ rows }: { rows: Array<{ label: string; segments: Array<{ value: number; color: string; label: string }> }> }) {
  if (rows.length === 0) return <p className="muted">Sin datos en este periodo.</p>;
  const max = Math.max(1, ...rows.map((row) => row.segments.reduce((sum, segment) => sum + segment.value, 0)));
  const chartWidth = 560;
  const chartHeight = 110;
  const barSpace = chartWidth / rows.length;
  const barWidth = Math.max(6, barSpace * 0.6);
  return (
    <svg className="metrics-chart" viewBox={`0 0 ${chartWidth} ${chartHeight + 22}`} role="img" aria-label="Grafico de barras por dia">
      {rows.map((row, index) => {
        let cursor = chartHeight;
        return (
          <g key={row.label}>
            {row.segments.map((segment, segmentIndex) => {
              const height = (segment.value / max) * chartHeight;
              cursor -= height;
              return <rect key={segmentIndex} x={index * barSpace + (barSpace - barWidth) / 2} y={cursor} width={barWidth} height={height} fill={segment.color}><title>{`${row.label} ${segment.label}: ${segment.value}`}</title></rect>;
            })}
            <text x={index * barSpace + barSpace / 2} y={chartHeight + 16} textAnchor="middle" fontSize="9" fill="currentColor">{row.label.slice(5)}</text>
          </g>
        );
      })}
    </svg>
  );
}
