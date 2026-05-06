"""Risk and root-cause taxonomy loading for Risk Inventory Builder."""

from __future__ import annotations

import re
from typing import Any

from controlnexus.risk_inventory.config import MatrixConfigLoader
from controlnexus.risk_inventory.models import RiskTaxonomyNode, RootCauseTaxonomyEntry


_ROOT_CAUSE_ALIASES: dict[str, str] = {
    "skills & capacity": "Inadequate Workforce Management & Resourcing",
    "awareness & training": "Inadequate Knowledge, Skills, or Training",
    "process design": "Design Failure (Process, Control, or Policy)",
    "process execution": "Implementation or Operating Failure",
    "reconciliation & data quality": "Implementation or Operating Failure",
    "system availability": "Inadequate Maintenance or Capacity",
    "access & entitlements": "Inadequate System Design or Development",
    "technology - excessive privileged access": "Inadequate System Design or Development",
    "third-party performance": "Third-Party Service Failure",
    "adversarial activity": "External Malicious or Criminal Acts",
    "regulatory & legal change": "Regulatory or Legislative Change",
}


_ROOT_CAUSE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Third-Party Service Failure",
        ("third party", "third-party", "vendor", "supplier", "service provider", "outsourced", "sla", "saas"),
    ),
    (
        "Client Conduct or Error",
        ("client error", "customer error", "customer misunderstanding", "duplicate wire", "customer initiates"),
    ),
    (
        "Competitor or Market Behaviour",
        ("competitor", "market dynamics", "industry shift", "deposit rate", "customer attrition"),
    ),
    (
        "External Malicious or Criminal Acts",
        (
            "external fraud",
            "fraud attempt",
            "social engineering",
            "business email compromise",
            "synthetic identity",
            "falsified",
            "robbery",
            "terrorism",
            "criminal",
        ),
    ),
    (
        "Natural Disaster or Environmental Disruption",
        ("natural disaster", "severe weather", "pandemic", "transit", "utility", "power grid", "seismic", "facility disruption"),
    ),
    (
        "Geopolitical, Economic, or Social Instability",
        ("geopolitical", "civil unrest", "economic instability", "social instability", "macro political"),
    ),
    (
        "Regulatory or Legislative Change",
        ("regulatory change", "legal change", "legislative", "supervisory guidance", "new regulation", "law", "cfpb"),
    ),
    (
        "Inadequate Knowledge, Skills, or Training",
        ("training", "knowledge", "skill", "expertise", "technical proficiency", "new hire", "awareness"),
    ),
    (
        "Inadequate Workforce Management & Resourcing",
        ("staffing", "resourcing", "capacity", "surge", "single point", "key-person", "succession", "incentive", "role clarity"),
    ),
    (
        "Cultural or Conduct Weakness",
        ("conduct", "culture", "pressure", "candid escalation", "whistleblowing", "customer interests", "career consequences"),
    ),
    (
        "Internal Malicious Acts",
        ("internal fraud", "collusion", "theft", "sabotage", "wilful", "willful", "override abuse", "deliberate harmful"),
    ),
    (
        "Human Error",
        ("human error", "mistake", "accident", "misinterpretation", "transposes", "manual entry", "approver reliance"),
    ),
    (
        "Missing Control, Process, or Policy",
        ("missing control", "missing process", "missing policy", "absent", "not identified", "ungoverned", "no documented"),
    ),
    (
        "Design Failure (Process, Control, or Policy)",
        (
            "design",
            "wrong granularity",
            "missing review",
            "ambiguous criteria",
            "insufficient coverage",
            "release gate",
            "approval quality",
            "process timing",
            "not required",
            "does not force",
            "unclear release criteria",
        ),
    ),
    (
        "Implementation or Operating Failure",
        (
            "execution",
            "not executed",
            "not operated",
            "not evidenced",
            "evidence gap",
            "not retained",
            "inconsistently followed",
            "lapsed",
            "skipped",
            "recertification",
            "discipline",
            "reviewer notes",
            "not consistently",
        ),
    ),
    (
        "Lack of Clarity or Ownership",
        ("unclear ownership", "ownership", "accountability", "decision rights", "governance forum", "split between", "no documented owner"),
    ),
    (
        "Change & Project Mismanagement",
        ("project", "organizational change", "regulatory implementation", "project delivery", "change communication"),
    ),
    (
        "Inadequate System Design or Development",
        (
            "system design",
            "system dependency",
            "system linkage",
            "screen",
            "surface",
            "interface design",
            "secure-coding",
            "functional requirement",
            "non-functional",
            "entitlement",
            "privilege",
            "access governance",
            "segregation enforcement",
            "routing-default",
        ),
    ),
    (
        "Inadequate Testing",
        ("testing", "regression", "user acceptance", "uat", "volume testing", "edge-case", "security testing"),
    ),
    (
        "Inadequate Change, Release, or Deployment Practices",
        ("change management", "change control", "deployment", "release", "rollback", "configuration change", "misconfigured"),
    ),
    (
        "Inadequate Maintenance or Capacity",
        ("outage", "performance", "interface break", "batch failure", "patching", "end-of-life", "unsupported", "throughput", "bandwidth"),
    ),
    (
        "Inadequate Data Storage, Retention & Destruction",
        ("storage", "backup", "retention", "archival", "destruction", "database corruption", "snapshot"),
    ),
)


