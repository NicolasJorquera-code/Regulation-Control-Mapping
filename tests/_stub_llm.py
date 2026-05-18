"""
StubLLMClient -- duck-typed stand-in for AsyncTransportClient used in tests.

Routes each agent's call to a canned-response generator (based on the unique
opening line of each agent's system prompt) and returns an OpenAI-style
chat-completion response. Lets the test suite exercise the real LLM code
path (prompt building -> chat_completion -> JSON parse -> validation ->
AI governance review) without any API keys.

Not for production use. Production requires real LLM credentials -- see
README.md and .env.example.
"""

from __future__ import annotations

import json
import re
from typing import Any


# Unique signature substrings that identify each agent from its system prompt.
_AGENT_SIGNATURES: dict[str, str] = {
    "classifier":      "regulatory compliance analyst specializing in regulatory change management",
    "mapper":          "mapping regulatory obligations to business processes using the APQC",
    "coverage":        "evaluating whether existing internal controls adequately cover",
    "risk_scorer":     "senior risk analyst at a large financial institution",
    "control_advisor": "controls advisory specialist for a large financial institution",
}


# Same keyword routing the production APQC mapper used to use for its
# deterministic fallback, kept here so test responses look realistic.
_KEYWORD_APQC_MAP: dict[str, tuple[str, str]] = {
    "liquidity":      ("9.7.1", "Manage treasury operations"),
    "capital":        ("9.5.1", "Manage capital structure"),
    "stress test":    ("9.7.1", "Manage treasury operations"),
    "risk committee": ("11.1.1", "Establish enterprise risk framework"),
    "risk management":("11.1.1", "Establish enterprise risk framework"),
    "credit":         ("9.6.1", "Manage credit"),
    "counterparty":   ("9.6.1", "Manage credit"),
    "compliance":     ("11.2.1", "Manage regulatory compliance"),
    "audit":          ("11.3.1", "Manage internal audit"),
    "report":         ("11.2.1", "Manage regulatory compliance"),
    "governance":     ("11.1.1", "Establish enterprise risk framework"),
    "board":          ("11.1.1", "Establish enterprise risk framework"),
    "foreign":        ("11.2.1", "Manage regulatory compliance"),
    "debt":           ("9.5.1", "Manage capital structure"),
    "resolution":     ("11.1.1", "Establish enterprise risk framework"),
    "contingency":    ("9.7.1", "Manage treasury operations"),
}


def _classify_one(citation: str, hint_text: str) -> dict[str, Any]:
    combined = hint_text.lower()
    if any(kw in combined for kw in ("definition", "authority", "purpose", "scope")):
        cat, rel, crit = "General Awareness", "N/A", "Low"
        rationale = "Definitional / authority language."
    elif any(kw in combined for kw in ("approve", "attest", "certif", "board")):
        cat, rel, crit = "Attestation", "Requires Existence", "High"
        rationale = "Attestation / board approval language."
    elif any(kw in combined for kw in ("report", "submit", "disclose", "document", "record")):
        cat, rel, crit = "Documentation", "Requires Evidence", "Medium"
        rationale = "Documentation or reporting language."
    elif any(kw in combined for kw in ("must", "shall", "require", "ensure", "maintain")):
        cat, rel, crit = "Controls", "Constrains Execution", "High"
        rationale = "Mandatory control language."
    else:
        cat, rel, crit = "Not Assigned", "N/A", "Low"
        rationale = "No clear actionable requirement identified."
    return {
        "citation": citation,
        "obligation_category": cat,
        "relationship_type": rel,
        "criticality_tier": crit,
        "classification_rationale": rationale,
    }


def _classifier_response(user_prompt: str) -> dict[str, Any]:
    classifications: list[dict[str, Any]] = []
    # User prompt lists "  - {citation}: {tl3} | {tl4} | {tl5}\n    {abstract}"
    for m in re.finditer(r"  - ([^:\n]+):([^\n]*)\n    ([^\n]*)", user_prompt):
        citation = m.group(1).strip()
        hint = m.group(2) + " " + m.group(3)
        classifications.append(_classify_one(citation, hint))
    return {"classifications": classifications}


def _mapper_response(user_prompt: str) -> dict[str, Any]:
    mappings: list[dict[str, Any]] = []
    # User prompt lists "  - {citation} [{cat}, {rel}, {crit}]:\n    {abstract}"
    for m in re.finditer(r"  - (.+?)\s*\[([^,]+),\s*([^,]+),\s*([^\]]+)\]:\n    ([^\n]*)", user_prompt):
        citation, _cat, rel, _crit, abstract = (g.strip() for g in m.groups())
        combined = abstract.lower()
        matched: tuple[str, str] | None = None
        keyword_seen = ""
        for kw, target in _KEYWORD_APQC_MAP.items():
            if kw in combined:
                matched = target
                keyword_seen = kw
                break
        if matched is None:
            matched = ("11.1.1", "Establish enterprise risk framework")
            detail = "Default mapping -- no specific keyword match."
            confidence = 0.4
        else:
            detail = f"Stub mapping based on keyword '{keyword_seen}'."
            confidence = 0.7
        apqc_id, apqc_name = matched
        mappings.append({
            "citation": citation,
            "apqc_hierarchy_id": apqc_id,
            "apqc_process_name": apqc_name,
            "relationship_type": rel or "Constrains Execution",
            "relationship_detail": detail,
            "confidence": confidence,
        })
    return {"mappings": mappings}


