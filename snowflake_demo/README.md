# Actuary in Snowflake

Run the same public RAA reserving workflow as the Databricks demo. Snowflake
stages the CSV, pins the import, runs the shared Python harness and stores the
original report and evidence. A successful query can still produce a draft
requiring actuarial review or stop before fitting if validation fails.

## Connect once

The demo reuses a named [Python Connector connection] from outside the checkout.
Use `ipc_demo` or pass `--connection YOUR_PROFILE` if you already have a
working connection. You can use that same profile from every fresh clone on
this machine.

For a standalone trial, configure [key-pair authentication] once. If you
already generated a key and have an `ALTER USER` statement for it, go to step 2.

1. Generate a local key pair using Snowflake's guide. Keep the private key
   on your machine. Use your Snowflake user object name in the SQL statement
   and your `LOGIN_NAME` in the connector profile.
2. In Snowsight, open an existing `.sql` file from **Recent projects**, or
   open **Workspaces → + Add New → SQL File**. Select a role authorized to
   register the public key and a warehouse. Paste the full `ALTER USER`
   statement into the SQL editor and click **▶ Run**. For a new registration,
   Snowflake recommends a [named key pair]. An existing generated statement
   that uses `SET RSA_PUBLIC_KEY` works with an unused key slot.
3. Use `authenticator = "SNOWFLAKE_JWT"` and `private_key_file` in your local
   connector profile. Run `sf_demo check` below once to verify the role and
   warehouse before recording.

Use [browser-based SSO] with `externalbrowser` when your Snowflake account
has a SAML identity provider configured. A SAML identity provider error on a
standalone trial is a cue to use the key-pair setup above.

## Set up the demo

The CLI uses `COMPUTE_WH` by default. The setup role needs access to a usable
warehouse, privileges to create the demo database and schema objects, and
permission to use the [shared PyPI repository]. The trial's AI features are a
separate capability.

From the repository root, build the wheel and define a terminal shortcut:

```bash
uv build --wheel
sf_demo() { uv run --no-project --python 3.12 --with snowflake-connector-python python -m snowflake_demo.demo "$@"; }
sf_demo check
sf_demo setup
```

Defaults are `IPC_RESERVING_DEMO.DEMO`, `COMPUTE_WH` and `ipc_demo`. Pass
`--connection`, `--database`, `--schema` or `--warehouse` before a subcommand to
override them. Rerunning setup updates the procedure and views and preserves
previous imports and attempts.

## Import, run and inspect

```bash
sf_demo import --dataset raa
sf_demo run <import_id> --method mack
sf_demo inspect <attempt_id>
sf_demo report <attempt_id> --output raa-draft.html
```

1. Import stages the CSV, runs `COPY INTO`, checks that the loaded rows match
   the supplied CSV, and saves a new snapshot. Open `RESERVING_TRIANGLES` in
   Snowsight and filter on the returned import ID. The default RAA fixture has
   55 observations. The snapshot retains both the raw file hash and the hash of
   the canonical CSV that is sent to the model.
2. Run calls `RUN_RESERVING` on the chosen import and method. Each invocation
   creates a new attempt. The result includes its Snowflake query ID for
   Snowsight Query History. The backend also tags the call
   `ipc-reserving:<attempt_id>` so the query can be located after a lost client
   connection. Reimporting the same file returns a new import ID and leaves the
   old snapshot available for reruns.
3. Inspect reads `RESERVING_RUNS` and `RESERVING_WARNINGS`. Report downloads the
   exact HTML stored for the selected attempt. Open it in a browser or deploy
   the Snowflake viewer with `sf_demo setup-viewer`. In Snowsight, open the
   `RESERVING_REVIEW` Streamlit app and choose the same attempt.

| Demo case | IBNR | Mack standard error | Expected state |
|---|---:|---:|---|
| `raa`, `mack` | 52,135.23 | 26,909.01 | Draft, review required |
| `raa`, `chain_ladder` | 52,135.23 | Null | Draft, review required |
| `gapped`, `mack` | Null | Null | `no_gaps` blocks fitting and no draft is saved |

## Run Mack yourself in Snowsight

