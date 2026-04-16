import { AnalysisResult } from "../App";
import type { ReactNode } from "react";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { Progress } from "./ui/progress";
import { Calendar, CheckCircle, Flame, Gauge, Image as ImageIcon, Layers } from "lucide-react";
import ForensicTestCard from "./ForensicTestCard";
import { normalizeForensicTests } from "../utils/forensicNormalizer";

interface ResultsDashboardProps {
  results: AnalysisResult[];
  selectedResult: AnalysisResult;
  onSelectResult: (result: AnalysisResult) => void;
}

const panelStyle = {
  borderRadius: "8px",
  border: "1px solid rgba(141, 112, 179, 0.3)",
  background: "rgba(255, 255, 255, 0.78)",
  boxShadow: "0 14px 34px rgba(61, 48, 77, 0.16)",
};

const mutedPanelStyle = {
  borderRadius: "8px",
  border: "1px solid rgba(141, 112, 179, 0.24)",
  background: "rgba(245, 240, 255, 0.58)",
};

function formatPercentMetric(value?: number) {
  return typeof value === "number" ? `${value.toFixed(2)}%` : "N/A";
}

function formatRatioMetric(value?: number) {
  if (typeof value !== "number") return "N/A";
  const asPercent = value <= 1 ? value * 100 : value;
  return `${asPercent.toFixed(2)}%`;
}

