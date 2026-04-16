import { AnalysisResult } from "../App";
import { Badge } from "./ui/badge";
import { Progress } from "./ui/progress";
import { Calendar, FileImage, Flame, Gauge, Layers } from "lucide-react";
import ForensicTestCard from "./ForensicTestCard";
import { normalizeForensicTests } from "../utils/forensicNormalizer";

interface ResultsDashboardProps {
  results: AnalysisResult[];
  selectedResult: AnalysisResult;
  onSelectResult: (result: AnalysisResult) => void;
}

const sectionStyle = {
  backgroundColor: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: "8px",
  boxShadow: "0 18px 48px rgba(15, 23, 42, 0.06)",
  padding: "1.5rem",
};

const mediaFrameStyle = {
  width: "min(100%, 640px)",
  aspectRatio: "4 / 3",
  borderRadius: "8px",
  backgroundColor: "#0f172a",
  border: "1px solid #d8dee8",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  overflow: "hidden",
};

const evidenceCardStyle = {
  border: "1px solid #e5e7eb",
  borderRadius: "8px",
  backgroundColor: "#f8fafc",
  padding: "1rem",
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

  const forensicTests = normalizeForensicTests(selectedResult)
    .slice()
    .sort((first, second) => second.score - first.score);
  const resultLabel = selectedResult.isAIGenerated ? "AI generated" : "Real photo";
  const resultTone = selectedResult.isAIGenerated
    ? {
        backgroundColor: "#fff1f2",
        color: "#be123c",
        border: "1px solid #fecdd3",
      }
    : {
        backgroundColor: "#ecfdf5",
        color: "#047857",
        border: "1px solid #bbf7d0",
      };

  const summaryItems = [
    {
      label: "Confidence",
      value: `${selectedResult.confidence.toFixed(1)}%`,
      icon: Gauge,
    },
    {
      label: "Forensic tests",
      value: String(forensicTests.length),
      icon: Layers,
    },
    {
      label: "File size",
      value: formatFileSize(selectedResult.fileSize),
      icon: FileImage,
    },
  ];

  return (
    <div style={{ display: "grid", gap: "1rem", width: "100%" }}>
      <section style={sectionStyle}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "1.5rem",
            alignItems: "stretch",
          }}
        >
          <div
            style={{
              flex: "1 1 480px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div style={mediaFrameStyle}>
              <img
                src={selectedResult.imageUrl}
                alt={selectedResult.fileName}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "contain",
                }}
              />
            </div>
          </div>

          <div
            style={{
              flex: "1 1 420px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              gap: "1.25rem",
              minWidth: 0,
            }}
          >
            <div>
              <div
                className="flex items-center gap-2"
                style={{ color: "#64748b", marginBottom: "0.5rem" }}
              >
                <Calendar className="w-4 h-4" />
                <span className="text-sm">
                  {selectedResult.uploadDate.toLocaleString()}
                </span>
              </div>
              <div
                className="flex items-center justify-between gap-3"
                style={{ marginBottom: "0.5rem" }}
              >
                <h3
                  style={{
                    color: "#111827",
                    fontWeight: 700,
                    wordBreak: "break-word",
                  }}
                >
                  {selectedResult.fileName}
                </h3>
                <Badge variant="outline" style={resultTone}>
                  {resultLabel}
                </Badge>
              </div>
              <p className="text-sm" style={{ color: "#64748b" }}>
                The image was checked against model confidence and forensic signals.
              </p>
            </div>

            <div>
              <div className="flex justify-between text-sm" style={{ color: "#475569" }}>
                <span>Overall confidence</span>
                <span>{selectedResult.confidence.toFixed(1)}%</span>
              </div>
              <Progress value={selectedResult.confidence} />
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
                gap: "0.75rem",
              }}
            >
              {summaryItems.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label} style={evidenceCardStyle}>
                    <Icon className="w-4 h-4" style={{ color: "#2563eb" }} />
                    <p
                      className="text-xs"
                      style={{ color: "#64748b", marginTop: "0.5rem" }}
                    >
                      {item.label}
                    </p>
                    <p style={{ color: "#111827", fontWeight: 700 }}>
                      {item.value}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      <section style={sectionStyle}>
        <div
          className="flex items-center justify-between gap-3"
          style={{ marginBottom: "1rem" }}
        >
          <div>
            <h3 style={{ color: "#111827", fontWeight: 700 }}>
              Forensic test results
            </h3>
            <p className="text-sm" style={{ color: "#64748b" }}>
              Signals are ranked by score and evidence strength.
            </p>
          </div>
          <Badge
            variant="secondary"
            style={{
              backgroundColor: "#eef2f7",
              color: "#334155",
              border: "1px solid #d8dee8",
            }}
          >
            {forensicTests.length} checks
          </Badge>
        </div>

        {forensicTests.length === 0 ? (
          <p style={{ color: "#64748b" }}>No forensic test results available.</p>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "1rem",
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
      </section>

      {selectedResult.ela && (
        <section style={sectionStyle}>
          <div className="flex items-center gap-2" style={{ marginBottom: "1rem" }}>
            <Flame className="w-5 h-5" style={{ color: "#f59e0b" }} />
            <div>
              <h3 style={{ color: "#111827", fontWeight: 700 }}>ELA evidence</h3>
              <p className="text-sm" style={{ color: "#64748b" }}>
                Error level response mapped over the source image.
              </p>
            </div>
          </div>

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "1.5rem",
              alignItems: "center",
            }}
          >
            <div
              style={{
                flex: "1 1 480px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {heatmapUrl ? (
                <div style={mediaFrameStyle}>
                  <img
                    src={heatmapUrl}
                    alt="ELA heatmap"
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "contain",
                    }}
                  />
                </div>
              ) : (
                <div style={mediaFrameStyle}>
                  <p style={{ color: "#94a3b8" }}>Heatmap not available</p>
                </div>
              )}
            </div>

            <div style={{ flex: "1 1 360px", display: "grid", gap: "1rem" }}>
              <div style={evidenceCardStyle}>
                <div className="flex justify-between text-sm" style={{ color: "#475569" }}>
                  <span>ELA score</span>
                  <span>{selectedResult.ela.score.toFixed(1)}%</span>
                </div>
                <Progress value={selectedResult.ela.score} />
              </div>

              <div style={evidenceCardStyle}>
                <p style={{ color: "#111827", fontWeight: 700, marginBottom: "0.5rem" }}>
                  Interpretation
                </p>
                <p className="text-sm" style={{ color: "#475569" }}>
                  {selectedResult.ela.explanation}
                </p>
              </div>

              {selectedResult.ela.metrics && (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                    gap: "0.75rem",
                  }}
                >
                  <div style={evidenceCardStyle}>
                    <p className="text-xs" style={{ color: "#64748b" }}>
                      Mean intensity
                    </p>
                    <p style={{ color: "#111827", fontWeight: 700 }}>
                      {formatPercentMetric(
                        selectedResult.ela.metrics.mean_intensity
                      )}
                    </p>
                  </div>
                  <div style={evidenceCardStyle}>
                    <p className="text-xs" style={{ color: "#64748b" }}>
                      Hotspot ratio
                    </p>
                    <p style={{ color: "#111827", fontWeight: 700 }}>
                      {formatRatioMetric(
                        selectedResult.ela.metrics.hotspot_ratio
                      )}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      <section
        style={{
          ...sectionStyle,
          backgroundColor: "#111827",
          borderColor: "#111827",
          color: "#ffffff",
        }}
      >
        <h3 style={{ fontWeight: 700 }}>Analysis summary</h3>
        <p style={{ color: "#cbd5e1", marginTop: "0.5rem" }}>
          Overall confidence is {selectedResult.confidence.toFixed(1)}%, which
          indicates the image is {selectedResult.isAIGenerated ? "likely AI-generated" : "likely real"}.
        </p>
      </section>
    </div>
  );
}
