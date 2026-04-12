"""Pydantic models for the fine-tuning system."""

from pydantic import BaseModel, Field


# ─── Training Data ──────────────────────────────────────


class TrainingPair(BaseModel):
    """A single (input, output) example for fine-tuning."""

    input: str
    output: str
    source: str = "conversation"  # conversation | knowledge | personality


class TrainingDataSourceStats(BaseModel):
    conversation_pairs: int = 0
    knowledge_pairs: int = 0
    personality_pairs: int = 0
    filtered_out: int = 0


class TrainingDataStats(BaseModel):
    owner_id: str
    total_pairs: int
    sources: TrainingDataSourceStats
    sufficient: bool  # >= finetune_min_pairs
    minimum_recommended: int
    holdout_size: int
    sample_pairs: list[TrainingPair] = []
    generated_at: str | None = None


class GenerateDataRequest(BaseModel):
    save_to_disk: bool = True


class GenerateDataResponse(BaseModel):
    stats: TrainingDataStats
    training_file_path: str | None = None
    warnings: list[str] = []


# ─── Fine-tune Job ──────────────────────────────────────


class FineTuneStartRequest(BaseModel):
    base_model: str | None = None
    use_existing_data: bool = True
    notes: str | None = Field(default=None, max_length=500)


class FineTuneJob(BaseModel):
    version_id: str
    owner_id: str
    version: int
    model_name: str
    base_model: str
    status: str  # pending | preparing | training | evaluating | completed | failed | rolled_back
    training_pair_count: int
    training_data_path: str | None = None
    progress: dict | None = None
    metrics: dict | None = None
    is_active: bool
    error_message: str | None = None
    started_at: str
    completed_at: str | None = None


class FineTuneStatusResponse(BaseModel):
    current_job: FineTuneJob | None = None
    queued: bool = False
    last_completed: FineTuneJob | None = None


# ─── Versions / Rollback ────────────────────────────────


class ModelVersionInfo(BaseModel):
    version_id: str
    version: int
    model_name: str
    base_model: str
    status: str
    is_active: bool
    training_pair_count: int
    metrics: dict | None = None
    started_at: str
    completed_at: str | None = None


class ModelVersionsResponse(BaseModel):
    versions: list[ModelVersionInfo]
    active_version: int | None = None
    total: int


class RollbackRequest(BaseModel):
    version: int = Field(..., ge=1)


class RollbackResponse(BaseModel):
    success: bool
    new_active_version: int | None = None
    message: str


# ─── Evaluation ─────────────────────────────────────────


class EvaluationMetric(BaseModel):
    name: str
    value: float
    description: str | None = None


class EvaluationSample(BaseModel):
    input: str
    expected: str
    base_response: str
    finetuned_response: str
    similarity_score: float | None = None


class EvaluationResult(BaseModel):
    version_id: str
    version: int
    sample_count: int
    metrics: list[EvaluationMetric]
    base_metrics: list[EvaluationMetric]
    samples: list[EvaluationSample] = []
    summary: str


class EvaluateRequest(BaseModel):
    version: int | None = None  # None = latest


# ─── Configuration ──────────────────────────────────────


class FineTuneConfigBody(BaseModel):
    auto_approve: bool = False
    auto_trigger_enabled: bool = False
    base_model: str = "mistral:7b-instruct"
    trigger_message_count: int = Field(default=500, ge=50, le=10_000)


class FineTuneConfigResponse(BaseModel):
    owner_id: str
    auto_approve: bool
    auto_trigger_enabled: bool
    base_model: str
    trigger_message_count: int
    last_trigger_message_total: int
    current_owner_message_count: int
    pending_messages_until_trigger: int
