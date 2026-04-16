import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { Progress } from "./ui/progress";
import { CheckCircle, AlertTriangle, XCircle } from "lucide-react";
import type { ForensicTest } from "../App";

interface Props {
  test: ForensicTest;
}

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
  return String(value);
}

export default function ForensicTestCard({ test }: Props) {
  const detailsEntries = Object.entries(test.details || {}).filter(
    ([, value]) => value !== ""
  );

  return (
    <Card className="p-4 bg-white/80 border border-[#8d70b3]/20 shadow-sm">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          {getIcon(test.verdict)}
          <span className="font-medium text-gray-900">{test.test_name}</span>
        </div>

        <Badge
          variant="outline"
          className={`text-xs border ${getVerdictColor(test.verdict)}`}
        >
          {test.verdict}
        </Badge>
      </div>

      <div className="space-y-2 mb-3">
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-600">Score</span>
          <span className="text-gray-900">{(test.score * 100).toFixed(1)}%</span>
        </div>
        <Progress value={test.score * 100} className="h-1.5" />
      </div>

      {detailsEntries.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-[#8d70b3]/20">
          {detailsEntries.map(([key, value]) => (
            <div key={key} className="text-sm">
              {key === "explanation" && value ? (
                <p className="text-sm text-gray-600 leading-relaxed mt-1">
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
    </Card>
  );
}