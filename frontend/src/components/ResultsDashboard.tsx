import { AnalysisResult } from "../App";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { Progress } from "./ui/progress";
import { Calendar, Flame } from "lucide-react";
import ForensicTestCard from "./ForensicTestCard";
import { normalizeForensicTests } from "../utils/forensicNormalizer";

interface ResultsDashboardProps {
  results: AnalysisResult[];
  selectedResult: AnalysisResult;
  onSelectResult: (result: AnalysisResult) => void;
}

export function ResultsDashboard({
  selectedResult,
}: ResultsDashboardProps) {
  const apiBaseUrl =
    (
      import.meta as ImportMeta & {
        env?: { VITE_API_BASE_URL?: string };
      }
    ).env?.VITE_API_BASE_URL?.trim() ?? "";
  const rawHeatmapUrl = selectedResult?.ela?.heatmap?.url;

  const heatmapUrl =
    rawHeatmapUrl?.startsWith("data:")
      ? rawHeatmapUrl
      : apiBaseUrl && rawHeatmapUrl
        ? new URL(rawHeatmapUrl, apiBaseUrl).toString()
        : null;

  const forensicTests = normalizeForensicTests(selectedResult);

  const formatPercentMetric = (value?: number) =>
    typeof value === "number" ? `${value.toFixed(2)}%` : "N/A";

  const formatRatioMetric = (value?: number) => {
    if (typeof value !== "number") return "N/A";
    const asPercent = value <= 1 ? value * 100 : value;
    return `${asPercent.toFixed(2)}%`;
  };

  return (
    <div className="space-y-6">
      {/* TOP IMAGE + INFO */}
      <Card className="p-6 shadow-md bg-white/70 border-[#8d70b3]/30">
        <div className="flex flex-col md:flex-row gap-6">
          <div className="md:w-1/2">
            <img
              src={selectedResult.imageUrl}
              alt={selectedResult.fileName}
              className="w-full h-64 object-cover rounded-lg border"
            />
          </div>

          <div className="md:w-1/2 space-y-4">
            <div>
              <h3>{selectedResult.fileName}</h3>
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <Calendar className="w-4 h-4" />
                {selectedResult.uploadDate.toLocaleString()}
              </div>
            </div>

            <div>
              <div className="flex justify-between text-sm">
                <span>Detection Result</span>
                <Badge
                  variant={
                    selectedResult.isAIGenerated
                      ? "destructive"
                      : "default"
                  }
                >
                  {selectedResult.isAIGenerated
                    ? "AI Generated"
                    : "Real Photo"}
                </Badge>
              </div>

              <div className="mt-2">
                <div className="flex justify-between text-sm">
                  <span>Confidence</span>
                  <span>
                    {selectedResult.confidence.toFixed(1)}%
                  </span>
                </div>
                <Progress value={selectedResult.confidence} />
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* FORENSIC TESTS (NEW SYSTEM) */}
      <Card className="p-6 shadow-md bg-white/70 border-[#8d70b3]/30">
        <h3 className="mb-4 font-semibold text-gray-900">
          Forensic Test Results
        </h3>

        {forensicTests.length === 0 ? (
          <p>No forensic test results available.</p>
        ) : (
          <div
            className="grid gap-4"
            style={{
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gridAutoRows: "1fr",
            }}
          >
            {forensicTests.map((test, index) => (
              <ForensicTestCard
                key={`${selectedResult.id}-${test.test_name}-${index}`}
                test={test}
              />
            ))}
          </div>
        )}
      </Card>

      {/* ELA */}
      {selectedResult.ela && (
        <Card className="p-6 shadow-md bg-white/70 border-[#8d70b3]/30">
          <div className="flex items-center gap-2 mb-4">
            <Flame className="w-5 h-5" />
            <h3>ELA Heatmap</h3>
          </div>

          <div className="flex flex-col md:flex-row gap-6">
            <div className="md:w-1/2">
              {heatmapUrl ? (
                <img
                  src={heatmapUrl}
                  alt="ELA heatmap"
                  className="w-full rounded-lg border object-contain bg-black"
                />
              ) : (
                <div className="h-48 flex items-center justify-center text-gray-400">
                  Heatmap not available
                </div>
              )}
            </div>

            <div className="md:w-1/2 space-y-4">
              <div>
                <div className="flex justify-between text-sm">
                  <span>ELA Score</span>
                  <span>
                    {selectedResult.ela.score.toFixed(1)}%
                  </span>
                </div>
                <Progress value={selectedResult.ela.score} />
              </div>

              <p className="text-sm">
                {selectedResult.ela.explanation}
              </p>

              {selectedResult.ela.metrics && (
                <div className="text-sm space-y-1">
                  <div>
                    Mean Intensity:{" "}
                    {formatPercentMetric(
                      selectedResult.ela.metrics.mean_intensity
                    )}
                  </div>
                  <div>
                    Hotspot Ratio:{" "}
                    {formatRatioMetric(
                      selectedResult.ela.metrics.hotspot_ratio
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* SUMMARY */}
      <Card className="p-6 bg-purple-100">
        <h3>Analysis Summary</h3>
        <p>
          This image has been analyzed using multiple detection
          indicators. The overall confidence score of{" "}
          {selectedResult.confidence.toFixed(1)}% suggests that it is{" "}
          {selectedResult.isAIGenerated
            ? "likely AI-generated"
            : "likely real"}.
        </p>
      </Card>
    </div>
  );
}
