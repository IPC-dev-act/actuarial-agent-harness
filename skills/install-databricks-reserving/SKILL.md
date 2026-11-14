---
name: install-databricks-reserving
description: Deploy and rehearse the Actuary in a Box RAA reserving demo in a Databricks workspace. Use when asked to install the Databricks reserving demo, provision its notebooks and jobs, run Mack on the public sample, or connect its reserving MCP server.
---

# Install Databricks reserving

Use the installer's commands from the matching Actuary in a Box source checkout.
Find it by locating `databricks.yml` and `scripts/install_databricks_demo.py`.
If the skill was installed on its own, check out its release tag or commit
from [IPC-dev-act/actuarial-agent-harness](https://github.com/IPC-dev-act/actuarial-agent-harness).
For branch-based testing, use the checkout from which the skill was installed.

Confirm the intended Databricks CLI profile and writable Unity Catalog
catalog from the conversation or workspace. When the user omits them,
inspect `databricks auth profiles` and `databricks catalogs list --profile PROFILE`.
Use the workspace's writable catalog if clear, and ask for the catalog if
several candidates remain. Run `databricks current-user me --profile PROFILE`
to check connectivity. When
sign-in is required, direct the user to their local browser sign-in with
`databricks auth login --host WORKSPACE_URL --profile PROFILE`. Use the
user's CLI session. Setup needs a recent Databricks CLI, uv, Python 3.11+
and the ability to create a schema and run jobs. Use the dedicated
`ipc_reserving_demo` schema unless the user specifies another demo schema.
Select the warehouse automatically when only one is available, or use the
user's choice with `--warehouse-id`.

Run the commands below with the actual profile and catalog. Keep the same
profile, catalog and schema across commands.

```bash
uv run --no-project --python '>=3.11' --with mcp==1.28.1 python scripts/install_databricks_demo.py deploy --profile PROFILE --catalog CATALOG
uv run --no-project --python '>=3.11' --with mcp==1.28.1 python scripts/install_databricks_demo.py rehearse --profile PROFILE --catalog CATALOG
uv run --no-project --python '>=3.11' --with mcp==1.28.1 python scripts/install_databricks_demo.py connect --profile PROFILE --catalog CATALOG
```

For an install request, deploy, then rehearse. The rehearsal uses
the project's MCP tools to upload the public sample, verify its 55 rows,
run Mack on the imported Delta version, verify the saved reserve and
standard error, and download the draft report. If interrupted after
submission, repeat the rehearsal with its printed `--request-id` to reuse
the original Lakeflow submissions. For a deploy-only request, stop after
deployment and give the user the job links.

If the user wants native Genie, run the installer with action `genie` after
a successful rehearsal. If Genie is unavailable, report the workspace error
and retain the verified job links and report. If the user wants direct MCP
access in their agent, run the generated registration command for the
user's client. If already registered, reuse the entry when its deployment
settings match. When the client loads MCP configuration at session start,
tell the user to start a new session to call the registered tools.

Return the workspace, job links, selected Delta version, run link, saved
IBNR and report path for a completed rehearsal. Report a draft as pending
actuarial review. To repeat the same workflow in the workspace UI, open the
deployed job links and use **Run now with different parameters**. Upload
`raa.csv` first or use the filename returned by the rehearsal.
