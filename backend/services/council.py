"""
Multi-LLM Council — parallel fan-out + synthesis + IDR logging.

Every decision that matters (sensitivity classification, semantic labelling,
vision-or-text routing) runs through the Council. The Council fans out a
single query to multiple providers in parallel, collects their votes,
synthesises a final decision with honest confidence, and appends an Intent
Decision Record to the tamper-evident chain.

Honesty guarantees:

- **Majority is not certainty.** Final confidence is the supporting-model
  average confidence multiplied by the agreement ratio, so 2/3 votes with
  0.8 self-reported confidence collapses to 0.53 final confidence, not
  0.8. This is the mechanism that prevents demo-day confidence inflation.
- **Dissent is recorded.** If any council member disagrees with the
  majority, the synthesis_method is marked ``devils_advocate`` and the
  dissenting reasoning is preserved in the IDR for audit review.
- **Failed members are still logged.** A council member that errors
  (timeout, API outage, bad parse) does not silently vanish — it appears
  in ``council_votes`` with ``error`` populated so reviewers can see the
  real attack surface.
"""

import asyncio
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from core.idr_store import IDRStore
from core.intent_decision_record import (
    CouncilVote,
    DecisionPoint,
    IntentDecisionRecord,
    SynthesisMethod,
)


@dataclass
class CouncilQuery:
    """A single question posed to the council."""

    decision_point: DecisionPoint
    system_prompt: str
    user_prompt: str
    input_hash: str
    input_summary: str
    falsification_criterion: str
    allowed_decisions: Optional[list[str]] = None
    metadata: dict = field(default_factory=dict)

    def to_idr(
        self,
        decision: str,
        confidence: float,
        confidence_rationale: str,
        reasoning: str,
        council_votes: list[CouncilVote],
        synthesis_method: SynthesisMethod,
        synthesised_falsification: str = "",
    ) -> IntentDecisionRecord:
        """Build an IDR from this query plus the synthesised verdict fields.

        Information Expert: ``CouncilQuery`` owns the input-shaped data
        (decision_point, input_hash, input_summary, falsification_criterion,
        metadata), so it also owns the construction of an IDR from those
        fields plus the verdict. The Council orchestrator only decides what
        the verdict IS; it doesn't know how to assemble a record.

        ``synthesised_falsification`` is the document-specific refutation
        observation the council itself produced. If present it overrides
        the query's ``falsification_criterion``, which is retained as a
        static fallback for when every model errored out or refused to
        supply one.
        """
        criterion = synthesised_falsification or self.falsification_criterion
        return IntentDecisionRecord(
            decision_point=self.decision_point,
            input_hash=self.input_hash,
            input_summary=self.input_summary,
            decision=decision,
            confidence=confidence,
            confidence_rationale=confidence_rationale,
            reasoning=reasoning,
            council_votes=council_votes,
            synthesis_method=synthesis_method,
            falsification_criterion=criterion,
            metadata=self.metadata,
        )


@dataclass
class CouncilResult:
    """The synthesised verdict + the signed IDR that was written."""

    decision: str
    confidence: float
    confidence_rationale: str
    reasoning: str
    votes: list[CouncilVote]
    synthesis_method: SynthesisMethod
    idr: dict


_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
_GROQ_MODEL = "llama-3.3-70b-versatile"
_RESPONSE_FORMAT_INSTRUCTION = (
    'Respond ONLY with a single JSON object, no prose, no code fences: '
    '{"decision": "<one of the allowed labels>", '
    '"confidence": <float 0.0 to 1.0>, '
    '"reasoning": "<one or two sentences citing the SPECIFIC evidence in this '
    'document that drove your decision>", '
    '"falsification": "<one or two sentences naming the SPECIFIC observation '
    'that would prove your decision wrong — reference concrete document '
    'evidence, not generic templates. Name both under- and over-classification '
    'failure modes where the label allows it.>"}'
)


