---
name: install-snowflake-reserving
description: Set up Actuary in Snowflake from a fresh checkout and guide a recorded public RAA Mack run through input, Snowpark execution and the saved draft.
---

# Install Actuary in Snowflake

Run from the root of the `snowflake-integration` checkout. Read
[snowflake_demo/README.md](../../../snowflake_demo/README.md) for account
setup and troubleshooting. Use the public RAA fixture for the walkthrough.

## Prepare the checkout and connection

- Check for `uv`. Help the user install it using the [official uv instructions](https://docs.astral.sh/uv/getting-started/installation/) if missing.
- Reuse a named Snowflake Python Connector profile if the user gives one.
  Otherwise run `check` against `ipc_demo`. Reuse a working profile across
  fresh clones. An available warehouse and a role that can create the demo
  objects are required.
- If the profile is missing or `externalbrowser` fails with a SAML identity
  provider error, follow [the one-time sign-in instructions](../../../snowflake_demo/README.md#connect-once).
  For a standalone trial, guide the user through key-pair setup. Reuse any
  key they already generated for this profile. Use `externalbrowser` for
  accounts with configured SAML SSO.
- When a public-key registration statement is ready, give the full click
  path and wait for this cue:

  > Open your `.sql` file in Snowsight, or choose **Workspaces → + Add New → SQL File**.
  > Paste the full `ALTER USER …` statement into the SQL editor and click
  > **▶ Run**. When Snowsight confirms success, say **Key added**.

  Save `ipc_demo` in the local connector configuration outside the checkout.
  Rerun `check` after the cue and continue when it returns the role and warehouse.
- Build the wheel with `uv build --wheel --python 3.12`.

Use this prefix for each command. Prepend `--connection`, `--database`,
`--schema` and `--warehouse` before the subcommand if overriding defaults.
Keep the same values throughout the recording.

```bash
uv run --no-project --python 3.12 --with snowflake-connector-python python -m snowflake_demo.demo
```

The default target is `IPC_RESERVING_DEMO.DEMO` and `COMPUTE_WH`.
For a repeat recording in the same database, use the next unused demo
schema, checking the list in Snowsight first. Keep the screen on the
selected Snowflake account throughout the walkthrough.

## Record the first live run

Create a fresh local evidence folder under `runs/`. Save each command's
successful JSON output there and cite the saved fields for any figure you
state. Keep each cue short and wait for it before taking the next action.

1. **Set up the demo.** Ask the user to open Snowflake's Database Explorer
   in Snowsight. On their cue, run `setup`. Confirm the demo database,
   schema and procedure from the returned output.
2. **Run the import.** On their cue, run `import --dataset raa`. Verify the
   55 observations and retain the returned import ID. Tell the user to
   refresh Snowsight and open the `RESERVING_TRIANGLES` view. Give them a
   `SELECT` filtered to the actual import ID to show the imported rows.
3. **Run Mack.** On their cue, run `run IMPORT_ID --method mack`. Run
   `inspect ATTEMPT_ID` with the returned ID and verify that the saved run
   matches the import and carries `review_required`. The reference result
   is 52,135.23 IBNR and 26,909.01 Mack standard error. State figures from
   the saved output and explain the pending review. Run
   `report ATTEMPT_ID --output PATH` into the evidence folder. Open the
   resulting HTML in a browser if possible and give the user its full path.
4. **Report shown.** Pause while the user shows the draft. Then give the
   query ID for Snowflake Query History and the attempt ID. If the user
   wants an evidence question, use the Snowsight SQL example from the guide
   with that exact attempt ID. The saved check should show origin 1982,
   development age 7 and a −103 incremental.

For this first take, use the direct Snowpark procedure. If a step fails,
identify the failing command, its Snowflake error or query ID when present,
and fix recoverable setup issues before resuming the same cue. Reuse the
saved IDs after an interruption. Treat local test results as local evidence.
