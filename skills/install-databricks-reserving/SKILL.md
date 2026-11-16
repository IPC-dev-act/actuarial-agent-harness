---
name: install-databricks-reserving
description: Guide the Actuary in a Box RAA reserving demo through a Databricks import, a Mack draft report in Databricks, and questions in Genie and Claude via MCP. Also use for deploy-only and automated rehearsals.
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
   one is available, or pass the user's choice as `--warehouse-id` on
   installer commands that use a warehouse.

## Default guided demo

For each new walkthrough, list the schemas with
`databricks schemas list CATALOG --profile PROFILE` and choose an unused
demo schema. Use `ipc_reserving_demo` if available, or add a numeric suffix
if it already exists. Use the same profile, catalog and schema throughout
the walkthrough. A fresh sign-in test can also use a new CLI profile.

Before deployment, link **Open the catalog in Databricks** to
`WORKSPACE_URL/explore/data/CATALOG`. Use the verified workspace origin
and catalog. If the user supplied only a profile, get the origin from
`details.host` in `databricks auth describe --profile PROFILE --output json`.
Use the chosen schema name in this cue.

> **Open the catalog in Databricks** and show the schema list. The demo
> schema **SCHEMA** hasn't been created yet. Say **Set up the demo** when
> the catalog is on screen.

Wait for **Set up the demo** in the guided walkthrough, then deploy.

```bash
uv run --no-project --python '>=3.11' --with mcp==1.28.1 python scripts/install_databricks_demo.py deploy --profile PROFILE --catalog CATALOG --schema SCHEMA
```

Once deployment succeeds, lead with this cue. Link **Open the demo schema
in Databricks** to `schema_url` and keep the message focused on the user's
next action.

> Refresh the catalog to see the new schema appear. Then **open the demo
> schema in Databricks** and select **Tables**. Say **Run the import**
> when you see the empty table list. I'll tell you when to refresh it to
> see the RAA table arrive.

If you offer a button, label it **Run the import**. Wait for the user
to continue, then run the import in the same schema.

```bash
uv run --no-project --python '>=3.11' --with mcp==1.28.1 python scripts/install_databricks_demo.py import --profile PROFILE --catalog CATALOG --schema SCHEMA
```

For a deploy-only request, stop after deployment and give the schema and job
links. For an explicit uninterrupted end-to-end run, use `rehearse` in place
of `import` to verify the 55 rows, run Mack on the imported Delta version,
and retrieve the draft. After an interruption, repeat the last action with
its printed `--request-id` to reuse the original Lakeflow submissions.

## Guide the user through the imported data

After the guided import succeeds, lead with this cue. Link
**ipc_reserving_demo_triangles** to `input_table_url`.

> Refresh the same **Tables** page now. The **ipc_reserving_demo_triangles**
> table should appear. Open it and select **Sample Data** to see the rows
> that just landed.

For a standalone import, lead with the direct table link and the
**Sample Data** step. If Databricks prompts for a SQL warehouse, tell the
user to select the available one.
Give the row count and imported Delta version from `import`. Link the
import run for anyone who wants the exact-version preview. Ask the user
to say **Run Mack** when they've seen the data, then pause.

## Run Mack and show the saved Databricks report

On **Run Mack**, link **Open Run reserving in Databricks** to
`reserving_job.url`. Fill in the actual imported Delta version in the cue.

> **Open Run reserving in Databricks**. From the menu beside **Run now**,
> choose the option to run with different parameters or settings. Keep
> `dataset=raa` and `method=mack`, and set `source_version` to **VERSION**.
> Start the job, open its new entry in **Runs**, and send me that link.

Use the Lakeflow job run ID from that link to check the job and its saved
evidence. Keep the same profile, catalog and schema.

```bash
uv run --no-project --python '>=3.11' --with mcp==1.28.1 python scripts/install_databricks_demo.py inspect-run --profile PROFILE --catalog CATALOG --schema SCHEMA --run-id RUN_ID
```

If it's still running, wait and check again. Confirm `mack.job_result`
is `SUCCESS`, `mack.method` is `mack`, `mack.source_version` matches
the import, and `mack.draft_report_available` is true. If a check fails,
tell the user which one and help them recover before moving to Q&A.

Make showing the rendered draft its own step. Link **Open the Mack draft
in Databricks** to `mack.run_url` and give the user this cue.

> **Open the Mack draft in Databricks** and select the **reserving** task.
> Scroll past the run-history table to the rendered HTML report under
> **Inspect the audit history and draft**. Put the report on screen and
> say **Report shown** when you're ready to continue.

Pause at this cue. Once the user says **Report shown**, link **Open the
saved run history** to `run_history_url` and point out the row for this
job run ID. The notebook reads the draft HTML back from that row's
`artifacts` column.

Give the saved IBNR, Mack standard error, review status, job run ID, attempt
ID and input Delta version. Describe `review_required` as pending actuarial
review. Ask the user to say **Ask Genie** to start Q&A.
Tell them before Q&A that they can open Claude in this checkout to load
the MCP server if their current session needs it.

## Ask Genie and Claude about the same run

On **Ask Genie**, run the installer action `genie` with the same profile,
catalog, schema and warehouse. Link to `genie.url` and give this question,
filling in the verified Lakeflow job run ID.

> For Mack job run RUN_ID, which origin year and development period had a
> negative incremental, and by how much? Cite the saved attempt ID.

Ask the user to say **Ask Claude** after seeing the answer. If the
workspace can't set up Genie, give the reason and offer **Ask Claude**
as the next step.

On **Ask Claude**, use the installer action `connect` for this deployment.
From the checkout, run the generated registration command for the user's
client. Reuse an existing entry with matching settings. If its name is
already used by a different deployment, choose an unused name for this
entry, such as `ipc-reserving-SCHEMA`, and keep the other entry.

In Claude Code, check **/mcp** before the question. If the tools aren't
loaded, have the user open a new session in this checkout. Give the
question with the actual job run ID so it also works in a fresh session.

> Use the reserving MCP server to look up Mack job run RUN_ID. What IBNR
> and Mack standard error did it save? Which diagnostic warnings were
> recorded? Give the attempt ID, input Delta version, and Databricks run link.

Use the read-only `get_raa_run` tool for that job run ID. Link back to the
same Databricks run the user opened for the draft.

Return the workspace, job links, selected Delta version, run link, saved
IBNR and report path for a completed rehearsal. Report a draft as pending
actuarial review. To repeat the same workflow in the workspace UI, open the
deployed job links and use **Run now with different parameters**. Upload
`raa.csv` first or use the filename returned by the rehearsal.
