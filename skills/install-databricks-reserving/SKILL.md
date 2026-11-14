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

## Connect to Databricks

1. If the user has provided neither a workspace URL nor a CLI profile,
   ask them to open their Databricks workspace, sign in, and paste the
   workspace URL from the address bar. Use the workspace origin, such as
   `https://dbc-example.cloud.databricks.com`. If they paste an account
   sign-in page, ask for the workspace URL once it opens.
2. Check for the [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install)
   (1.3 or later), [uv](https://docs.astral.sh/uv/getting-started/installation/),
   and Python 3.11 or later. Help the user install any missing prerequisite
   using its official instructions.
3. Use the named CLI profile, or `ipc-demo` by default. Check
   `databricks auth profiles` for a profile matching the intended workspace.
   When browser sign-in is needed, run
   `databricks auth login --host WORKSPACE_URL --profile PROFILE` and tell
   the user to finish in their browser. Verify the connection with
   `databricks current-user me --profile PROFILE`.
4. Run `databricks catalogs list --profile PROFILE` if the catalog is
   unspecified. Use the workspace's writable catalog if clear, or ask
   when several are suitable. The user needs permission to create a
   schema and run jobs. Select the SQL warehouse automatically when only
   one is available, or use the user's choice with `--warehouse-id`.

Use `ipc_reserving_demo` for a first install. For a clean retry in the same
workspace, use an unused schema name passed with `--schema` on every
installer command. This gives the bundle a fresh workspace path and
deployment state. For a fresh sign-in test, also use a new CLI profile.

Run the commands below with the actual profile and catalog. Keep the same
profile, catalog and schema across commands.

```bash
uv run --no-project --python '>=3.11' --with mcp==1.28.1 python scripts/install_databricks_demo.py deploy --profile PROFILE --catalog CATALOG
uv run --no-project --python '>=3.11' --with mcp==1.28.1 python scripts/install_databricks_demo.py import --profile PROFILE --catalog CATALOG
```

Use the guided import for a request to set up, install, or walk through the
demo. For a deploy-only request, stop after deployment and give the job links.
For an explicit end-to-end run, use `rehearse` in place of `import` to
verify the 55 rows, run Mack on the imported Delta version, and retrieve
the draft. After an interruption, repeat the last action with its printed
`--request-id` to reuse the original Lakeflow submissions.

## Guide the user through the imported data

Lead with a clickable **Open RAA triangle in Databricks** link from
`input_table_url`. Tell the user to select **Sample Data** and use the
available SQL warehouse if prompted. The table shows the current rows.
Give the import run link as well so the user can see the preview and Delta
version from that import. Show the first five rows, the exact Delta
version, and the reserving job link, then pause for the user to inspect.
To run from the workspace, use **Run now with different parameters** on the
reserving job, set `method=mack`, and set `source_version` to the printed
version. After the job completes, link to the run and tell the user to
open the **reserving** notebook task to see the draft. Provide
`run_history_url` to inspect the stored results in Catalog Explorer.

If the user wants native Genie, run the installer with action `genie` after
a successful Mack run. If Genie is unavailable, report the workspace error
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
