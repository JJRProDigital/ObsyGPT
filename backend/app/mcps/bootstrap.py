"""Optional startup seeding for the Google Flow MCP (services/flow-mcp).

When FLOW_MCP_URL is configured (docker compose --profile flow), the matching
mcp_servers row is created or refreshed on startup so the image-generation tools
are available without manual registration. With the variable unset this module
does nothing, so default installs are unaffected.
"""

import logging
import os

from .. import db as app_db

logger = logging.getLogger("obsygpt.mcp.bootstrap")

FLOW_MCP_NAME = "Google Flow"
FLOW_MCP_DESCRIPTION = (
    "Generates images with Google Flow (Nano Banana Pro / 2 / 2 Lite) and uploads "
    "reference images. Generated files land in /data/workspace/flow-images (also "
    "./data/flow-images on the host); copy them into a project workspace with "
    "write_file so the user can open them. Call flow_upload_file first for reference "
    "photos (paths under /data/uploads or /data/workspace), then flow_generate_image "
    "with @{name} in the prompt."
)


def seed_flow_mcp() -> None:
    url = os.getenv("FLOW_MCP_URL", "").strip()
    if not url:
        return
    url = url.rstrip("/")
    with app_db.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id, url, description FROM mcp_servers WHERE name = %s;", (FLOW_MCP_NAME,))
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """
                    INSERT INTO mcp_servers (name, description, connection_type, url, enabled)
                    VALUES (%s, %s, 'url', %s, true)
                    RETURNING id;
                    """,
                    (FLOW_MCP_NAME, FLOW_MCP_DESCRIPTION, url),
                )
                cursor.fetchone()
                action = "created"
            elif row[1] != url or row[2] != FLOW_MCP_DESCRIPTION:
                cursor.execute(
                    "UPDATE mcp_servers SET url = %s, description = %s WHERE id = %s;",
                    (url, FLOW_MCP_DESCRIPTION, row[0]),
                )
                action = "updated"
            else:
                action = None
    if action:
        logger.info("Flow MCP %s (name=%s, url=%s)", action, FLOW_MCP_NAME, url)
