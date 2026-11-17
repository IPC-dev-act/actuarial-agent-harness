"""Read-only MCP access to saved Snowflake reserving evidence."""

import argparse
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import StringConstraints

from snowflake_demo.demo import add_connection_options, connect, identifier, inspect_attempt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_options(parser)
    options = parser.parse_args()
    namespace = f"{identifier(options.database)}.{identifier(options.schema)}"
    mcp = FastMCP("Actuary in Snowflake")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
    def inspect_reserving_attempt(attempt_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]) -> dict:
        """Return saved reserve figures, review status and checks for an exact Snowflake attempt ID."""
        with connect(options) as connection, connection.cursor() as cursor:
            return inspect_attempt(cursor, namespace, attempt_id)

    mcp.run()


if __name__ == "__main__":
    main()
