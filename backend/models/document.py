"""Document models for the ingestion pipeline."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    CONTRACT = "contract"
    BRIEF = "brief"
    CORRESPONDENCE = "correspondence"
    COURT_FILING = "court_filing"
    INVOICE = "invoice"
    MEMORANDUM = "memorandum"
    NDA = "nda"
    OTHER = "other"
    DECISION = "dec"        # TODO: Leandro to confirm DEC = Entscheidung/Décision/Decisione (Swiss federal court decision)
    REGULATION = "rse"      # TODO: Leandro to confirm RSE = Recueil Systématique (Federal collection of regulations)?
    JUDGMENT = "rsg"        # TODO: Leandro to confirm RSG = exact semantic — placeholder Judgment


class ExtractionResult(BaseModel):
    """Raw text extracted from a document."""
    text: str
    page_count: int
    method: str  # "pymupdf4llm" or "claude_haiku"
    source_path: str


class ClassificationResult(BaseModel):
    """LLM-based document classification."""
    document_type: DocumentType
    confidence: float = Field(ge=0.0, le=1.0)
    parties: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    matter_reference: Optional[str] = None
    jurisdiction: Optional[str] = None
    summary: str = ""


class FilingResult(BaseModel):
    """Auto-generated filename and path."""
    original_path: str
    new_filename: str
    new_path: str
    document_type: DocumentType
    confidence: float


class DocumentRecord(BaseModel):
    """Complete document record after full pipeline."""
    id: str
    original_filename: str
    filed_path: str
    document_type: DocumentType
    classification_confidence: float
    parties: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    matter_reference: Optional[str] = None
    jurisdiction: Optional[str] = None
    summary: str = ""
    page_count: int = 0
    extraction_method: str = ""
    indexed_at: datetime = Field(default_factory=datetime.utcnow)
    chunk_count: int = 0
