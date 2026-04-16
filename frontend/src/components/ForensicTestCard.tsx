import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import type { ForensicTest } from "../api/detector";

interface Props {
  test: ForensicTest;
}

type DetailRecord = Record<string, unknown>;

function getVerdictStyles(verdict: string) {
  switch (verdict) {
    case "clean":
      return {
        icon: <CheckCircle className="w-4 h-4" style={{ color: "#059669" }} />,
        bar: "#10b981",
        badge: {
          backgroundColor: "#ecfdf5",
          color: "#047857",
          border: "1px solid #bbf7d0",
        },
      };
    case "suspicious":
      return {
        icon: <XCircle className="w-4 h-4" style={{ color: "#e11d48" }} />,
        bar: "#e11d48",
        badge: {
          backgroundColor: "#fff1f2",
          color: "#be123c",
          border: "1px solid #fecdd3",
        },
      };
    default:
      return {
        icon: <AlertTriangle className="w-4 h-4" style={{ color: "#d97706" }} />,
        bar: "#f59e0b",
        badge: {
          backgroundColor: "#fffbeb",
          color: "#b45309",
          border: "1px solid #fde68a",
        },
      };
  }
}

function formatDetailKey(key: string) {
  if (key === "explanation") return "Explanation";
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDetailValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  }
  if (Array.isArray(value)) {
    return `${value.length} item${value.length === 1 ? "" : "s"}`;
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function isDetailRecord(value: unknown): value is DetailRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getArtifactMap(details: DetailRecord) {
  const artifactMap = details.artifact_map;
  if (!isDetailRecord(artifactMap) || typeof artifactMap.url !== "string") {
    return null;
  }
  return {
    url: artifactMap.url,
    mediaType:
      typeof artifactMap.mediaType === "string"
        ? artifactMap.mediaType
        : "image/png",
  };
}

export default function ForensicTestCard({ test }: Props) {
  const details = test.details || {};
  const artifactMap = getArtifactMap(details);
  const regions = Array.isArray(details.regions) ? details.regions : [];
  const metrics = isDetailRecord(details.metrics) ? details.metrics : null;
  const verdict = getVerdictStyles(test.verdict);
  const score = Math.max(0, Math.min(1, test.score));

  const detailsEntries = Object.entries(details).filter(
    ([key, value]) =>
      value !== "" &&
      ![
        "artifact_map",
        "block_inconsistency_score",
        "regions",
        "metrics",
      ].includes(key)
  );
  const metricEntries = metrics
    ? Object.entries(metrics).filter(
        ([key, value]) =>
          ["string", "number", "boolean"].includes(typeof value) &&
          value !== "" &&
          ![
            "analyzed_blocks",
            "block_inconsistency_score",
            "raw_block_inconsistency_score",
            "request_id",
          ].includes(key)
      )
    : [];

  return (
    <Card
      style={{
        width: "100%",
        minHeight: "232px",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: "0.875rem",
        padding: "1rem",
        borderRadius: "8px",
        border: "1px solid #e5e7eb",
        backgroundColor: "#ffffff",
        boxShadow: "0 10px 28px rgba(15, 23, 42, 0.05)",
        overflow: "hidden",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          {verdict.icon}
          <span
            style={{
              color: "#111827",
              fontWeight: 700,
              fontSize: "0.875rem",
              lineHeight: 1.25,
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {test.test_name}
          </span>
        </div>

        <Badge variant="outline" style={verdict.badge}>
          {test.verdict}
        </Badge>
      </div>

      <div>
        <div className="flex items-center justify-between text-xs" style={{ color: "#64748b" }}>
          <span>Score</span>
          <span style={{ color: "#111827", fontWeight: 700 }}>
            {(score * 100).toFixed(1)}%
          </span>
        </div>
        <div
          style={{
            height: "6px",
            borderRadius: "999px",
            backgroundColor: "#e5e7eb",
            marginTop: "0.375rem",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${score * 100}%`,
              height: "100%",
              borderRadius: "999px",
              backgroundColor: verdict.bar,
            }}
          />
        </div>
      </div>

      {artifactMap && (
        <div
          style={{
            height: "72px",
            borderRadius: "8px",
            border: "1px solid #e5e7eb",
            backgroundColor: "#0f172a",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
          }}
        >
          <img
            src={artifactMap.url}
            alt={`${test.test_name} artifact map`}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "contain",
            }}
          />
        </div>
      )}

      {detailsEntries.length > 0 ? (
        <div style={{ display: "grid", gap: "0.375rem" }}>
          {detailsEntries.slice(0, artifactMap ? 1 : 2).map(([key, value]) => (
            <div key={key} className="text-xs">
              {key === "explanation" ? (
                <p
                  style={{
                    color: "#64748b",
                    display: "-webkit-box",
                    WebkitLineClamp: artifactMap ? 2 : 3,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {formatDetailValue(value)}
                </p>
              ) : (
                <div className="flex justify-between gap-3">
                  <span style={{ color: "#64748b" }}>{formatDetailKey(key)}</span>
                  <span style={{ color: "#111827", textAlign: "right" }}>
                    {formatDetailValue(value)}
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs" style={{ color: "#94a3b8" }}>
          Basic indicator score returned.
        </p>
      )}

      {(regions.length > 0 || metricEntries.length > 0) && (
        <div
          style={{
            display: "grid",
            gap: "0.375rem",
            marginTop: "auto",
            paddingTop: "0.75rem",
            borderTop: "1px solid #eef2f7",
          }}
        >
          {regions.length > 0 && (
            <div className="flex justify-between gap-3 text-xs">
              <span style={{ color: "#64748b" }}>Highlighted regions</span>
              <span style={{ color: "#111827", fontWeight: 700 }}>
                {regions.length}
              </span>
            </div>
          )}

          {metricEntries.slice(0, artifactMap ? 1 : 2).map(([key, value]) => (
            <div key={key} className="flex justify-between gap-3 text-xs">
              <span style={{ color: "#64748b" }}>{formatDetailKey(key)}</span>
              <span style={{ color: "#111827", textAlign: "right" }}>
                {formatDetailValue(value)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
