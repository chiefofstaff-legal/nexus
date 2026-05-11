"""SOP (Standard Operating Procedure) models."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class StepType(str, Enum):
    TEXT_INPUT = "text_input"
    BOOLEAN = "boolean"
    FILE_UPLOAD = "file_upload"
    SELECT = "select"
    CHECKLIST = "checklist"
    APPROVAL = "approval"


class SOPStep(BaseModel):
    """A single step in an SOP."""
    id: str
    prompt: str
    step_type: StepType = StepType.TEXT_INPUT
    required: bool = True
    options: list[str] = Field(default_factory=list)  # For SELECT type
    checklist_items: list[str] = Field(default_factory=list)  # For CHECKLIST type
    on_false: Optional[str] = None  # For BOOLEAN type: action if false
    validation_hint: Optional[str] = None


class SOPDefinition(BaseModel):
    """A complete SOP definition."""
    id: str
    name: str
    description: str
    category: str = "general"
    steps: list[SOPStep]
    output_template: Optional[str] = None


class SOPExecution(BaseModel):
    """Runtime state of an SOP execution."""
    sop_id: str
    sop_name: str
    current_step_index: int = 0
    total_steps: int
    responses: dict[str, Any] = Field(default_factory=dict)
    completed: bool = False
    halted: bool = False
    halt_reason: Optional[str] = None

    @property
    def progress_pct(self) -> float:
        return (self.current_step_index / self.total_steps) * 100 if self.total_steps else 0

    @property
    def current_step_id(self) -> Optional[str]:
        return None  # Set by the engine based on SOP definition
