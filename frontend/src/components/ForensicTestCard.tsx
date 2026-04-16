import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { Progress } from "./ui/progress";
import { CheckCircle, AlertTriangle, XCircle } from "lucide-react";
import type { ForensicTest } from "../api/detector";

interface Props {
  test: ForensicTest;
}

type DetailRecord = Record<string, unknown>;

function getVerdictColor(verdict: string) {
  switch (verdict) {
    case "clean":
      return "bg-emerald-100 text-emerald-700 border-emerald-200";
    case "suspicious":
      return "bg-rose-100 text-rose-700 border-rose-200";
    default:
      return "bg-amber-100 text-amber-700 border-amber-200";
  }
}

function getIcon(verdict: string) {
  switch (verdict) {
    case "clean":
      return <CheckCircle className="w-4 h-4 text-emerald-500" />;
    case "suspicious":
      return <XCircle className="w-4 h-4 text-rose-500" />;
    default:
      return <AlertTriangle className="w-4 h-4 text-amber-500" />;
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
      className="p-4 bg-white/80 border border-[#8d70b3]/20"
      style={{
        width: "100%",
        minWidth: 0,
        minHeight: "156px",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: "0.625rem",
        borderRadius: "16px",
        boxShadow: "0 8px 22px rgba(61, 48, 77, 0.1)",
        overflow: "hidden",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          {getIcon(test.verdict)}
          <span
            className="font-medium text-gray-900"
            style={{
              fontSize: "0.92rem",
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

        <Badge
          variant="outline"
          className={`text-xs border shrink-0 ${getVerdictColor(test.verdict)}`}
        >
          {test.verdict}
        </Badge>
      </div>

      <div className="space-y-2">
        <div
          className="flex items-center justify-between"
          style={{ fontSize: "0.82rem" }}
        >
          <span className="text-gray-600">Score</span>
          <span className="text-gray-900">{(test.score * 100).toFixed(1)}%</span>
        </div>
        <Progress value={test.score * 100} className="h-1.5" />
      </div>

      {detailsEntries.length > 0 && (
        <div className="space-y-1">
          {detailsEntries.slice(0, 1).map(([key, value]) => (
            <div key={key} style={{ fontSize: "0.82rem" }}>
              {key === "explanation" && value ? (
                <p
                  className="text-gray-600"
                  style={{
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {formatDetailValue(value)}
                </p>
              ) : (
                <div className="flex justify-between gap-3">
                  <span className="text-gray-500">{formatDetailKey(key)}</span>
                  <span className="text-gray-900 text-right">
                    {formatDetailValue(value)}
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {(regions.length > 0 || metricEntries.length > 0) && (
        <div
          className="space-y-1 pt-2 border-t border-[#8d70b3]/20"
          style={{ marginTop: "auto" }}
        >
          {regions.length > 0 && (
            <div
              className="flex justify-between gap-3"
              style={{ fontSize: "0.82rem" }}
            >
              <span className="text-gray-500">Highlighted Regions</span>
              <span className="text-gray-900">{regions.length}</span>
            </div>
          )}

          {artifactMap && (
            <div
              className="flex justify-between gap-3"
              style={{ fontSize: "0.82rem" }}
            >
              <span className="text-gray-500">Evidence Map</span>
              <span className="text-gray-900">Available</span>
            </div>
          )}

          {metricEntries.slice(0, artifactMap ? 1 : 2).map(([key, value]) => (
            <div
              key={key}
              className="flex justify-between gap-3"
              style={{ fontSize: "0.82rem" }}
            >
              <span className="text-gray-500">{formatDetailKey(key)}</span>
              <span className="text-gray-900 text-right">
                {formatDetailValue(value)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
