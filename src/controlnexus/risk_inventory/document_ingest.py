"""Document ingestion helpers for Risk Inventory Builder.

The frontend uses these deterministic helpers to turn policy/procedure
documents into a usable process context before the graph runs.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class DocumentAnalysis(BaseModel):
    """Deterministic extraction result from an uploaded policy/procedure."""

    filename: str
    text: str
    process_id: str
    process_name: str
    product: str = ""
    business_unit: str = ""
    description: str = ""
    systems: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    detected_risk_categories: list[str] = Field(default_factory=list)
    detected_controls: list[str] = Field(default_factory=list)
    exposure_cues: list[str] = Field(default_factory=list)
    obligations: list[str] = Field(default_factory=list)
    document_stats: dict[str, int] = Field(default_factory=dict)

    def process_context(self) -> dict[str, Any]:
        """Return a graph-ready process context dictionary."""
        return {
            "process_id": self.process_id,
            "process_name": self.process_name,
            "product": self.product,
            "business_unit": self.business_unit,
            "description": self.description,
            "systems": self.systems,
            "stakeholders": self.stakeholders,
            "source_documents": [self.filename],
        }


def extract_text_from_document(filename: str, content: bytes) -> str:
    """Extract text from a supported uploaded document."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(content)
    if suffix in {".txt", ".md", ".markdown"}:
        return content.decode("utf-8", errors="replace")
    raise ValueError("Supported process documents are PDF, TXT, and Markdown files.")


def analyze_process_document(filename: str, content: bytes) -> DocumentAnalysis:
    """Extract process context and analysis cues from a policy/procedure document."""
    text = _normalize_text(extract_text_from_document(filename, content))
    lower = text.lower()

    process_name = _extract_labeled_value(text, ("process", "procedure", "process name")) or _infer_process_name(lower)
    product = _extract_labeled_value(text, ("product", "service", "product/service")) or _infer_product(lower)
    business_unit = _extract_labeled_value(text, ("business unit", "owner", "department")) or _infer_business_unit(lower)
    systems = _extract_list_value(text, ("systems", "applications", "platforms")) or _infer_systems(text)
    stakeholders = _extract_list_value(text, ("stakeholders", "roles", "process owners")) or _infer_stakeholders(text)
    detected_controls = _find_phrases(
        text,
        [
            "daily exception queue review",
            "dual approval",
            "reconciliation",
            "entitlement review",
            "sla breach monitoring",
            "incident escalation",
            "business continuity testing",
            "management review",
            "quality assurance review",
            "maker-checker",
        ],
    )
    detected_risks = _infer_risk_categories(lower)
    exposure_cues = _find_exposure_cues(text)
    obligations = _find_obligations(text)
    description = _build_description(text, process_name, detected_controls, exposure_cues, obligations)

    return DocumentAnalysis(
        filename=filename,
        text=text,
        process_id=_slug(process_name),
        process_name=process_name,
        product=product,
        business_unit=business_unit,
        description=description,
        systems=systems,
        stakeholders=stakeholders,
        detected_risk_categories=detected_risks,
        detected_controls=detected_controls,
        exposure_cues=exposure_cues,
        obligations=obligations,
        document_stats={
            "characters": len(text),
            "words": len(text.split()),
            "sentences": len(re.findall(r"[.!?]", text)),
        },
    )


