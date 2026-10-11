// Auto-extracted from App.tsx: presentational view over useApp() state.

import { useApp } from "../state/context";

export function DiagnosticsView() {
  const { diagnostics } = useApp();
  return (
<section className="panel full-panel"><h2>Diagnostics</h2>{diagnostics ? <><p>Users: {diagnostics.counts.users} | Agents: {diagnostics.counts.agents} | Workflows: {diagnostics.counts.workflows} | MCPs: {diagnostics.counts.mcp_servers}</p>{diagnostics.providers.map((provider) => <p className="muted" key={provider.id}>{provider.name}: {provider.ready ? "ready" : "not ready"} ({provider.configured_models} model(s), key {provider.api_key_configured ? "set" : "missing"})</p>)}</> : <p className="muted">No diagnostics loaded.</p>}</section>
  );
}
