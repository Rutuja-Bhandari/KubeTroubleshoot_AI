from dataclasses import dataclass, field


@dataclass
class RemediationAction:
    action_id: str
    action_type: str
    description: str
    command: str
    risk_level: str
    requires_approval: bool
    reason: str
    metadata: dict = field(default_factory=dict)