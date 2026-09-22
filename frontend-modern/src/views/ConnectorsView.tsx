// Auto-extracted from App.tsx: presentational view over useApp() state.

import { useApp } from "../state/context";

export function ConnectorsView() {
  const { connectorMessage, catalogConnectors, connectorBusy, testConnectorAccount, disconnectConnector, connectConnector, connectorTokenDrafts, setConnectorTokenDrafts } = useApp();
  return (
<section className="panel full-panel">
          <h2>Conectores</h2>
          <p className="muted">Conecta tus cuentas para que los agentes puedan usarlas. Los tokens se guardan cifrados y las herramientas sensibles piden aprobaciÃ³n. ActÃ­valas por agente en Ajustes, AdministraciÃ³n, Agents.</p>
          {connectorMessage && <p className="muted">{connectorMessage}</p>}
          <div className="skill-grid">{catalogConnectors.map((connector) => <article className="skill-card" key={connector.slug}>
            <div className="skill-card-head"><div><strong>{connector.name}</strong><span>{connector.account ? `Conectado Â· ${connector.account.display_name || connector.account.status}` : "Sin conectar"}</span></div></div>
            <p>{connector.description}</p>
            <div className="chip-row">{connector.tool_names.map((toolName) => <span className="chip" key={toolName}>{toolName}</span>)}</div>
            {connector.account ? <div className="skill-actions">
              <button className="text-button" disabled={connectorBusy === connector.slug} onClick={() => void testConnectorAccount(connector)}>{connectorBusy === connector.slug ? "Probando..." : "Probar token"}</button>
              <button className="text-button danger" disabled={connectorBusy === connector.slug} onClick={() => void disconnectConnector(connector)}>Desconectar</button>
            </div> : <form className="task-create" onSubmit={(event) => { event.preventDefault(); void connectConnector(connector.slug); }}>
              <input type="password" value={connectorTokenDrafts[connector.slug] ?? ""} onChange={(event) => setConnectorTokenDrafts((current) => ({ ...current, [connector.slug]: event.target.value }))} placeholder={connector.token_label} required />
              <button type="submit" disabled={connectorBusy === connector.slug}>{connectorBusy === connector.slug ? "Conectando..." : "Conectar"}</button>
            </form>}
            <details className="card-details"><summary>CÃ³mo obtener el token</summary><p className="muted">{connector.token_help}</p></details>
          </article>)}</div>
        </section>
  );
}
