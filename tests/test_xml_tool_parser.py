"""Tests for the XML tool-call parser."""

from __future__ import annotations

from controlnexus.tools.xml_tool_parser import (
    format_tool_results,
    parse_xml_tool_calls,
    strip_tool_calls,
)


# ── parse_xml_tool_calls ──────────────────────────────────────────────────────


class TestParseXmlToolCalls:
    def test_single_tool_call(self):
        text = (
            "I need to look up placements.\n"
            "<tool_call>\n"
            "<name>placement_lookup</name>\n"
            '<arguments>{"control_type": "Reconciliation"}</arguments>\n'
            "</tool_call>\n"
        )
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        assert result[0]["name"] == "placement_lookup"
        assert result[0]["arguments"] == {"control_type": "Reconciliation"}

    def test_multiple_tool_calls(self):
        text = (
            "<tool_call>\n"
            "<name>placement_lookup</name>\n"
            '<arguments>{"control_type": "Authorization"}</arguments>\n'
            "</tool_call>\n"
            "Now checking methods.\n"
            "<tool_call>\n"
            "<name>method_lookup</name>\n"
            "<arguments>{}</arguments>\n"
            "</tool_call>\n"
        )
        result = parse_xml_tool_calls(text)
        assert len(result) == 2
        assert result[0]["name"] == "placement_lookup"
        assert result[1]["name"] == "method_lookup"
        assert result[1]["arguments"] == {}

    def test_no_tool_calls(self):
        text = '{"control_type": "Reconciliation", "placement": "Detective"}'
        result = parse_xml_tool_calls(text)
        assert result == []

    def test_malformed_json_arguments_skipped(self):
        text = (
            "<tool_call>\n"
            "<name>placement_lookup</name>\n"
            "<arguments>not valid json</arguments>\n"
            "</tool_call>\n"
        )
        result = parse_xml_tool_calls(text)
        assert result == []

    def test_empty_arguments(self):
        text = (
            "<tool_call>\n"
            "<name>method_lookup</name>\n"
            "<arguments></arguments>\n"
            "</tool_call>\n"
        )
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        assert result[0]["arguments"] == {}

    def test_nested_json_in_arguments(self):
        text = (
            "<tool_call>\n"
            "<name>taxonomy_validator</name>\n"
            '<arguments>{"level_1": "Preventive", "level_2": "Authorization"}</arguments>\n'
            "</tool_call>\n"
        )
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        assert result[0]["arguments"]["level_1"] == "Preventive"
        assert result[0]["arguments"]["level_2"] == "Authorization"

    def test_whitespace_tolerance(self):
        text = (
            "<tool_call>  \n"
            "  <name>  placement_lookup  </name>  \n"
            '  <arguments>  {"control_type": "Rec"}  </arguments>  \n'
            "</tool_call>"
        )
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        assert result[0]["name"] == "placement_lookup"
        assert result[0]["arguments"] == {"control_type": "Rec"}

    def test_tool_call_with_surrounding_text(self):
        text = (
            "Let me check the placement categories for this control type.\n\n"
            "<tool_call>\n"
            "<name>placement_lookup</name>\n"
            '<arguments>{"control_type": "Reconciliation"}</arguments>\n'
            "</tool_call>\n\n"
            "I'll also check evidence rules.\n\n"
            "<tool_call>\n"
            "<name>evidence_rules_lookup</name>\n"
            '<arguments>{"control_type": "Reconciliation"}</arguments>\n'
            "</tool_call>\n"
        )
        result = parse_xml_tool_calls(text)
        assert len(result) == 2


# ── format_tool_results ──────────────────────────────────────────────────────


class TestFormatToolResults:
    def test_single_result(self):
        results = [{"name": "placement_lookup", "output": {"placements": ["Detective"]}}]
        formatted = format_tool_results(results)
        assert '<tool_result name="placement_lookup">' in formatted
        assert '"placements"' in formatted
        assert "</tool_result>" in formatted

    def test_multiple_results(self):
        results = [
            {"name": "placement_lookup", "output": {"placements": ["Detective"]}},
            {"name": "method_lookup", "output": {"methods": ["Automated", "Manual"]}},
        ]
        formatted = format_tool_results(results)
        assert formatted.count("<tool_result") == 2
        assert formatted.count("</tool_result>") == 2

    def test_empty_results_list(self):
        assert format_tool_results([]) == ""


# ── strip_tool_calls ─────────────────────────────────────────────────────────


class TestStripToolCalls:
    def test_removes_tool_call_blocks(self):
        text = (
            "Here is my analysis.\n"
            "<tool_call>\n"
            "<name>placement_lookup</name>\n"
            '<arguments>{"control_type": "Rec"}</arguments>\n'
            "</tool_call>\n"
            '{"control_type": "Reconciliation"}'
        )
        cleaned = strip_tool_calls(text)
        assert "<tool_call>" not in cleaned
        assert '{"control_type": "Reconciliation"}' in cleaned

    def test_no_tool_calls_returns_original(self):
        text = '{"control_type": "Reconciliation"}'
        assert strip_tool_calls(text) == text

    def test_multiple_blocks_stripped(self):
        text = (
            "<tool_call><name>a</name><arguments>{}</arguments></tool_call>"
            " middle "
            "<tool_call><name>b</name><arguments>{}</arguments></tool_call>"
            " end"
        )
        cleaned = strip_tool_calls(text)
        assert "<tool_call>" not in cleaned
        assert "middle" in cleaned
        assert "end" in cleaned
