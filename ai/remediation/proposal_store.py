
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


DB_PATH = (
    Path(__file__).resolve().parents[2]
    / "remediation_proposals.db"
)


def get_connection():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_proposal_store():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS remediation_proposals (
                proposal_id TEXT PRIMARY KEY,
                action_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                pod_name TEXT NOT NULL,
                namespace TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                result_json TEXT
            )
        """)


def create_proposal(action, pod_name, namespace):
    proposal_id = str(uuid4())
    metadata = dict(action.metadata or {})
    metadata["pod_name"] = pod_name
    metadata["namespace"] = namespace

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO remediation_proposals (
                proposal_id, action_id, action_type,
                pod_name, namespace, metadata_json,
                status, created_at, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                proposal_id,
                action.action_id,
                action.action_type,
                pod_name,
                namespace,
                json.dumps(metadata),
                "PENDING_APPROVAL",
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    return proposal_id


def get_proposal(proposal_id):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM remediation_proposals
            WHERE proposal_id = ?
            """,
            (proposal_id,),
        ).fetchone()

    if row is None:
        return None

    proposal = dict(row)
    proposal["metadata"] = json.loads(proposal.pop("metadata_json"))
    proposal["result"] = (
        json.loads(proposal.pop("result_json"))
        if proposal.get("result_json")
        else None
    )
    return proposal



def claim_proposal(proposal_id):
    """Atomically claim a pending proposal for execution."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE remediation_proposals
            SET status = 'EXECUTING'
            WHERE proposal_id = ?
              AND status = 'PENDING_APPROVAL'
            """,
            (proposal_id,),
        )
        return cursor.rowcount == 1


def update_proposal_status(proposal_id, status, result=None):
    """Record the result after a proposal has been claimed."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE remediation_proposals
            SET status = ?, result_json = ?
            WHERE proposal_id = ?
              AND status IN ('EXECUTING', 'IN_PROGRESS')
            """,
            (
                status,
                json.dumps(result) if result is not None else None,
                proposal_id,
            ),
        )
        return cursor.rowcount == 1