def _extract_pdf_text(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(page.strip() for page in pages if page.strip())


def _normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        pattern = rf"(?im)^\s*{re.escape(label)}\s*[:\-]\s*(.+?)\s*$"
        match = re.search(pattern, text)
        if match:
            return _clean_label_value(match.group(1))
    return ""


def _extract_list_value(text: str, labels: tuple[str, ...]) -> list[str]:
    value = _extract_labeled_value(text, labels)
    if not value:
        return []
    parts = re.split(r"[,;|]|\s+-\s+", value)
    return [_clean_label_value(part) for part in parts if _clean_label_value(part)]


def _infer_process_name(lower_text: str) -> str:
    if "payment exception" in lower_text:
        return "Payment Exception Handling"
    if "customer onboarding" in lower_text or "know your customer" in lower_text:
        return "Customer Onboarding"
    if "vendor onboarding" in lower_text or "third-party onboarding" in lower_text:
        return "Vendor Onboarding"
    if "wire transfer" in lower_text:
        return "Wire Transfer Operations"
    if "complaint" in lower_text:
        return "Complaint Intake"
    if "access provisioning" in lower_text:
        return "Access Provisioning"
    if "regulatory reporting" in lower_text:
        return "Regulatory Reporting"
    return "Uploaded Policy / Procedure Review"


def _infer_product(lower_text: str) -> str:
    if "high-value" in lower_text and "payment" in lower_text:
        return "High-value payment processing"
    if "wire" in lower_text:
        return "Wire transfer operations"
    if "customer" in lower_text and "onboarding" in lower_text:
        return "Customer onboarding"
    if "vendor" in lower_text or "third-party" in lower_text:
        return "Third-party services"
    return "Business process"


def _infer_business_unit(lower_text: str) -> str:
    if "payment" in lower_text or "wire" in lower_text:
        return "Payment Operations"
    if "compliance" in lower_text or "regulatory" in lower_text:
        return "Compliance"
    if "technology" in lower_text or "system" in lower_text:
        return "Technology Operations"
    return "Business Operations"


def _infer_systems(text: str) -> list[str]:
    candidates = [
        "Payment Exception Workflow",
        "Wire Transfer Platform",
        "Case Management System",
        "General Ledger",
        "Identity and Access Management",
        "Regulatory Reporting Portal",
        "Vendor Management Platform",
    ]
    lower = text.lower()
    found = [candidate for candidate in candidates if candidate.lower() in lower]
    if not found and ("queue" in lower or "workflow" in lower):
        found.append("Workflow / Queue Management System")
    return found


def _infer_stakeholders(text: str) -> list[str]:
    candidates = [
        "Payment Operations Manager",
        "Exception Analyst",
        "Compliance Officer",
        "Technology Owner",
        "Risk Manager",
        "Business Continuity Lead",
        "Vendor Manager",
    ]
    lower = text.lower()
    found = [candidate for candidate in candidates if candidate.lower() in lower]
    return found or ["Process Owner", "Control Owner", "Risk Reviewer"]


def _infer_risk_categories(lower_text: str) -> list[str]:
    rules = {
        "Business Process Risk": ("exception", "manual", "queue", "timely", "procedure", "approval"),
        "Data Management Risk": ("data", "reconciliation", "record", "report", "accuracy"),
        "IT Security / Cybersecurity Risk": ("access", "entitlement", "privileged", "unauthorized"),
        "Regulatory Reporting Risk": ("regulatory", "reportable", "incident", "filing", "notification"),
        "Operational Resiliency Risk": ("continuity", "outage", "recover", "disruption", "backup"),
        "Third Party Risk": ("vendor", "third party", "service provider", "outsourcer"),
        "Compliance Risk": ("policy", "compliance", "requirement", "standard"),
        "External Fraud Risk": ("fraud", "counterparty", "unauthorized payment"),
    }
    found = [category for category, tokens in rules.items() if any(token in lower_text for token in tokens)]
    return found or ["Business Process Risk", "Compliance Risk"]


def _find_phrases(text: str, phrases: list[str]) -> list[str]:
    lower = text.lower()
    return [phrase.title() for phrase in phrases if phrase in lower]


def _find_exposure_cues(text: str) -> list[str]:
    cues: list[str] = []
    patterns = [
        r"\b\d+%\s+(?:of\s+)?(?:items|exceptions|payments|cases)",
        r"\b\d+\s+(?:exceptions|payments|cases|items|breaches)\s+(?:per|each)\s+(?:day|week|month)",
        r"\$[0-9][0-9,.]*(?:m|mm| million| billion)?",
        r"\b(?:daily|weekly|monthly|quarterly)\b",
        r"\b(?:same-day|next-day|within\s+\d+\s+hours?)\b",
    ]
    for pattern in patterns:
        cues.extend(match.group(0) for match in re.finditer(pattern, text, flags=re.IGNORECASE))
    return list(dict.fromkeys(cues))[:12]


def _find_obligations(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    markers = ("must", "shall", "required", "requires", "escalate", "approve", "review", "report")
    obligations = [sentence.strip() for sentence in sentences if any(marker in sentence.lower() for marker in markers)]
    return obligations[:8]


def _build_description(
    text: str,
    process_name: str,
    controls: list[str],
    exposure_cues: list[str],
    obligations: list[str],
) -> str:
    first_sentences = re.split(r"(?<=[.!?])\s+", text)[:3]
    summary = " ".join(sentence.strip() for sentence in first_sentences if sentence.strip())
    parts = [summary or f"Uploaded policy/procedure for {process_name}."]
    if controls:
        parts.append(f"Detected control activities include {', '.join(controls[:5])}.")
    if exposure_cues:
        parts.append(f"Detected exposure cues include {', '.join(exposure_cues[:5])}.")
    if obligations:
        parts.append("The document contains explicit review, approval, escalation, or reporting obligations.")
    return " ".join(parts)[:2500]


def _clean_label_value(value: str) -> str:
    return value.strip().strip("-*•").strip()


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").upper()
    return f"PROC-{slug or 'UPLOADED-DOCUMENT'}"
