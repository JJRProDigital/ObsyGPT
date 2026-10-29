# obsygpt-flow-mcp

Servicio Docker que expone generación de imágenes con **Google Flow (Nano Banana)**
como MCP de tipo URL para ObsyGPT.

## Procedencia

El código en `src/` está vendido de [srz-google-flow-mcp](https://srzclub.com/flow-mcp)
v1.0.1 (licencia MIT). Cambios sobre el original:

- `chrome.js`: candidatos de binario para Linux (`/usr/bin/chromium`) y flag
  opt-in `FLOW_CHROME_NO_SANDBOX=1` (necesario para Chromium como root en contenedores).
- Todo lo demás (`flow.js`, `lock.js`, `mcp.js`, `cli.js`) está sin cambios.

## Arquitectura

```
ObsyGPT backend ──POST JSON-RPC──> bridge.js :8808 ──stdio──> src/mcp.js
                                     │                            │
                                     │                       playwright-core
                                     │                       (CDP :9222)
                                     ▼
                              Xvfb :99 + Chromium headed
                                     │
                              noVNC :6901 (sign-in de Google una vez)
```

- `bridge.js` mantiene **un** proceso MCP vivo, hace el handshake `initialize` al
  arrancar y responde los `initialize` del gateway desde caché. Reenvía
  `tools/list` / `tools/call` remapeando ids. Si el hijo muere, lo relanza.
- El gateway de ObsyGPT (`backend/app/mcps/gateway.py`) habla JSON-RPC crudo por
  HTTP POST; este bridge es la capa de compatibilidad exacta para ese contrato.

## Variables

| Variable | Default | Uso |
|---|---|---|
| `PORT` | `8808` | Puerto HTTP del bridge (JSON-RPC + `/health`) |
| `NOVNC_PORT` | `6901` | Puerto de noVNC para el sign-in |
| `FLOW_CDP_PORT` | `9222` | Puerto CDP de Chromium (loopback interno) |
| `FLOW_USER_DATA_DIR` | `/config/flow-profile` | Perfil de Chromium (persistir en volumen) |
| `FLOW_OUTPUT_DIR` | `/data/images` | Carpeta de imágenes generadas |
| `FLOW_CHROME_NO_SANDBOX` | `1` | Requerido como root en el contenedor |

## Test

```bash
npm test   # test/bridge.test.js con un servidor stdio MCP falso
```