_RISK_NODE_ROOT_CAUSES: dict[str, tuple[str, ...]] = {
    "RIB-BPR": (
        "Design Failure (Process, Control, or Policy)",
        "Implementation or Operating Failure",
        "Lack of Clarity or Ownership",
    ),
    "RIB-IFR": (
        "Internal Malicious Acts",
        "Cultural or Conduct Weakness",
        "Implementation or Operating Failure",
    ),
    "RIB-EFR": (
        "External Malicious or Criminal Acts",
        "Client Conduct or Error",
        "Inadequate System Design or Development",
    ),
    "RIB-ORS": (
        "Natural Disaster or Environmental Disruption",
        "Inadequate Maintenance or Capacity",
        "Third-Party Service Failure",
    ),
    "RIB-TPR": (
        "Third-Party Service Failure",
        "Implementation or Operating Failure",
        "Regulatory or Legislative Change",
    ),
    "RIB-DM": (
        "Design Failure (Process, Control, or Policy)",
        "Implementation or Operating Failure",
        "Inadequate Data Storage, Retention & Destruction",
    ),
    "RIB-IT": (
        "Inadequate Maintenance or Capacity",
        "Inadequate Change, Release, or Deployment Practices",
        "Inadequate Testing",
    ),
    "RIB-PCM": (
        "Change & Project Mismanagement",
        "Inadequate Change, Release, or Deployment Practices",
        "Inadequate Testing",
    ),
    "RIB-PRI": (
        "Inadequate Data Storage, Retention & Destruction",
        "Inadequate System Design or Development",
        "Human Error",
    ),
    "RIB-CYB": (
        "Inadequate System Design or Development",
        "Inadequate Change, Release, or Deployment Practices",
        "External Malicious or Criminal Acts",
    ),
    "RIB-HCM": (
        "Inadequate Workforce Management & Resourcing",
        "Inadequate Knowledge, Skills, or Training",
        "Cultural or Conduct Weakness",
    ),
    "RIB-EMP": (
        "Cultural or Conduct Weakness",
        "Inadequate Workforce Management & Resourcing",
        "Human Error",
    ),
    "RIB-RR": (
        "Regulatory or Legislative Change",
        "Missing Control, Process, or Policy",
        "Implementation or Operating Failure",
    ),
    "RIB-COM": (
        "Regulatory or Legislative Change",
        "Missing Control, Process, or Policy",
        "Design Failure (Process, Control, or Policy)",
    ),
}


