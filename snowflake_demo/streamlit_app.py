"""Review saved Snowflake reserving attempts and the original draft HTML."""

import streamlit as st
import streamlit.components.v1 as components
from snowflake.snowpark.context import get_active_session


NAMESPACE = "__DEMO_SCHEMA__"
st.set_page_config(page_title="Actuary in Snowflake", layout="wide")
st.title("Actuary in Snowflake")
session = get_active_session()
run_rows = session.sql(f"""
    SELECT ATTEMPT_ID, IMPORT_ID, DATASET, METHOD, STATUS, IBNR, MACK_SE, STARTED_AT, INPUT_SHA256,
           PLATFORM_QUERY_ID, TASK_RUN_GROUP_ID, REPORT_AVAILABLE
    FROM {NAMESPACE}.RESERVING_RUNS ORDER BY STARTED_AT DESC, ATTEMPT_ID LIMIT 50
""").collect()
if not run_rows:
    st.info("Run a reserving attempt to view its results here.")
    st.stop()

attempts = {row["ATTEMPT_ID"]: row for row in run_rows}
selected_id = st.selectbox("Saved attempt", list(attempts), format_func=lambda key: (
    f"{attempts[key]['DATASET']} · {attempts[key]['METHOD']} · {key}"
))
selected = attempts[selected_id]
status = selected["STATUS"].replace("_", " ").capitalize()
for column, label, value in zip(
    st.columns(3), ("Status", "IBNR", "Mack standard error"),
    (status, selected["IBNR"], selected["MACK_SE"]), strict=True,
):
    column.metric(label, f"{value:,.2f}" if isinstance(value, (float, int)) else value or "—")
st.caption(f"Import {selected['IMPORT_ID']} · SHA-256 {selected['INPUT_SHA256']}")
if selected["PLATFORM_QUERY_ID"]:
    st.caption(f"Snowflake query {selected['PLATFORM_QUERY_ID']}")
if selected["TASK_RUN_GROUP_ID"]:
    st.caption(f"Snowflake task run group {selected['TASK_RUN_GROUP_ID']}")

warnings = session.sql(f"""
    SELECT CHECK_STAGE, CHECK_ID, VERDICT, DETAILS FROM {NAMESPACE}.RESERVING_WARNINGS
    WHERE ATTEMPT_ID = ? ORDER BY CHECK_STAGE, CHECK_ID
""", params=[selected_id]).collect()
if warnings:
    st.subheader("Validation and diagnostic findings")
    st.dataframe([row.as_dict() for row in warnings], use_container_width=True)
if selected["REPORT_AVAILABLE"]:
    rows = session.sql(f"""
        SELECT REPORT_HTML FROM {NAMESPACE}.RESERVING_REPORTS WHERE ATTEMPT_ID = ?
    """, params=[selected_id]).collect()
    if rows:
        report = rows[0]["REPORT_HTML"]
        st.download_button("Download draft report", report, file_name=f"reserving-{selected_id}.html", mime="text/html")
        components.html(report, height=780, scrolling=True)