def _coverage_response(user_prompt: str) -> dict[str, Any]:
    # Stub: stable Partially Covered verdict for every structurally matched call.
    return {
        "semantic_match": "Partial",
        "semantic_rationale": "Stub semantic match -- partial structural overlap detected.",
        "relationship_match": "Partial",
        "relationship_rationale": "Stub relationship match -- partial alignment detected.",
        "overall_coverage": "Partially Covered",
    }


def _risk_response(user_prompt: str) -> dict[str, Any]:
    # Stub: one realistic-shaped risk per call, scoring based on criticality
    # mentioned in the prompt.
    m = re.search(r"CRITICALITY:\s*([A-Za-z]+)", user_prompt)
    criticality = (m.group(1) if m else "Medium").capitalize()
    impact, freq = {"High": (3, 2), "Medium": (2, 2)}.get(criticality, (1, 1))
    cit_m = re.search(r"OBLIGATION:\s*([^\n]+)", user_prompt)
    citation = cit_m.group(1).strip() if cit_m else "UNKNOWN"
    return {
        "risks": [{
            "risk_description": f"Stub risk for {citation}: non-compliance with the obligation could trigger supervisory action.",
            "risk_category": "Compliance Risk",
            "sub_risk_category": "Regulatory Compliance Risk",
            "impact_rating": impact,
            "impact_rationale": f"Stub impact rationale based on {criticality} criticality.",
            "frequency_rating": freq,
            "frequency_rationale": f"Stub frequency rationale based on {criticality} criticality.",
        }],
    }


def _control_response(user_prompt: str) -> dict[str, Any]:
    ctrl_m = re.search(r'Use control_id:\s*"([^"]+)"', user_prompt)
    hier_m = re.search(r'Use hierarchy_id:\s*"([^"]+)"', user_prompt)
    cit_m = re.search(r"OBLIGATION:\s*([^\n]+)", user_prompt)
    return {
        "proposed_control": {
            "control_id":         (ctrl_m.group(1) if ctrl_m else "PROP-STUB-001"),
            "hierarchy_id":       (hier_m.group(1) if hier_m else "11.1.1"),
            "leaf_name":          f"Stub control for {cit_m.group(1).strip() if cit_m else 'obligation'}",
            "full_description":   "Stub-generated control description for test purposes.",
            "selected_level_1":   "Preventive",
            "selected_level_2":   "Policy Control",
            "who":                "Stub Owner",
            "what":               "Stub control activity.",
            "when":               "Quarterly",
            "frequency":          "Quarterly",
            "where":              "Enterprise-wide",
            "why":                "Stub rationale.",
            "evidence":           "Stub evidence artifact.",
            "quality_rating":     "Effective",
            "business_unit_name": "Stub BU",
        },
        "improvement_rationale": "Stub improvement rationale.",
        "change_type":           "new",
        "gap_addressed":         "Stub gap summary.",
    }


_AGENT_DISPATCH = {
    "classifier":      _classifier_response,
    "mapper":          _mapper_response,
    "coverage":        _coverage_response,
    "risk_scorer":     _risk_response,
    "control_advisor": _control_response,
}


def _identify_agent(system_prompt: str) -> str | None:
    for agent_key, signature in _AGENT_SIGNATURES.items():
        if signature in system_prompt:
            return agent_key
    return None


class StubLLMClient:
    """Duck-typed AsyncTransportClient replacement for tests."""

    # Attributes BaseAgent / GraphInfra read on the client.
    model: str = "stub-llm"
    provider: str = "stub"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict | None = None,
    ) -> dict[str, Any]:
        system_prompt = next((m["content"] for m in messages if m.get("role") == "system"), "")
        user_prompt   = next((m["content"] for m in messages if m.get("role") == "user"),   "")
        agent_key = _identify_agent(system_prompt)
        self.calls.append({"agent": agent_key, "system": system_prompt[:120], "user": user_prompt[:200]})

        if agent_key is None:
            content_json: dict[str, Any] = {}
        else:
            content_json = _AGENT_DISPATCH[agent_key](user_prompt)

        return {
            "choices": [{
                "message": {"role": "assistant", "content": json.dumps(content_json)},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            "model": self.model,
        }
