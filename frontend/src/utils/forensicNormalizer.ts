import type { AnalysisResult } from "../App";
import type { ForensicTest } from "../api/detector";

export function normalizeForensicTests(
  result: AnalysisResult
): ForensicTest[] {
  const standardizedTests = Array.isArray(result.forensic_tests)
    ? result.forensic_tests
    : [];

  const indicatorTests = Array.isArray(result.indicators)
    ? result.indicators.map((indicator) => ({
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
    }))
    : [];

  if (standardizedTests.length === 0) {
    return indicatorTests;
  }

  const existingNames = new Set(
    standardizedTests.map((test) => test.test_name.toLowerCase())
  );

  return [
    ...standardizedTests,
    ...indicatorTests.filter(
      (test) => !existingNames.has(test.test_name.toLowerCase())
    ),
  ];
}