function formatFileSize(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function MediaFrame({
  children,
  maxWidth = "620px",
}: {
  children: ReactNode;
  maxWidth?: string;
}) {
  return (
    <div
      className="border"
      style={{
        width: `min(100%, ${maxWidth})`,
        aspectRatio: "4 / 3",
        borderRadius: "8px",
        backgroundColor: "transparent",
        borderColor: "rgba(141, 112, 179, 0.18)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        overflow: "hidden",
      }}
    >
      {children}
    </div>
  );
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
  const detectionLabel = selectedResult.isAIGenerated
    ? "AI Generated"
    : "Real Photo";
  const elaScore = selectedResult.ela?.score;
  const statCards = [
    {
      label: "Detection",
      value: detectionLabel,
      detail: `${selectedResult.confidence.toFixed(1)}% confidence`,
      icon: CheckCircle,
    },
    {
      label: "Confidence",
      value: `${selectedResult.confidence.toFixed(1)}%`,
      detail: "overall model score",
      icon: Gauge,
    },
    {
      label: "Forensic Tests",
      value: String(forensicTests.length),
      detail: "signals reviewed",
      icon: Layers,
    },
    {
      label: "File Size",
      value: formatFileSize(selectedResult.fileSize),
      detail: selectedResult.fileName,
      icon: ImageIcon,
    },
  ];

  return (
    <div
      style={{
        width: "100%",
        display: "grid",
        gap: "1rem",
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "1rem",
        }}
      >
        {statCards.map((item) => {
          const Icon = item.icon;
          return (
            <Card
              key={item.label}
              className="p-4"
              style={{
                ...panelStyle,
                minHeight: "116px",
                justifyContent: "space-between",
              }}
            >
              <div className="flex items-center justify-between gap-3">
                <span
                  className="text-xs"
                  style={{ color: "#655080", fontWeight: 600 }}
                >
                  {item.label}
                </span>
                <Icon className="w-4 h-4 text-[#655080]" />
              </div>
              <div>
                <p
                  style={{
                    color: "#1f2937",
                    fontSize: "1.6rem",
                    fontWeight: 700,
                    lineHeight: 1.1,
                  }}
                >
                  {item.value}
                </p>
                <p
                  className="text-xs"
                  style={{
                    color: "#655080",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {item.detail}
                </p>
              </div>
            </Card>
          );
        })}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
          gap: "1rem",
          alignItems: "stretch",
        }}
      >
        <Card className="p-5" style={panelStyle}>
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <h3 className="font-semibold text-gray-900">Source Image</h3>
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <Calendar className="w-4 h-4" />
                {selectedResult.uploadDate.toLocaleString()}
              </div>
            </div>
            <Badge
              variant={
                selectedResult.isAIGenerated ? "destructive" : "default"
              }
            >
              {detectionLabel}
            </Badge>
          </div>

          <div className="flex justify-center">
            <MediaFrame>
              <img
                src={selectedResult.imageUrl}
                alt={selectedResult.fileName}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "contain",
                }}
              />
            </MediaFrame>
          </div>
        </Card>

        <Card className="p-5" style={panelStyle}>
          <h3 className="font-semibold text-gray-900 mb-2">Result Summary</h3>
          <p className="text-sm text-gray-600 mb-5">
            This report combines the model score with forensic checks and visual evidence maps.
          </p>

          <div className="space-y-4">
            <div style={mutedPanelStyle} className="p-4">
              <div className="flex justify-between text-sm">
                <span>Overall Confidence</span>
                <span>{selectedResult.confidence.toFixed(1)}%</span>
              </div>
              <Progress value={selectedResult.confidence} className="mt-2" />
            </div>

            {typeof elaScore === "number" && (
              <div style={mutedPanelStyle} className="p-4">
                <div className="flex justify-between text-sm">
                  <span>ELA Score</span>
                  <span>{elaScore.toFixed(1)}%</span>
                </div>
                <Progress value={elaScore} className="mt-2" />
              </div>
            )}

            <div
              style={{
                ...mutedPanelStyle,
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                gap: "0.75rem",
              }}
              className="p-4 text-sm"
            >
              <div>
                <p className="text-gray-500">File</p>
                <p className="text-gray-900" style={{ wordBreak: "break-word" }}>
                  {selectedResult.fileName}
                </p>
              </div>
              <div>
                <p className="text-gray-500">Forensic checks</p>
                <p className="text-gray-900">{forensicTests.length}</p>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <Card className="p-5" style={panelStyle}>
        <div className="flex items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="font-semibold text-gray-900">
              Forensic Test Results
            </h3>
            <p className="text-sm text-gray-600">
              Compression, consistency, and pattern checks.
            </p>
          </div>
          <Badge variant="secondary">{forensicTests.length} checks</Badge>
        </div>

        {forensicTests.length === 0 ? (
          <p>No forensic test results available.</p>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "0.75rem",
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

      {selectedResult.ela && (
        <Card className="p-5" style={panelStyle}>
          <div className="flex items-center gap-2 mb-4">
            <Flame className="w-5 h-5" />
            <div>
              <h3 className="font-semibold text-gray-900">ELA Heatmap</h3>
              <p className="text-sm text-gray-600">
                Error level response mapped over the image.
              </p>
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
              gap: "1rem",
              alignItems: "center",
            }}
          >
            <div className="flex justify-center">
              {heatmapUrl ? (
                <MediaFrame>
                  <img
                    src={heatmapUrl}
                    alt="ELA heatmap"
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "contain",
                    }}
                  />
                </MediaFrame>
              ) : (
                <div className="h-48 flex items-center justify-center text-gray-400">
                  Heatmap not available
                </div>
              )}
            </div>

            <div className="space-y-4">
              <div style={mutedPanelStyle} className="p-4">
                <div className="flex justify-between text-sm">
                  <span>ELA Score</span>
                  <span>{selectedResult.ela.score.toFixed(1)}%</span>
                </div>
                <Progress value={selectedResult.ela.score} className="mt-2" />
              </div>

              <p className="text-sm text-gray-700">
                {selectedResult.ela.explanation}
              </p>

              {selectedResult.ela.metrics && (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                    gap: "0.75rem",
                  }}
                >
                  <div style={mutedPanelStyle} className="p-3 text-sm">
                    <p className="text-gray-500">Mean Intensity</p>
                    <p className="text-gray-900">
                      {formatPercentMetric(
                        selectedResult.ela.metrics.mean_intensity
                      )}
                    </p>
                  </div>
                  <div style={mutedPanelStyle} className="p-3 text-sm">
                    <p className="text-gray-500">Hotspot Ratio</p>
                    <p className="text-gray-900">
                      {formatRatioMetric(
                        selectedResult.ela.metrics.hotspot_ratio
                      )}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      <Card className="p-5 bg-purple-100" style={panelStyle}>
        <h3>Analysis Summary</h3>
        <p className="text-sm text-gray-700">
          The overall confidence score of{" "}
          {selectedResult.confidence.toFixed(1)}% suggests that it is{" "}
          {selectedResult.isAIGenerated
            ? "likely AI-generated"
            : "likely real"}.
        </p>
      </Card>
    </div>
  );
}
