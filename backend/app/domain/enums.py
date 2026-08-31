from enum import StrEnum

class Phase(StrEnum):
    OPENING = "opening"
    EXPLORE = "explore"
    TENSION = "tension"
    DEEPEN = "deepen"
    CLOSE = "close"

class Action(StrEnum):
    SILENCE = "SILENCE"
    PASS = "PASS"
    PROBE = "PROBE"
    REFRAME = "REFRAME"
    GROUND = "GROUND"
    CLOSE = "CLOSE"

class DisagreementType(StrEnum):
    FACT_CONFLICT = "fact_conflict"
    CAUSAL_DISAGREEMENT = "causal_disagreement"
    LAYER_MISMATCH = "layer_mismatch"
    DEFINITION_MISMATCH = "definition_mismatch"
    VALUE_CONFLICT = "value_conflict"
    EXPERIENCE_GAP = "experience_gap"

class Level(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class SafetyLevel(StrEnum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    CRITICAL = "critical"

class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"

class InvitationPreference(StrEnum):
    MANY = "many"
    FEW = "few"
    NONE = "none"

class ConversationMode(StrEnum):
    ASYNC = "async"
    SYNC = "sync"
