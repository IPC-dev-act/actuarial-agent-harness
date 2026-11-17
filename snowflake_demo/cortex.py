"""Optional native Q&A over saved reserving evidence."""

import json


def deploy_qa(cursor, namespace, warehouse):
    semantic_view = f"{namespace}.RESERVING_SEMANTICS"
    agent = f"{namespace}.RESERVING_ASSISTANT"
    cursor.execute(f"""
        CREATE OR REPLACE SEMANTIC VIEW {semantic_view}
        TABLES (runs AS {namespace}.RESERVING_RUNS PRIMARY KEY (ATTEMPT_ID))
        FACTS (
            runs.ibnr AS IBNR COMMENT = 'Saved IBNR for one reserving attempt',
            runs.mack_standard_error AS MACK_SE COMMENT = 'Saved Mack standard error, null for Basic Chain Ladder',
            runs.negative_incremental AS NEGATIVE_INCREMENTAL COMMENT = 'Negative incremental from the saved validation check'
        )
        DIMENSIONS (
            runs.attempt_id AS ATTEMPT_ID,
            runs.import_id AS IMPORT_ID,
            runs.method AS METHOD,
            runs.status AS STATUS,
            runs.negative_origin AS NEGATIVE_ORIGIN,
            runs.negative_development_age AS NEGATIVE_DEVELOPMENT_AGE
        )
        COMMENT = 'Saved actuarial reserving attempts and their review status'
        AI_SQL_GENERATION 'When a question specifies an attempt ID, filter on that exact attempt. Return the saved value and attempt ID. Avoid summing amounts across attempts.'
        COPY GRANTS
    """)
    specification = {
        "models": {"orchestration": "auto"},
        "instructions": {
            "orchestration": "Use the ReservingEvidence tool to retrieve saved evidence. Ask for the attempt ID when it is missing.",
            "response": "Cite the attempt ID and saved review status. Report saved values and distinguish the Mack standard error from the reserve estimate.",
            "sample_questions": [{"question": "Which origin year and development age had a negative incremental on attempt <attempt_id>, and by how much?"}],
        },
        "tools": [{"tool_spec": {
            "type": "cortex_analyst_text_to_sql", "name": "ReservingEvidence",
            "description": "Query the saved figures and validation evidence for a specific reserving attempt.",
        }}],
        "tool_resources": {"ReservingEvidence": {
            "semantic_view": semantic_view, "execution_environment": {"type": "warehouse", "warehouse": warehouse},
        }},
    }
    cursor.execute(f"""
        CREATE OR REPLACE AGENT {agent} COPY GRANTS
        FROM SPECIFICATION
        $${json.dumps(specification)}$$
    """)
    return {"semantic_view": semantic_view, "agent": agent}