Open a SQL file in Snowsight, select your warehouse, and replace `<import_id>`
with the ID returned by `sf_demo import`. Use your demo database and schema
if they differ from these defaults. Paste the full statement and click
**▶ Run**.

```sql
CALL IPC_RESERVING_DEMO.DEMO.RUN_RESERVING(
  '<import_id>',
  'mack',
  LOWER(REPLACE(UUID_STRING(), '-', '')),
  NULL::VARCHAR
);
```

Copy the new `attempt_id` from the result. Use it with `sf_demo inspect`
and `sf_demo report` to read the evidence and download the draft for the
run you just started. Find this `CALL` in Snowsight Query History for its
query ID.

The procedure stores its Python handler inline, from `snowflake_demo/procedure.py`.
It loads `ipc_reserving_harness.zip` from `RESERVING_FILES/bundles/<bundle_sha256>/`.
Inside the ZIP, `databricks_demo/reserving.py` runs the shared harness and
`engine/chainladder_adapter.py` calls the `chainladder` implementation of Mack.

## Run as a Snowflake Task

For the on-demand Snowflake job view, use `sf_demo setup-task` and
`sf_demo run-task <import_id> --method mack`. The task owner role needs the
account-level `EXECUTE TASK` privilege and warehouse access. The task has no
schedule. Submission returns the attempt ID. Check the `RESERVING_JOB` Task
History in Snowsight, then pass the attempt ID to `inspect`. The saved evidence
includes the Snowflake task run group ID for this route.

## Ask about a saved attempt

In Snowsight, the trial-compatible route is to query the view directly:

```sql
SELECT ATTEMPT_ID, STATUS, NEGATIVE_ORIGIN, NEGATIVE_DEVELOPMENT_AGE,
       NEGATIVE_INCREMENTAL, IBNR, MACK_SE
FROM IPC_RESERVING_DEMO.DEMO.RESERVING_RUNS
WHERE ATTEMPT_ID = '<mack_attempt_id>';
```

The saved negative incremental is **−103 at origin 1982 and development age 7**.
If the account has [Cortex Agents] enabled, `sf_demo setup-qa` creates a semantic
view and the `RESERVING_ASSISTANT` agent for the same evidence. Ask which origin
and age triggered the check and request the attempt ID in the answer.

For Claude, use a separate `ipc_demo_reader` connection with warehouse,
database and schema usage and `SELECT` on `RESERVING_RUNS` and
`RESERVING_WARNINGS`. From the repository root, register the stdio server:

```bash
claude mcp add snowflake-reserving -- uv run --no-project --python 3.12 --with snowflake-connector-python --with mcp==1.28.1 python -m snowflake_demo.reserving_mcp --connection ipc_demo_reader
```

Ask it for IBNR, Mack standard error and the warnings for the same attempt.
The MCP server exposes a single read-only lookup by attempt ID. The reader role
can be scoped to the two evidence views, which omit the raw CSV and report HTML.

## Verify the runtime

The packaged handler can be checked locally and in the trial. Build the wheel
first. The local command uses the project's pinned scientific packages:

```bash
uv run --python 3.12 python snowflake_demo/runtime_probe.py \
  dist/actuarial_agent_harness-0.2.9.post2-py3-none-any.whl --local
```

For the standalone live probe, set the named connection's database, schema and
warehouse to existing objects, then run:

```bash
uv run --no-project --python 3.12 --with snowflake-connector-python \
  python snowflake_demo/runtime_probe.py \
  dist/actuarial_agent_harness-0.2.9.post2-py3-none-any.whl --connection ipc_demo
```

The live probe uses a temporary stage and procedure. The workflow uses a
content-addressed stage location for the wheel and records its SHA-256 on each
attempt. Both routes unpack the staged wheel so the shared renderer can open
its packaged HTML template as a regular file.

[Python Connector connection]: https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect
[browser-based SSO]: https://docs.snowflake.com/en/user-guide/admin-security-fed-auth-use#browser-based-sso
[key-pair authentication]: https://docs.snowflake.com/en/user-guide/key-pair-auth
[shared PyPI repository]: https://docs.snowflake.com/en/developer-guide/udf/python/udf-python-packages
[Cortex Agents]: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents
[named key pair]: https://docs.snowflake.com/en/sql-reference/sql/alter-user-add-key-pair
