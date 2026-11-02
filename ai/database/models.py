from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime
)

from ai.database.database import Base


class Incident(Base):

    __tablename__ = "incidents"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    pod_name = Column(
        String,
        nullable=False,
        index=True
    )

    namespace = Column(
        String,
        nullable=False
    )

    status = Column(
        String,
        nullable=False
    )

    root_cause = Column(
        Text,
        nullable=True
    )

    confidence = Column(
        String,
        nullable=True
    )

    impact = Column(
        Text,
        nullable=True
    )

    recommended_fix = Column(
        Text,
        nullable=True
    )

    evidence = Column(
        Text,
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )