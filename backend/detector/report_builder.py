from datetime import datetime
from typing import Any


def generate_official_analysis_report(image_name: str, report: dict[str, Any]) -> str:
    """
    Build a clean human-readable analysis report from the final pipeline result.
    """

    api_result = report.get("api_result", {})
    forensic_summary = report.get("forensic_summary", {})
    final_decision = report.get("final_decision", {})
    suspicious_tests = report.get("suspicious_tests", [])
    forensic_results = report.get("forensic_results", [])

    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []

    lines.append("FAKE PHOTO DETECTOR - ANALYSIS REPORT")
    lines.append("=" * 50)
    lines.append(f"Image Name: {image_name}")
    lines.append(f"Analysis Date: {today}")
    lines.append("")

    lines.append("FINAL RESULT")
    lines.append("-" * 50)
    lines.append(f"Final Verdict: {final_decision.get('final_verdict', 'Unknown')}")
    lines.append(f"Final Score: {final_decision.get('final_score', 'N/A')}")
    lines.append("")

    lines.append("AI MODEL RESULT")
    lines.append("-" * 50)
    lines.append(f"Model Verdict: {api_result.get('verdict', 'Unknown')}")
    lines.append(f"Model Confidence: {api_result.get('confidence', 'N/A')}")
    lines.append(f"Model Name: {api_result.get('model', 'Unknown')}")
    lines.append("")

    lines.append("FORENSIC SUMMARY")
    lines.append("-" * 50)
    lines.append(f"Total Tests: {forensic_summary.get('total_tests', 0)}")
    lines.append(f"Suspicious: {forensic_summary.get('suspicious_count', 0)}")
    lines.append(f"Inconclusive: {forensic_summary.get('inconclusive_count', 0)}")
    lines.append(f"Clean: {forensic_summary.get('clean_count', 0)}")
    lines.append("")

    lines.append("SUSPICIOUS TESTS")
    lines.append("-" * 50)
    if suspicious_tests:
        for test_name in suspicious_tests:
            lines.append(f"- {test_name}")
    else:
        lines.append("None")
    lines.append("")

    lines.append("FORENSIC TEST DETAILS")
    lines.append("-" * 50)

    for test in forensic_results:
        details = test.get("details", {})
        explanation = details.get("explanation", "No explanation available.")

        lines.append(f"Test Name: {test.get('test_name', 'Unknown')}")
        lines.append(f"Verdict: {test.get('verdict', 'Unknown')}")
        lines.append(f"Score: {test.get('score', 'N/A')}")
        lines.append(f"Confidence: {test.get('confidence', 'N/A')}")
        lines.append(f"Explanation: {explanation}")
        lines.append("")

    return "\n".join(lines)
