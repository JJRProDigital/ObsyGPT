#!/usr/bin/env node
// Fake stdio MCP server used to exercise bridge.js without driving a browser.
import readline from 'node:readline';

const rl = readline.createInterface({ input: process.stdin });
rl.on('line', (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let message;
  try {
    message = JSON.parse(trimmed);
  } catch {
    return;
  }
  if (message.id === undefined || message.id === null) return; // notification
  let result = null;
  if (message.method === 'initialize') {
    result = {
      protocolVersion: message.params?.protocolVersion || '2024-11-05',
      capabilities: { tools: {} },
      serverInfo: { name: 'fake-flow', version: '0.0.0' },
    };
  } else if (message.method === 'tools/list') {
    result = { tools: [{ name: 'echo', description: 'echo tool', inputSchema: {} }] };
  } else if (message.method === 'tools/call') {
    if (message.params?.name === 'die') process.exit(1); // no response: simulates a crash
    result = { content: [{ type: 'text', text: `pong:${message.params?.arguments?.say ?? ''}` }] };
  } else {
    process.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', id: message.id, error: { code: -32601, message: `unknown method ${message.method}` } })}\n`);
    return;
  }
  process.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', id: message.id, result })}\n`);
});
