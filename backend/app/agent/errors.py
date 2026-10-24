"""Agent loop errors."""


class ApprovalRequiredError(Exception):
    """Raised when a sensitive tool needs explicit user approval before running."""

    def __init__(self, approval_id: int, tool_name: str, args: dict):
        self.approval_id = approval_id
        self.tool_name = tool_name
        self.args = args
        super().__init__(f"Approval required for tool '{tool_name}' (approval #{approval_id}).")


class RunCancelledError(Exception):
    """Raised when the caller requests the agent loop to stop between iterations."""

