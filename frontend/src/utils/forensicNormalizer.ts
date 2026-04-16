import type { AnalysisResult } from "../App";
import type { ForensicTest } from "../api/detector";

export function normalizeForensicTests(
  result: AnalysisResult
): ForensicTest[] {
  // If backend already returns standardized forensic tests, use them
  if (
    result.forensic_tests &&
    Array.isArray(result.forensic_tests) &&
    result.forensic_tests.length > 0
  ) {
    return result.forensic_tests;
  }

  // Otherwise convert legacy indicators into the new forensic format
  if (result.indicators && Array.isArray(result.indicators)) {
    return result.indicators.map((indicator) => ({
      test_name: indicator.label,
      score:
        typeof indicator.value === "number"
          ? Math.max(0, Math.min(1, indicator.value / 100))
          : 0,
      confidence:
        typeof indicator.value === "number"
          ? Math.max(0, Math.min(1, indicator.value / 100))
          : 0,
      verdict:
        indicator.status === "pass"
          ? "clean"
          : indicator.status === "fail"
          ? "suspicious"
          : "inconclusive",
      details: {
        explanation: indicator.explanation ?? "",
      },
    }));
  }

  return [];
}
