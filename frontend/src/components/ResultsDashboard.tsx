import { AnalysisResult } from "../App";
import type { ReactNode } from "react";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { Progress } from "./ui/progress";
import {
  BarChart3,
  Calendar,
  CheckCircle,
  Gauge,
  Image as ImageIcon,
  Layers,
} from "lucide-react";
import ForensicTestCard from "./ForensicTestCard";
import { normalizeForensicTests } from "../utils/forensicNormalizer";

interface ResultsDashboardProps {
  results: AnalysisResult[];
  selectedResult: AnalysisResult;
  onSelectResult: (result: AnalysisResult) => void;
}

const panelStyle = {
  borderRadius: "16px",
  border: "1px solid rgba(141, 112, 179, 0.3)",
  background: "rgba(255, 255, 255, 0.78)",
  boxShadow: "0 18px 42px rgba(61, 48, 77, 0.14)",
};

const mutedPanelStyle = {
  borderRadius: "14px",
  border: "1px solid rgba(141, 112, 179, 0.24)",
  background: "rgba(245, 240, 255, 0.58)",
};

function formatFileSize(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function getSignalLabel(status: "pass" | "warning" | "fail") {
  switch (status) {
    case "pass":
      return "strong AI signal";
    case "warning":
      return "moderate signal";
    default:
      return "low signal";
  }
}

function getSignalBadgeClass(status: "pass" | "warning" | "fail") {
  switch (status) {
    case "pass":
      return "bg-rose-100 text-rose-700 border-rose-200";
    case "warning":
      return "bg-amber-100 text-amber-700 border-amber-200";
    default:
      return "bg-emerald-100 text-emerald-700 border-emerald-200";
  }
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
        borderRadius: "14px",
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
  const forensicTests = normalizeForensicTests(selectedResult);
  const evidenceCheckCount = forensicTests.length;
  const detectionLabel = selectedResult.isAIGenerated
    ? "AI Generated"
    : "Real Photo";
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
      label: "Evidence Checks",
      value: String(evidenceCheckCount),
      detail: "forensic maps reviewed",
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
        width: "min(100%, 1320px)",
        margin: "0 auto",
        display: "grid",
        gap: "1.25rem",
        fontSize: "0.95rem",
        lineHeight: 1.4,
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
          gap: "1rem",
        }}
      >
        {statCards.map((item) => {
          const Icon = item.icon;
          return (
            <Card
              key={item.label}
              style={{
                ...panelStyle,
                minHeight: "108px",
                padding: "1rem",
                justifyContent: "space-between",
                gap: "0.75rem",
              }}
            >
              <div className="flex items-center justify-between gap-3">
                <span
                  style={{
                    color: "#655080",
                    fontSize: "0.82rem",
                    fontWeight: 700,
                  }}
                >
                  {item.label}
                </span>
                <Icon className="w-5 h-5 text-[#655080]" />
              </div>
              <div>
                <p
                  style={{
                    color: "#1f2937",
                    fontSize: item.value.length > 10 ? "1.2rem" : "1.45rem",
                    fontWeight: 700,
                    lineHeight: 1.1,
                    overflowWrap: "anywhere",
                  }}
                >
                  {item.value}
                </p>
                <p
                  style={{
                    color: "#655080",
                    fontSize: "0.84rem",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
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
          gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 360px), 1fr))",
          gap: "1.25rem",
          alignItems: "stretch",
        }}
      >
        <Card style={{ ...panelStyle, padding: "1.25rem" }}>
          <div className="flex items-center justify-between gap-3" style={{ marginBottom: "1rem" }}>
            <div>
              <h3
                className="font-semibold text-gray-900"
                style={{ fontSize: "1.05rem" }}
              >
                Source Image
              </h3>
              <div
                className="flex items-center gap-2 text-gray-500"
                style={{ fontSize: "0.88rem" }}
              >
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
            <MediaFrame maxWidth="500px">
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

        <Card style={{ ...panelStyle, padding: "1.25rem" }}>
          <h3
            className="font-semibold text-gray-900 mb-2"
            style={{ fontSize: "1.05rem" }}
          >
            Result Summary
          </h3>
          <p className="text-gray-600 mb-5" style={{ fontSize: "0.92rem" }}>
            This report combines the model score with supporting evidence checks.
          </p>

          <div className="space-y-4">
            <div style={mutedPanelStyle} className="p-4">
              <div
                className="flex justify-between"
                style={{ fontSize: "0.9rem" }}
              >
                <span>Overall Confidence</span>
                <span>{selectedResult.confidence.toFixed(1)}%</span>
              </div>
              <Progress value={selectedResult.confidence} className="mt-2" />
            </div>

            <div
              className="p-4"
              style={{
                ...mutedPanelStyle,
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                gap: "0.75rem",
                fontSize: "0.9rem",
              }}
            >
              <div>
                <p className="text-gray-500">File</p>
                <p className="text-gray-900" style={{ wordBreak: "break-word" }}>
                  {selectedResult.fileName}
                </p>
              </div>
              <div>
                <p className="text-gray-500">Evidence checks</p>
                <p className="text-gray-900">{evidenceCheckCount}</p>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {selectedResult.indicators.length > 0 && (
        <Card style={{ ...panelStyle, padding: "1.25rem" }}>
          <div
            className="flex items-start justify-between gap-3"
            style={{ marginBottom: "1rem" }}
          >
            <div className="flex items-start gap-2">
              <BarChart3
                className="w-5 h-5 text-[#655080]"
                style={{ flexShrink: 0, marginTop: "0.15rem" }}
              />
              <div>
                <h3
                  className="font-semibold text-gray-900"
                  style={{ fontSize: "1.05rem" }}
                >
                  Model Signals
                </h3>
                <p className="text-gray-600" style={{ fontSize: "0.92rem" }}>
                  Pixel, noise, edge, color, and frequency scores from the detector.
                </p>
              </div>
            </div>
            <Badge variant="secondary" style={{ flexShrink: 0 }}>
              {selectedResult.indicators.length} signals
            </Badge>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
              gap: "0.85rem",
            }}
          >
            {selectedResult.indicators.map((indicator) => (
              <div
                key={indicator.label}
                className="p-4"
                style={{
                  ...mutedPanelStyle,
                  minHeight: "128px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  gap: "0.75rem",
                }}
              >
                <div className="flex items-start justify-between gap-3">
                  <p
                    className="text-gray-900"
                    style={{
                      fontSize: "0.92rem",
                      fontWeight: 650,
                      lineHeight: 1.2,
                    }}
                  >
                    {indicator.label}
                  </p>
                  <Badge
                    variant="outline"
                    className={`border ${getSignalBadgeClass(indicator.status)}`}
                    style={{ whiteSpace: "normal", textAlign: "center" }}
                  >
                    {getSignalLabel(indicator.status)}
                  </Badge>
                </div>

                <div>
                  <div
                    className="flex justify-between"
                    style={{ fontSize: "0.9rem" }}
                  >
                    <span className="text-gray-600">Signal score</span>
                    <span className="text-gray-900">
                      {indicator.value.toFixed(1)}%
                    </span>
                  </div>
                  <Progress value={indicator.value} className="mt-2" />
                </div>

                {indicator.explanation && (
                  <p
                    className="text-gray-600"
                    style={{
                      fontSize: "0.82rem",
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {indicator.explanation}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card
        style={{
          ...panelStyle,
          padding: "1.5rem",
          gap: "1.25rem",
        }}
      >
        <div
          className="flex items-start justify-between gap-3"
          style={{ alignItems: "flex-start" }}
        >
          <div>
            <h3
              className="font-semibold text-gray-900"
              style={{ fontSize: "1.05rem", lineHeight: 1.25 }}
            >
              Forensic Test Results
            </h3>
            <p
              className="text-gray-600"
              style={{ fontSize: "0.92rem", lineHeight: 1.45, marginTop: "0.25rem" }}
            >
              Checks for edit hotspots and local compression mismatches.
            </p>
          </div>
          <Badge variant="secondary" style={{ flexShrink: 0 }}>
            {evidenceCheckCount} evidence {evidenceCheckCount === 1 ? "check" : "checks"}
          </Badge>
        </div>

        {forensicTests.length === 0 ? (
          <p className="text-gray-600" style={{ fontSize: "0.92rem" }}>
            No forensic evidence maps were available for this file.
          </p>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 340px))",
              gap: "1rem",
              justifyContent: "start",
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

      <Card className="bg-purple-100" style={{ ...panelStyle, padding: "1.25rem" }}>
        <h3 style={{ fontSize: "1.05rem" }}>Analysis Summary</h3>
        <p className="text-gray-700" style={{ fontSize: "0.92rem" }}>
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
