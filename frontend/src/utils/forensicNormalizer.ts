import type { AnalysisResult } from "../App";
import type { ForensicTest } from "../api/detector";

export function normalizeForensicTests(
  result: AnalysisResult
): ForensicTest[] {
  const tests = Array.isArray(result.forensic_tests)
    ? [...result.forensic_tests]
    : [];

  const hasElaTest = tests.some((test) => {
    const name = test.test_name.toLowerCase();
    return name.includes("error level") || name.includes("ela");
  });

  if (result.ela && !hasElaTest) {
    const score = Math.max(0, Math.min(1, result.ela.score / 100));
    const verdict: ForensicTest["verdict"] =
      result.ela.score >= 55
        ? "suspicious"
        : result.ela.score >= 30
          ? "inconclusive"
          : "clean";

    tests.unshift({
      test_name: "Error Level Analysis",
      score,
      confidence: Math.max(0, Math.min(0.94, 0.54 + score * 0.4)),
      verdict,
      details: {
        ela_score: result.ela.score,
        explanation: result.ela.explanation,
        metrics: result.ela.metrics,
        artifact_map: {
          url: result.ela.heatmap.url,
          mediaType: "image/png",
        },
      },
    });
  }

  return tests;
}
