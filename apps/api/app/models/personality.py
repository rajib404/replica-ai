from pydantic import BaseModel, Field


# ─── Response models ─────────────────────────────────────


class TraitItem(BaseModel):
    name: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    confirmed: bool | None = None  # owner confirmed/rejected, None = unreviewed


class CommunicationStyle(BaseModel):
    formality: str = "neutral"  # casual / neutral / formal
    verbosity: str = "moderate"  # terse / moderate / verbose
    emoji_usage: str = "low"  # none / low / moderate / heavy
    tone: str = "friendly"  # warm / friendly / neutral / professional / blunt


class HumorPatterns(BaseModel):
    style: str = "none"  # dry / sarcastic / self_deprecating / puns / observational / none
    frequency: str = "low"  # none / low / moderate / high
    examples: list[str] = []


class EmotionDetection(BaseModel):
    emotion: str  # happy / sad / anxious / angry / neutral / excited / lonely / stressed
    intensity: float = Field(ge=0.0, le=1.0)
    secondary_emotions: list[str] = []
    context_summary: str | None = None


class PersonalityProfileResponse(BaseModel):
    owner_id: str
    traits: list[TraitItem]
    communication_style: CommunicationStyle
    humor_patterns: HumorPatterns
    values_and_beliefs: list[TraitItem]
    phrases_and_idioms: list[str]
    emotional_baseline: dict[str, float]
    messages_analyzed: int
    last_analysis_at: str | None = None


class TraitListResponse(BaseModel):
    traits: list[TraitItem]
    total: int


class EmotionTrendEntry(BaseModel):
    date: str
    emotion: str
    intensity: float
    count: int


class EmotionTrendResponse(BaseModel):
    current_emotion: EmotionDetection | None = None
    trend: list[EmotionTrendEntry]
    period_days: int


# ─── Request models ──────────────────────────────────────


class RefreshPersonalityRequest(BaseModel):
    force: bool = False  # force re-analysis even if threshold not reached


class UpdateTraitRequest(BaseModel):
    trait_name: str
    confirmed: bool  # True = confirm, False = reject


class UpdateTraitsRequest(BaseModel):
    updates: list[UpdateTraitRequest]
