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

function isElaTest(testName: string) {
  const normalized = testName.toLowerCase();
  return normalized.includes("error level") || normalized.includes("ela");
}

function isCompressionTest(testName: string) {
  const normalized = testName.toLowerCase();
  return normalized.includes("compression") || normalized.includes("artifact");
}

function isNoiseTextureTest(testName: string) {
  const normalized = testName.toLowerCase();
  return normalized.includes("noise") || normalized.includes("texture");
}

function isCopyMoveTest(testName: string) {
  const normalized = testName.toLowerCase();
  return (
    normalized.includes("copy-move") ||
    normalized.includes("copy move") ||
    normalized.includes("clone")
  );
}

function isProvenanceTest(testName: string) {
  const normalized = testName.toLowerCase();
  return normalized.includes("provenance") || normalized.includes("watermark");
}

function isFrequencyFingerprintTest(testName: string) {
  const normalized = testName.toLowerCase();
  return normalized.includes("frequency fingerprint");
}

function isDiffusionReconstructionTest(testName: string) {
  const normalized = testName.toLowerCase();
  return normalized.includes("diffusion") || normalized.includes("reconstruction");
}

function isSemanticConsistencyTest(testName: string) {
  const normalized = testName.toLowerCase();
  return normalized.includes("semantic");
}

function getVerdictLabel(testName: string, verdict: string) {
  if (isProvenanceTest(testName)) {
    switch (verdict) {
      case "clean":
        return "no provenance found";
      case "suspicious":
        return "AI provenance found";
      default:
        return "metadata inconclusive";
    }
  }

  if (isFrequencyFingerprintTest(testName)) {
    switch (verdict) {
      case "clean":
        return "no spectral fingerprint";
      case "suspicious":
        return "AI spectral pattern";
      default:
        return "review spectrum";
    }
  }

  if (isDiffusionReconstructionTest(testName)) {
    switch (verdict) {
      case "clean":
        return "no reconstruction signal";
      case "suspicious":
        return "reconstruction signal";
      default:
        return "review reconstruction";
    }
  }

  if (isSemanticConsistencyTest(testName)) {
    switch (verdict) {
      case "clean":
        return "no semantic anomaly";
      case "suspicious":
        return "semantic anomaly";
      default:
        return "review semantics";
    }
  }

  if (isElaTest(testName)) {
    switch (verdict) {
      case "clean":
        return "no edit hotspot";
      case "suspicious":
        return "edit hotspots";
      default:
        return "review hotspots";
    }
  }

  if (isCopyMoveTest(testName)) {
    switch (verdict) {
      case "clean":
        return "no clone match";
      case "suspicious":
        return "clone match";
      default:
        return "review clone";
    }
  }

  if (isNoiseTextureTest(testName)) {
    switch (verdict) {
      case "clean":
        return "consistent noise";
      case "suspicious":
        return "noise mismatch";
      default:
        return "review texture";
    }
  }

  if (isCompressionTest(testName)) {
    switch (verdict) {
      case "clean":
        return "no compression anomaly";
      case "suspicious":
        return "compression mismatch";
      default:
        return "weak signal";
    }
  }

  switch (verdict) {
    case "clean":
      return "low signal";
    case "suspicious":
      return "suspicious";
    default:
      return "weak signal";
  }
}

function getScoreLabel(testName: string) {
  if (isProvenanceTest(testName)) return "Provenance signal";
  if (isFrequencyFingerprintTest(testName)) return "Frequency fingerprint";
  if (isDiffusionReconstructionTest(testName)) return "Reconstruction signal";
  if (isSemanticConsistencyTest(testName)) return "Semantic signal";
  if (isElaTest(testName)) return "ELA signal";
  if (isCopyMoveTest(testName)) return "Clone signal";
  if (isNoiseTextureTest(testName)) return "Noise/texture signal";
  if (isCompressionTest(testName)) return "Compression signal";
  return "Forensic signal";
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
        "ela_score",
        "block_inconsistency_score",
        "noise_variance_score",
        "clone_score",
        "provenance_score",
        "frequency_fingerprint_score",
        "diffusion_reconstruction_score",
        "semantic_consistency_score",
        "clone_pairs",
        "indicators",
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
            "noise_variance_score",
            "clone_score",
            "provenance_score",
            "frequency_fingerprint_score",
            "diffusion_reconstruction_score",
            "semantic_consistency_score",
            "raw_block_inconsistency_score",
            "raw_noise_variance_score",
            "raw_clone_score",
            "raw_frequency_fingerprint_score",
            "raw_diffusion_reconstruction_score",
            "raw_semantic_consistency_score",
            "raw_ela_score",
            "request_id",
          ].includes(key)
      )
    : [];

  return (
    <Card
      className="p-3 bg-white/80 border border-[#8d70b3]/20 shadow-sm"
      style={{
        width: "100%",
        minWidth: 0,
        minHeight: "292px",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
        overflow: "hidden",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          {getIcon(test.verdict)}
          <span
            className="font-medium text-gray-900 text-sm"
            style={{
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
          {getVerdictLabel(test.test_name, test.verdict)}
        </Badge>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-gray-600">{getScoreLabel(test.test_name)}</span>
          <span className="text-gray-900">{(test.score * 100).toFixed(1)}%</span>
        </div>
        <Progress value={test.score * 100} className="h-1.5" />
      </div>

      {artifactMap && (
        <div>
          <img
            src={artifactMap.url}
            alt={`${test.test_name} artifact map`}
            className="w-full rounded border bg-black"
            style={{
              height: "128px",
              objectFit: "contain",
            }}
          />
        </div>
      )}

      {detailsEntries.length > 0 && (
        <div className="space-y-1 pt-2 border-t border-[#8d70b3]/20">
          {detailsEntries.map(([key, value]) => (
            <div key={key} className="text-xs">
              {key === "explanation" && value ? (
                <p
                  className="text-xs text-gray-600"
                  style={{
                    display: "-webkit-box",
                    WebkitLineClamp: artifactMap ? 2 : 4,
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
            <div className="flex justify-between gap-3 text-xs">
              <span className="text-gray-500">Highlighted Regions</span>
              <span className="text-gray-900">{regions.length}</span>
            </div>
          )}

          {metricEntries.slice(0, artifactMap ? 2 : 3).map(([key, value]) => (
            <div key={key} className="flex justify-between gap-3 text-xs">
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