def load_risk_inventory_taxonomy(config_dir: str | None = None) -> list[RiskTaxonomyNode]:
    """Load inventory-ready taxonomy nodes from the risk inventory crosswalk."""
    loader = MatrixConfigLoader(config_dir)
    payload = loader.taxonomy_crosswalk()
    root_causes = load_root_cause_taxonomy(config_dir)
    nodes = [RiskTaxonomyNode.model_validate(item) for item in payload.get("nodes", [])]
    return [
        node.model_copy(
            update={
                "typical_root_causes": normalize_root_cause_names(
                    node.typical_root_causes,
                    root_causes,
                    node=node,
                    max_items=4,
                )
            }
        )
        for node in nodes
    ]


def load_root_cause_taxonomy(config_dir: str | None = None) -> list[RootCauseTaxonomyEntry]:
    """Load the Basel-aligned root-cause taxonomy from inventory config."""
    payload = MatrixConfigLoader(config_dir).root_cause_taxonomy()
    return root_cause_entries_from_payload(payload)


def root_cause_entries_from_payload(payload: Any) -> list[RootCauseTaxonomyEntry]:
    """Flatten supported root-cause taxonomy YAML shapes into entries."""
    rows = _flatten_root_cause_payload(payload)
    return [RootCauseTaxonomyEntry.model_validate(row) for row in rows]


def root_cause_lookup(
    entries: list[RootCauseTaxonomyEntry] | None = None,
) -> dict[str, RootCauseTaxonomyEntry]:
    """Return a case-insensitive lookup by name and code."""
    entries = entries or load_root_cause_taxonomy()
    lookup: dict[str, RootCauseTaxonomyEntry] = {}
    for entry in entries:
        lookup[_normalize_text(entry.name)] = entry
        lookup[_normalize_text(entry.code)] = entry
    return lookup


def normalize_root_cause_names(
    causes: list[str] | tuple[str, ...] | None,
    entries: list[RootCauseTaxonomyEntry] | None = None,
    *,
    node: RiskTaxonomyNode | None = None,
    max_items: int | None = None,
) -> list[str]:
    """Map free-text or legacy root causes onto the canonical taxonomy names."""
    entries = entries or load_root_cause_taxonomy()
    by_name = root_cause_lookup(entries)
    canonical_names = {entry.name for entry in entries}
    selected: list[str] = []
    for cause in causes or []:
        match = _match_root_cause_name(str(cause), by_name, canonical_names)
        if match and match not in selected:
            selected.append(match)
    for fallback in _fallback_root_causes(node):
        if fallback in canonical_names and fallback not in selected:
            selected.append(fallback)
        if max_items is not None and len(selected) >= max_items:
            break
    if max_items is not None:
        return selected[:max_items]
    return selected


def root_cause_selection_sentence(
    causes: list[str] | tuple[str, ...] | None,
    entries: list[RootCauseTaxonomyEntry] | None = None,
    *,
    max_items: int = 2,
) -> str:
    """Return a risk-statement sentence using definition-derived selection criteria."""
    entries = entries or load_root_cause_taxonomy()
    by_name = root_cause_lookup(entries)
    clauses: list[str] = []
    for cause in normalize_root_cause_names(list(causes or []), entries, max_items=max_items):
        entry = by_name.get(_normalize_text(cause))
        if not entry:
            continue
        criteria = _sentence_fragment(entry.selection_criteria or entry.definition or entry.description)
        if criteria:
            clauses.append(criteria)
    if not clauses:
        return ""
    return f"Root cause selection reflects {_join_phrase(clauses)}."


def risk_statement_with_root_cause_selection(
    description: str,
    causes: list[str] | tuple[str, ...] | None,
    entries: list[RootCauseTaxonomyEntry] | None = None,
) -> str:
    """Append root-cause selection criteria to a risk statement once."""
    clean = description.strip()
    sentence = root_cause_selection_sentence(causes, entries)
    if not sentence or sentence.lower() in clean.lower():
        return clean
    return f"{clean.rstrip()} {sentence}"


