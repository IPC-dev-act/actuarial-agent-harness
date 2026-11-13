# Actuary in a Box on Databricks

The LinkedIn demo runs the existing reserving harness on Databricks serverless
compute. It uses two managed Delta tables in Unity Catalog. The Python engine
still computes the reserves for one small triangle on the driver.

| Unity Catalog table | Contents |
| --- | --- |
| `ipc_reserving_demo_triangles` | RAA and deliberately gapped sample observations |
| `ipc_reserving_demo_run_history` | Each attempt, including its input Delta version, CSV and SHA-256, stage exit codes, estimates, review evidence and any draft report |

## Set up on Databricks Free Edition

1. Download and unzip the `databricks-reserving-demo` artifact from a successful
   [GitHub Actions run on this branch](https://github.com/IPC-dev-act/actuarial-agent-harness/actions/workflows/ci.yml?query=branch%3Adatabricks-integration).
   To build the same files locally, run `python -m build --wheel` from the repository
   root and use the wheel in `dist/` with [Reserving_Demo.py](Reserving_Demo.py).
2. In **Workspace**, import `Reserving_Demo.py` and upload the wheel to the
   same folder. Open the resulting notebook and connect to **Serverless**.
3. In the notebook's **Environment** pane, select a **Standard** CPU environment.
   Standard v6 uses Python 3.12. Standard v2 uses Python 3.11 and works with
   the updated wheel. Add it as a dependency using its full
   `/Workspace/…/actuarial_agent_harness-0.2.9.post1-py3-none-any.whl`
   path and click **Apply**. If your notebook lists a previous harness wheel,
   remove that dependency before applying the update.
4. Run the setup cells to create the widgets. Use a writable Unity Catalog
   catalog and schema. A blank catalog uses the current catalog, and
   `schema` defaults to `default`. The workspace identity needs to be able to
   create and write the two tables in that schema.

See [Databricks serverless environments](https://docs.databricks.com/aws/en/compute/serverless/dependencies)
and [importing workspace files](https://docs.databricks.com/aws/en/files/workspace-basics).

## Record the demo

1. **Show the input in Catalog Explorer.** Run the notebook with `raa` and
   `mack`. Open `ipc_reserving_demo_triangles` and show the sample observations.
2. **Show the run and its draft.** The history records the RAA result as
   `review_required`. Show IBNR, the Mack standard error, diagnostics and the
   sensitivity exhibits in the draft HTML report rendered in the notebook.
3. **Show the gate.** Change the dataset widget to `gapped` and run the
   notebook again. In the history, show `blocked_by_validation`, the failed
   gap check and the empty reserve fields alongside the RAA result.

Optional Lakeflow recording step. Create a job with a serverless Notebook
task pointing at the imported notebook. Set the task's `job_run_id`
parameter to `{{job.run_id}}`. Use dataset and method task parameters to
choose the run. The resulting Delta row links back to that Lakeflow run.
The deliberately blocked case completes with its business outcome recorded
in Delta. Execution errors fail the task after attempting to save the evidence.

The notebook runs without an LLM. The report is the existing deterministic
harness report and stays in draft status for human review.