class Council:
    """Parallel-fan-out multi-LLM council with IDR logging."""

    def __init__(
        self,
        idr_store: IDRStore,
        async_anthropic_client=None,
        timeout_per_call_s: float = 5.0,
    ):
        self._store = idr_store
        self._anthropic = async_anthropic_client
        self._timeout = timeout_per_call_s
        self._groq_client = None

    def _get_groq(self):
        if self._groq_client is None:
            try:
                from groq import AsyncGroq
                self._groq_client = AsyncGroq()
            except Exception:
                self._groq_client = False
        return self._groq_client if self._groq_client else None

    async def deliberate(
        self, query: CouncilQuery, user_id: str
    ) -> CouncilResult:
        """Run the council: fan out, gather, synthesise, log.

        ``user_id`` is the acting tenant; it is threaded into
        ``IDRStore.append`` so the council's IDR is tenant-attributed
        and visible on the /idr page (it was previously written with no
        tenant_id and therefore invisible to every account).
        """
        tasks = [self._ask_anthropic(query), self._ask_groq(query)]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        votes = [v if isinstance(v, CouncilVote) else _exception_vote(v) for v in raw]

        (
            decision,
            confidence,
            method,
            rationale,
            reasoning,
            synthesised_falsification,
        ) = self._synthesise(votes)

        idr = query.to_idr(
            decision=decision,
            confidence=confidence,
            confidence_rationale=rationale,
            reasoning=reasoning,
            council_votes=votes,
            synthesis_method=method,
            synthesised_falsification=synthesised_falsification,
        )
        signed = self._store.append(idr, user_id=user_id)

        return CouncilResult(
            decision=decision,
            confidence=confidence,
            confidence_rationale=rationale,
            reasoning=reasoning,
            votes=votes,
            synthesis_method=method,
            idr=signed,
        )

    async def _ask_anthropic(self, query: CouncilQuery) -> CouncilVote:
        start = time.time()
        try:
            if not self._anthropic:
                raise RuntimeError("no anthropic client available")
            system = _compose_system_prompt(query.system_prompt, query.allowed_decisions)
            resp = await asyncio.wait_for(
                self._anthropic.messages.create(
                    model=_ANTHROPIC_MODEL,
                    max_tokens=800,
                    system=system,
                    messages=[{"role": "user", "content": query.user_prompt}],
                ),
                timeout=self._timeout,
            )
            text = resp.content[0].text if resp.content else ""
            decision, confidence, reasoning, falsification = _parse_vote(
                text, query.allowed_decisions
            )
            return CouncilVote(
                model=_ANTHROPIC_MODEL,
                provider="anthropic",
                decision=decision,
                confidence=confidence,
                reasoning=reasoning,
                falsification=falsification,
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            return _error_vote(_ANTHROPIC_MODEL, "anthropic", start, exc)

    async def _ask_groq(self, query: CouncilQuery) -> CouncilVote:
        start = time.time()
        try:
            client = self._get_groq()
            if not client:
                raise RuntimeError("no groq client available")
            system = _compose_system_prompt(query.system_prompt, query.allowed_decisions)
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=_GROQ_MODEL,
                    max_tokens=800,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": query.user_prompt},
                    ],
                ),
                timeout=self._timeout,
            )
            text = resp.choices[0].message.content or ""
            decision, confidence, reasoning, falsification = _parse_vote(
                text, query.allowed_decisions
            )
            return CouncilVote(
                model=_GROQ_MODEL,
                provider="groq",
                decision=decision,
                confidence=confidence,
                reasoning=reasoning,
                falsification=falsification,
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            return _error_vote(_GROQ_MODEL, "groq", start, exc)

    def _synthesise(
        self, votes: list[CouncilVote]
    ) -> tuple[str, float, SynthesisMethod, str, str, str]:
        """Majority + devil's advocate + honest confidence + falsification.

        Returns (decision, confidence, method, rationale, reasoning,
        falsification). The falsification is the document-specific
        refutation observation, synthesised from council votes. Empty
        string if no supporting vote supplied one; the caller falls
        back to the query's static default in that case.
        """
        valid = [v for v in votes if not v.error and v.decision]
        if not valid:
            errors = [v.error or "empty decision" for v in votes]
            return (
                "unknown",
                0.0,
                SynthesisMethod.SINGLE_MODEL,
                "all council members failed",
                f"errors: {errors}",
                "",
            )

        counts = Counter(v.decision for v in valid)
        top_decision, top_count = counts.most_common(1)[0]
        agreement = top_count / len(valid)
        supporting = [v for v in valid if v.decision == top_decision]
        dissent = [v for v in valid if v.decision != top_decision]
        avg_support_confidence = sum(v.confidence for v in supporting) / len(supporting)
        final_confidence = round(avg_support_confidence * agreement, 3)

        if len(valid) == 1:
            rationale = f"single-model decision ({valid[0].provider} only responder)"
            method = SynthesisMethod.SINGLE_MODEL
        elif agreement == 1.0:
            rationale = f"unanimous {len(valid)}/{len(valid)} on '{top_decision}'"
            method = SynthesisMethod.MAJORITY_VOTE
        else:
            rationale = (
                f"majority {top_count}/{len(valid)} on '{top_decision}', "
                f"dissent from {[v.provider for v in dissent]}"
            )
            method = SynthesisMethod.DEVILS_ADVOCATE

        # Keep each provider's reasoning long enough to be meaningful but
        # cap per-vote so the joined line stays manageable. 500 chars per
        # vote means a 3-provider council caps near 1.5 KB, which the /idr
        # UI can wrap freely without the old mid-word cut-off at 120 chars.
        reasoning = " || ".join(
            f"{v.provider}: {v.reasoning[:500]}" for v in valid
        )

        # Synthesise a document-specific falsification from the council.
        # Prefer supporting votes (they defend the majority label) so
        # the criterion is self-consistent with the decision. If dissent
        # also supplied criteria, append them under "dissent:" so a
        # reviewer can see what the minority would have looked for.
        support_criteria = [
            f"{v.provider}: {v.falsification.strip()}"
            for v in supporting
            if v.falsification.strip()
        ]
        dissent_criteria = [
            f"{v.provider} (dissent, voted '{v.decision}'): {v.falsification.strip()}"
            for v in dissent
            if v.falsification.strip()
        ]
        if support_criteria:
            falsification = " || ".join(support_criteria + dissent_criteria)
        elif dissent_criteria:
            # No majority supplied a criterion but dissent did — still useful.
            falsification = " || ".join(dissent_criteria)
        else:
            falsification = ""

        return (
            top_decision,
            final_confidence,
            method,
            rationale,
            reasoning,
            falsification,
        )


def _compose_system_prompt(base: str, allowed: Optional[list[str]]) -> str:
    """Combine the caller's system prompt with a JSON-format instruction."""
    parts = [base.strip()] if base else []
    if allowed:
        parts.append(f"Allowed decision labels: {', '.join(allowed)}.")
    parts.append(_RESPONSE_FORMAT_INSTRUCTION)
    return "\n\n".join(parts)


def _parse_vote(
    text: str, allowed: Optional[list[str]]
) -> tuple[str, float, str, str]:
    """Try strict JSON first, fall back to label-in-text + default confidence.

    Returns (decision, confidence, reasoning, falsification). The
    falsification slot is empty when the model did not supply one.
    """
    text = (text or "").strip()
    if not text:
        return "", 0.0, "", ""

    # Strip optional code fences
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        obj = json.loads(text)
        decision = str(obj.get("decision", "")).strip()
        confidence = float(obj.get("confidence", 0.5))
        reasoning = str(obj.get("reasoning", ""))[:1000]
        falsification = str(obj.get("falsification", ""))[:1000]
        return decision, max(0.0, min(1.0, confidence)), reasoning, falsification
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    if allowed:
        lowered = text.lower()
        for label in allowed:
            if label.lower() in lowered:
                return label, 0.5, text[:500], ""
    return text[:100], 0.5, text[:500], ""


def _error_vote(model: str, provider: str, start: float, exc: BaseException) -> CouncilVote:
    return CouncilVote(
        model=model,
        provider=provider,
        decision="",
        confidence=0.0,
        reasoning="",
        latency_ms=(time.time() - start) * 1000,
        error=str(exc)[:200],
    )


def _exception_vote(exc: BaseException) -> CouncilVote:
    return CouncilVote(
        model="unknown",
        provider="unknown",
        decision="",
        confidence=0.0,
        reasoning="",
        latency_ms=0.0,
        error=str(exc)[:200],
    )