def find_applicable_nodes(
    process_text: str,
    nodes: list[RiskTaxonomyNode],
    *,
    include_all_if_none: bool = False,
) -> list[RiskTaxonomyNode]:
    """Select taxonomy nodes by configured process-pattern keywords."""
    text = process_text.lower()
    selected = []
    for node in nodes:
        patterns = [p.lower() for p in node.applicable_process_patterns]
        if any(pattern in text for pattern in patterns):
            selected.append(node)
    if not selected and include_all_if_none:
        return nodes
    return selected


def _flatten_root_cause_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if "source" in payload and len(payload) == 1:
        return _flatten_root_cause_payload(MatrixConfigLoader().root_cause_taxonomy())
    if "root_cause_taxonomy" in payload:
        return _flatten_root_cause_payload(payload["root_cause_taxonomy"])
    if "entries" in payload:
        return _flatten_root_cause_payload(payload["entries"])
    if "causes" in payload and isinstance(payload["causes"], list):
        category = str(payload.get("category", "")).strip()
        cause_origin = str(payload.get("cause_origin", "")).strip()
        return [
            {
                **dict(item),
                "category": item.get("category", category),
                "cause_origin": item.get("cause_origin", cause_origin),
            }
            for item in payload["causes"]
            if isinstance(item, dict)
        ]
    rows: list[dict[str, Any]] = []
    categories = payload.get("categories", [])
    if isinstance(categories, dict):
        categories = [
            {"category": category, **details}
            for category, details in categories.items()
            if isinstance(details, dict)
        ]
    for category_payload in categories if isinstance(categories, list) else []:
        if not isinstance(category_payload, dict):
            continue
        category = str(category_payload.get("category", "")).strip()
        cause_origin = str(category_payload.get("cause_origin", "")).strip()
        for item in category_payload.get("causes", []) or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    **dict(item),
                    "category": item.get("category", category),
                    "cause_origin": item.get("cause_origin", cause_origin),
                }
            )
    return rows


def _match_root_cause_name(
    raw_cause: str,
    by_name: dict[str, RootCauseTaxonomyEntry],
    canonical_names: set[str],
) -> str:
    normalized = _normalize_text(raw_cause)
    if normalized in by_name:
        return by_name[normalized].name
    if normalized in _ROOT_CAUSE_ALIASES:
        return _ROOT_CAUSE_ALIASES[normalized]
    for alias, canonical in _ROOT_CAUSE_ALIASES.items():
        if alias in normalized and canonical in canonical_names:
            return canonical
    for canonical, keywords in _ROOT_CAUSE_KEYWORDS:
        if canonical in canonical_names and any(keyword in normalized for keyword in keywords):
            return canonical
    return ""


def _fallback_root_causes(node: RiskTaxonomyNode | None) -> tuple[str, ...]:
    if node is None:
        return ()
    if node.id in _RISK_NODE_ROOT_CAUSES:
        return _RISK_NODE_ROOT_CAUSES[node.id]
    category = node.level_2_category.lower()
    if "third" in category:
        return _RISK_NODE_ROOT_CAUSES["RIB-TPR"]
    if "cyber" in category or "security" in category:
        return _RISK_NODE_ROOT_CAUSES["RIB-CYB"]
    if "data" in category:
        return _RISK_NODE_ROOT_CAUSES["RIB-DM"]
    if "technology" in category or "information technology" in category:
        return _RISK_NODE_ROOT_CAUSES["RIB-IT"]
    if "regulatory" in category or "compliance" in category:
        return _RISK_NODE_ROOT_CAUSES["RIB-COM"]
    if "human" in category or "employment" in category:
        return _RISK_NODE_ROOT_CAUSES["RIB-HCM"]
    return _RISK_NODE_ROOT_CAUSES["RIB-BPR"]


def _sentence_fragment(text: str) -> str:
    clean = text.strip().rstrip(".")
    clean = re.sub(r"^select when\s+", "", clean, flags=re.IGNORECASE)
    if not clean:
        return ""
    return clean[0].lower() + clean[1:]


def _normalize_text(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9&/ -]+", " ", value.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _join_phrase(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"
