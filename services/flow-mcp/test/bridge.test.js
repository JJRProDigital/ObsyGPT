// bridge.js contract tests: run it against the fake stdio MCP server and speak the
// raw JSON-RPC-over-HTTP dialect ObsyGPT's gateway uses (backend/app/mcps/gateway.py).
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

async function startBridge() {
  const child = spawn(process.execPath, [path.join(ROOT, 'bridge.js')], {
    env: { ...process.env, PORT: '0', FLOW_MCP_SCRIPT: path.join(ROOT, 'test', 'fake-mcp.js') },
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  const lines = createInterface({ input: child.stdout });
  const [line] = await once(lines, 'line');
  const port = Number(line.match(/listening on :(\d+)/)[1]);
  const base = `http://127.0.0.1:${port}`;
  const rpc = async (body) => {
    const res = await fetch(base, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return { status: res.status, body: await res.json() };
  };
  return { child, base, rpc };
}

async function waitHealthy(base) {
  for (let i = 0; i < 40; i++) {
    const health = await (await fetch(`${base}/health`)).json();
    if (health.ok) return health;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  assert.fail('bridge did not become healthy');
}

test('bridge handshake, cached initialize, tools/list and tools/call', async (t) => {
  const { child, base, rpc } = await startBridge();
  t.after(() => child.kill());

  const health = await waitHealthy(base);
  assert.equal(health.server, 'obsygpt-flow-mcp');

  // The gateway's inspect flow: initialize -> notifications/initialized -> tools/list.
  const init = await rpc({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'obsygpt', version: '1.0.0' } } });
  assert.equal(init.status, 200);
  assert.equal(init.body.result.serverInfo.name, 'fake-flow');

  const notified = await rpc({ jsonrpc: '2.0', method: 'notifications/initialized' });
  assert.deepEqual(notified.body, {});

  const list = await rpc({ jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} });
  assert.deepEqual(list.body.result.tools.map((tool) => tool.name), ['echo']);

  const call = await rpc({ jsonrpc: '2.0', id: 42, method: 'tools/call', params: { name: 'echo', arguments: { say: 'hi' } } });
  assert.equal(call.body.id, 42, 'response must carry the caller id');
  assert.equal(call.body.result.content[0].text, 'pong:hi');
});

test('bridge recovers when the MCP child crashes mid-call', async (t) => {
  const { child, rpc } = await startBridge();
  t.after(() => child.kill());

  const call = await rpc({ jsonrpc: '2.0', id: 7, method: 'tools/call', params: { name: 'echo', arguments: { say: 'x' } } });
  assert.equal(call.body.id, 7);
  assert.equal(call.body.result.content[0].text, 'pong:x');

  const die = await rpc({ jsonrpc: '2.0', id: 8, method: 'tools/call', params: { name: 'die', arguments: {} } });
  assert.equal(die.body.id, 8);
  assert.equal(die.body.error?.code, -32000, 'the in-flight call reports the child exit');

  const after = await rpc({ jsonrpc: '2.0', id: 9, method: 'tools/call', params: { name: 'echo', arguments: { say: 'y' } } });
  // Respawned child re-initializes, so the next call succeeds (never a stale error).
  assert.equal(after.body.id, 9);
  assert.equal(after.body.result.content[0].text, 'pong:y');
});
