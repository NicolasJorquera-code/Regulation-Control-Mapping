"""Quick smoke test for the redesigned card header."""
from regrisk.ui.results_tab import _card_header_html, _highest_severity_color
from regrisk.ui.components import render_risk_chip, CATEGORY_BG

print("All imports OK")

ob = {
    "citation": "12 CFR 252.14(a)(1)",
    "criticality_tier": "High",
    "overall_coverage": "Not Covered",
    "obligation_category": "Controls",
    "relationship_type": "Sets Frequency",
    "abstract": "The board of directors must annually approve a written liquidity policy.",
    "title_level_2": "Subpart D",
    "title_level_3": "Stress Testing Requirements",
}
risks = [
    {"inherent_risk_rating": "Critical", "impact_rating": 4, "frequency_rating": 3},
    {"inherent_risk_rating": "High", "impact_rating": 3, "frequency_rating": 3},
]

html = _card_header_html(ob, 2, risks)
assert "crit-pill-high" in html, "Missing criticality pill"
assert "cov-pill-gap" in html, "Missing coverage pill"
assert "category-pill" in html, "Missing category pill"
assert "2 risks" in html, "Missing risk count"
assert "Subpart D" in html, "Missing breadcrumb"
assert "Stress Testing" in html, "Missing breadcrumb part 2"
assert "liquidity policy" in html, "Missing preview text"
assert "ob-card-header" in html, "Missing header class"
assert "ob-card-meta" in html, "Missing meta class"
assert "ob-card-preview" in html, "Missing preview class"

bg, fg = _highest_severity_color(risks)
assert bg == "#c62828", f"Expected critical red, got {bg}"

# Edge case: no risks
html_no_risk = _card_header_html(ob, 0, [])
assert "risk" not in html_no_risk.lower() or "risk" not in html_no_risk

# Edge case: Low criticality, Covered
ob2 = dict(ob, criticality_tier="Low", overall_coverage="Covered")
html2 = _card_header_html(ob2, 0, [])
assert "crit-pill-low" in html2
assert "cov-pill-covered" in html2

print("All assertions passed!")
print("Sample HTML output:")
print(html)
