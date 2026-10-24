#!/usr/bin/env node
// HTTP JSON-RPC <-> stdio MCP bridge.
//
// ObsyGPT's MCP gateway speaks raw JSON-RPC over HTTP POST: one request in, one
// response out, no session state. MCP servers speak newline-delimited JSON-RPC over
// stdio and require an initialize handshake before answering tools/*.
//
// This bridge keeps ONE MCP child process alive, performs the handshake itself at
// startup, and forwards requests with id remapping. Gateway `initialize` requests are
// answered from the cached handshake result, so the gateway's inspect flow works even
// though the child is already initialized. If the child dies it is respawned on the
// next request.
import http from 'node:http';
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import readline from 'node:readline';

const PORT = Number(process.env.PORT || 8808);
const MCP_SCRIPT = process.env.FLOW_MCP_SCRIPT || join(dirname(fileURLToPath(import.meta.url)), 'src', 'mcp.js');
const PROTOCOL_VERSION = '2024-11-05';
// Upper bound for forwarded requests. Cold Chrome/CDP starts and multi-image
// generations take minutes; the HTTP client's timeout (MCP_TOOL_TIMEOUT) is the
// authoritative limit, this just avoids hanging forever if the child never answers.
const REQUEST_TIMEOUT_MS = Number(process.env.FLOW_REQUEST_TIMEOUT_MS || 600000);

let child = null;
let nextId = 1;
let pending = new Map();
let handshake = null; // cached initialize result

function startChild() {
  if (child && child.exitCode === null) return;
  child = spawn(process.execPath, [MCP_SCRIPT], { cwd: dirname(MCP_SCRIPT), stdio: ['pipe', 'pipe', 'inherit'] });
  pending = new Map();
  handshake = null;
  const rl = readline.createInterface({ input: child.stdout });
  rl.on('line', (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    let message;
    try {
      message = JSON.parse(trimmed);
    } catch {
      return;
    }
    if (message.id !== undefined && message.id !== null && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
    }
  });
  child.on('exit', () => {
    for (const resolve of pending.values()) resolve({ jsonrpc: '2.0', error: { code: -32000, message: 'flow-mcp child process exited' } });
    pending = new Map();
    handshake = null;
  });
}

function send(message) {
  child.stdin.write(`${JSON.stringify(message)}\n`);
}

function request(method, params, timeoutMs = REQUEST_TIMEOUT_MS) {
  const id = nextId++;
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      resolve({ jsonrpc: '2.0', id, error: { code: -32001, message: `flow-mcp timed out on ${method}` } });
    }, timeoutMs);
    pending.set(id, (message) => {
      clearTimeout(timer);
      resolve(message);
    });
    send({ jsonrpc: '2.0', id, method, params });
  });
}

async function ensureReady() {
  startChild();
  if (handshake) return;
  const init = await request('initialize', {
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {},
    clientInfo: { name: 'obsygpt-flow-bridge', version: '1.0.0' },
  });
  if (init.error || !init.result) {
    handshake = null;
    throw new Error(init.error ? init.error.message : 'MCP child returned no initialize result');
  }
  handshake = init.result;
  send({ jsonrpc: '2.0', method: 'notifications/initialized' });
}

async function handle(req, res) {
  if (req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: Boolean(handshake), server: 'obsygpt-flow-mcp' }));
    return;
  }
  if (req.method !== 'POST') {
    res.writeHead(405).end();
    return;
  }
  let body = '';
  for await (const chunk of req) body += chunk;
  let rpc;
  try {
    rpc = JSON.parse(body);
  } catch {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ jsonrpc: '2.0', error: { code: -32700, message: 'Invalid JSON' } }));
    return;
  }
  const { method, id } = rpc;
  try {
    await ensureReady();
    if (method === 'initialize') {
      respond(res, { jsonrpc: '2.0', id, result: handshake });
    } else if (method === 'notifications/initialized') {
      respond(res, {});
    } else if (id === undefined || id === null) {
      send({ jsonrpc: '2.0', method, params: rpc.params });
      respond(res, {});
    } else {
      const reply = await request(method, rpc.params);
      respond(res, { ...reply, id });
    }
  } catch (error) {
    respond(res, { jsonrpc: '2.0', id, error: { code: -32000, message: `flow-mcp bridge: ${error.message}` } });
  }
}

function respond(res, body) {
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

const server = http.createServer((req, res) => {
  handle(req, res).catch((error) => respond(res, { jsonrpc: '2.0', error: { code: -32000, message: String(error) } }));
});

// Graceful stop: docker stop sends TERM to this process (chromium's parent). Let the
// browser exit cleanly first — an abrupt kill breaks Google session cookie persistence.
function shutdown(signal) {
  console.log(`[flow-mcp-bridge] ${signal} received, stopping chromium gracefully`);
  let pid = 0;
  try {
    pid = Number(readFileSync('/tmp/chromium.pid', 'utf8').trim());
    if (pid) process.kill(pid, 'SIGTERM');
  } catch { /* chromium already gone */ }
  const deadline = Date.now() + 8000;
  const wait = () => {
    let alive = false;
    try {
      process.kill(pid, 0);
      alive = true;
    } catch { /* exited */ }
    if (alive && Date.now() < deadline) return setTimeout(wait, 500);
    process.exit(0);
  };
  wait();
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[flow-mcp-bridge] listening on :${server.address().port}`);
  // Warm up: handshake with the child at boot so /health is true and the first
  // request doesn't pay for it. Failures surface on the first real request.
  ensureReady().catch(() => {});
});
