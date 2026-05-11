"""
SOP Agent Engine
=================

Loads firm-specific SOPs from YAML, walks through steps,
collects inputs, validates, and produces structured output.
"""

import json
from pathlib import Path
from typing import Any, Optional

import yaml

from models.sop import SOPDefinition, SOPExecution, SOPStep, StepType


class SOPEngine:
    """Load and execute Standard Operating Procedures."""

    def __init__(self, sop_dir: Path):
        self.sop_dir = sop_dir
        self.sop_dir.mkdir(parents=True, exist_ok=True)
        self.sops: dict[str, SOPDefinition] = {}
        self._load_sops()

    def _load_sops(self):
        """Load all SOP definitions from YAML files."""
        for yaml_file in self.sop_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                if data:
                    sop = SOPDefinition(**data)
                    self.sops[sop.id] = sop
            except Exception:
                pass  # Skip malformed SOPs

    def list_sops(self) -> list[dict]:
        """List available SOPs."""
        return [
            {"id": s.id, "name": s.name, "description": s.description,
             "category": s.category, "steps": len(s.steps)}
            for s in self.sops.values()
        ]

    def start_execution(self, sop_id: str) -> SOPExecution:
        """Start executing an SOP."""
        sop = self.sops.get(sop_id)
        if not sop:
            raise ValueError(f"SOP not found: {sop_id}")

        return SOPExecution(
            sop_id=sop.id,
            sop_name=sop.name,
            total_steps=len(sop.steps),
        )

    def get_current_step(self, execution: SOPExecution) -> Optional[SOPStep]:
        """Get the current step to present to the user."""
        sop = self.sops.get(execution.sop_id)
        if not sop or execution.completed or execution.halted:
            return None
        if execution.current_step_index >= len(sop.steps):
            return None
        return sop.steps[execution.current_step_index]

    def submit_response(
        self, execution: SOPExecution, response: Any
    ) -> SOPExecution:
        """Submit a response for the current step and advance."""
        sop = self.sops.get(execution.sop_id)
        if not sop or execution.completed or execution.halted:
            return execution

        step = sop.steps[execution.current_step_index]

        # Validate boolean gates
        if step.step_type == StepType.BOOLEAN and step.on_false:
            if not response:
                execution.halted = True
                execution.halt_reason = step.on_false
                return execution

        # Record response
        execution.responses[step.id] = response
        execution.current_step_index += 1

        # Check completion
        if execution.current_step_index >= len(sop.steps):
            execution.completed = True

        return execution

    def generate_output(self, execution: SOPExecution) -> dict:
        """Generate structured output from a completed SOP execution."""
        sop = self.sops.get(execution.sop_id)
        if not sop:
            return {"error": "SOP not found"}

        output = {
            "sop_name": sop.name,
            "sop_id": sop.id,
            "completed": execution.completed,
            "halted": execution.halted,
            "halt_reason": execution.halt_reason,
            "progress": f"{execution.current_step_index}/{execution.total_steps}",
            "responses": {},
        }

        for step in sop.steps:
            if step.id in execution.responses:
                output["responses"][step.id] = {
                    "prompt": step.prompt,
                    "type": step.step_type.value,
                    "response": execution.responses[step.id],
                }

        return output


def create_sample_sops(sop_dir: Path):
    """Create sample SOP YAML files for demo purposes."""
    sop_dir.mkdir(parents=True, exist_ok=True)

    # SOP 1: New Client Intake
    client_intake = {
        "id": "new-client-intake",
        "name": "New Client Intake",
        "description": "Standard procedure for onboarding a new client to the firm.",
        "category": "client_management",
        "steps": [
            {"id": "conflict_check", "prompt": "Have you completed a conflict of interest check?",
             "step_type": "boolean", "required": True,
             "on_false": "HALT: Conflict check is mandatory before proceeding with client intake."},
            {"id": "client_name", "prompt": "Enter the client's full legal name:",
             "step_type": "text_input", "required": True},
            {"id": "client_type", "prompt": "Select the client type:",
             "step_type": "select", "options": ["Individual", "Corporation", "Partnership", "Trust", "Government Entity"]},
            {"id": "matter_type", "prompt": "Select the matter type:",
             "step_type": "select", "options": ["Litigation", "Corporate", "Real Estate", "IP", "Employment", "Tax", "Family", "Criminal"]},
            {"id": "engagement_letter", "prompt": "Upload the signed engagement letter:",
             "step_type": "file_upload", "required": True},
            {"id": "onboarding_checklist", "prompt": "Complete the onboarding checklist:",
             "step_type": "checklist",
             "checklist_items": [
                 "Client ID verified", "Anti-money laundering check completed",
                 "Fee arrangement confirmed", "Retainer received",
                 "Client portal access created", "Welcome email sent",
             ]},
            {"id": "responsible_partner", "prompt": "Enter the name of the responsible partner:",
             "step_type": "text_input", "required": True},
            {"id": "partner_approval", "prompt": "Has the responsible partner approved this intake?",
             "step_type": "boolean", "required": True,
             "on_false": "HALT: Partner approval required before opening the matter."},
        ],
    }

    # SOP 2: Document Review Checklist
    doc_review = {
        "id": "document-review",
        "name": "Document Review Checklist",
        "description": "Standard checklist for reviewing incoming legal documents.",
        "category": "document_management",
        "steps": [
            {"id": "doc_type", "prompt": "What type of document is being reviewed?",
             "step_type": "select", "options": ["Contract", "Brief", "Court Filing", "Correspondence", "Evidence", "Other"]},
            {"id": "review_checklist", "prompt": "Complete the review checklist:",
             "step_type": "checklist",
             "checklist_items": [
                 "Parties correctly identified", "Dates and deadlines noted",
                 "Key terms highlighted", "Obligations mapped",
                 "Risks identified", "Cross-references verified",
             ]},
            {"id": "key_findings", "prompt": "Summarise key findings from the document:",
             "step_type": "text_input", "required": True},
            {"id": "action_required", "prompt": "Is immediate action required?",
             "step_type": "boolean",
             "on_false": None},
            {"id": "action_items", "prompt": "List any action items (if applicable):",
             "step_type": "text_input", "required": False},
        ],
    }

    # SOP 3: Matter Closure
    matter_closure = {
        "id": "matter-closure",
        "name": "Matter Closure",
        "description": "Standard procedure for closing a completed matter.",
        "category": "matter_management",
        "steps": [
            {"id": "final_invoice", "prompt": "Has the final invoice been sent and payment received?",
             "step_type": "boolean", "required": True,
             "on_false": "HALT: Final billing must be completed before matter closure."},
            {"id": "closure_checklist", "prompt": "Complete the closure checklist:",
             "step_type": "checklist",
             "checklist_items": [
                 "All documents filed and indexed", "Client notified of closure",
                 "Conflict check database updated", "Trust account reconciled",
                 "Original documents returned to client", "File archived per retention policy",
             ]},
            {"id": "outcome_summary", "prompt": "Summarise the matter outcome:",
             "step_type": "text_input", "required": True},
            {"id": "lessons_learned", "prompt": "Any lessons learned or precedents set?",
             "step_type": "text_input", "required": False},
            {"id": "partner_signoff", "prompt": "Has the responsible partner signed off on closure?",
             "step_type": "boolean", "required": True,
             "on_false": "HALT: Partner sign-off required for matter closure."},
        ],
    }

    for sop_data in [client_intake, doc_review, matter_closure]:
        path = sop_dir / f"{sop_data['id']}.yaml"
        with open(path, "w") as f:
            yaml.dump(sop_data, f, default_flow_style=False, sort_keys=False)
