"""Trading protocols (Mark 1 Stage 3.1) and proactive alerts (Stage 3.2). Deterministic;
no AI anywhere. Importing the package registers the actions."""

from protocols.actions import REGISTRY
from protocols.registry import (
    ActionError,
    ActionRegistry,
    ActionSpec,
    ProtocolSpec,
    StepSpec,
    validate_steps,
)

__all__ = [
    "REGISTRY",
    "ActionError",
    "ActionRegistry",
    "ActionSpec",
    "ProtocolSpec",
    "StepSpec",
    "validate_steps",
]
