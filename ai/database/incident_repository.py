import json

from ai.database.database import SessionLocal
from ai.database.models import Incident


def save_incident(
    pod_name,
    namespace,
    health_result,
    rca
):

    db = SessionLocal()

    try:

        incident = Incident(
            pod_name=pod_name,
            namespace=namespace,

            status=health_result.get(
                "status"
            ),

            root_cause=rca.get(
                "root_cause"
            ),

            confidence=rca.get(
                "confidence"
            ),

            impact=rca.get(
                "impact"
            ),

            recommended_fix=json.dumps(
                rca.get(
                    "recommended_fix",
                    []
                )
            ),

            evidence=json.dumps(
                rca.get(
                    "evidence",
                    []
                )
            )
        )

        db.add(incident)

        db.commit()

        db.refresh(incident)

        return incident

    finally:

        db.close()


def get_recent_incidents(
    limit=20
):

    db = SessionLocal()

    try:

        incidents = (
            db.query(Incident)
            .order_by(
                Incident.created_at.desc()
            )
            .limit(limit)
            .all()
        )

        return incidents

    finally:

        db.close()