"""Add mcp_servers.tool_permission (safe MCP tools can run in headless readonly runs).

Revision ID: 0027_mcp_server_tool_permission
Revises: 0026_higgsfield_api_connector
"""

from alembic import op

revision: str = "0027_mcp_server_tool_permission"
down_revision: str | None = "0026_higgsfield_api_connector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE mcp_servers
        ADD COLUMN tool_permission VARCHAR(20) DEFAULT 'sensitive' NOT NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE mcp_servers
        ADD CONSTRAINT mcp_servers_tool_permission_check CHECK (tool_permission IN ('safe', 'sensitive'));
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE mcp_servers DROP CONSTRAINT IF EXISTS mcp_servers_tool_permission_check;")
    op.execute("ALTER TABLE mcp_servers DROP COLUMN IF EXISTS tool_permission;")
