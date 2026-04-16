import { useEffect, useState } from "react";
import { Download, ShieldCheck } from "lucide-react";
import { Button } from "./components/ui/button";
import { Card } from "./components/ui/card";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "./components/ui/tabs";
import { Progress } from "./components/ui/progress";
import { Badge } from "./components/ui/badge";
import { UploadZone } from "./components/UploadZone";
import { ResultsDashboard } from "./components/ResultsDashboard";
import { HowToGuide } from "./components/HowToGuide";
import { exportToPDF } from "./utils/pdfExport";
import {
  detectImage,
  type ELAMetadata,
  type ForensicTest,
} from "./api/detector";

export interface AnalysisResult {
  id: string;
  fileName: string;
  fileSize: number;
  uploadDate: Date;
  isAIGenerated: boolean;
  confidence: number;
  indicators: {
    label: string;
    value: number;
    status: "pass" | "warning" | "fail";
    explanation?: string;
  }[];
  forensic_tests?: ForensicTest[];
  imageUrl: string;
  ela?: ELAMetadata;
}

export default function App() {
  const [currentTab, setCurrentTab] = useState<
    "upload" | "results" | "guide"
  >("upload");
  const [currentResult, setCurrentResult] =
    useState<AnalysisResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [lastUploadedFile, setLastUploadedFile] =
    useState<File | null>(null);

  useEffect(() => {
    return () => {
      if (currentResult?.imageUrl) {
        URL.revokeObjectURL(currentResult.imageUrl);
      }
    };
  }, [currentResult]);

  const handleFileUpload = async (files: File[]) => {
    if (!files.length || isAnalyzing) return;

    const file = files[0];
    setLastUploadedFile(file);
    setIsAnalyzing(true);
    setUploadError(null);

    try {
      const response = await detectImage(file);
      const previewUrl = URL.createObjectURL(file);

      setCurrentResult((previous) => {
        if (previous?.imageUrl) {
          URL.revokeObjectURL(previous.imageUrl);
        }

        return {
          id: response.metadata?.requestId ?? Date.now().toString(),
          fileName: file.name,
          fileSize: file.size,
          uploadDate: new Date(),
          isAIGenerated: response.isAIGenerated,
          confidence: response.confidence,
          indicators: response.indicators,
          forensic_tests: response.forensic_tests,
          imageUrl: previewUrl,
          ela: response.metadata?.ela,
        };
      });

      setCurrentTab("results");
    } catch (error: any) {
      let message = "Analysis failed. Please try again.";
      const status = error?.response?.status ?? error?.status;

      if (status === 422) {
        message =
          "Invalid file. Please upload a JPG, PNG, or WEBP image under 10MB.";
      } else if (status === 415) {
        message =
          "Unsupported file type. Please upload JPG, PNG, or WEBP.";
      } else if (
        typeof error?.message === "string" &&
        (error.message.includes("Failed to fetch") ||
          error.message.includes("NetworkError") ||
          error.message.includes("ECONNREFUSED"))
      ) {
        message =
          "Cannot connect to backend. Make sure the server is running.";
      } else if (error instanceof Error && error.message) {
        message = error.message;
      }

      setUploadError(message);
      setCurrentTab("upload");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleRetry = () => {
    if (lastUploadedFile) {
      void handleFileUpload([lastUploadedFile]);
    }
  };

  const handleExportPDF = () => {
    if (currentResult) {
      exportToPDF(currentResult);
    }
  };

  const isResultsView = currentTab === "results";
  const pageMaxWidth = isResultsView ? "none" : "1120px";

  const tabTriggerStyle = (isActive: boolean) => ({
    border: "0",
    borderRadius: "999px",
    color: isActive ? "#ffffff" : "#4b5563",
    backgroundColor: isActive ? "#111827" : "transparent",
    boxShadow: isActive ? "0 6px 16px rgba(17, 24, 39, 0.16)" : "none",
    padding: "0.5rem 1rem",
  });

  return (
    <div
      className="min-h-screen"
      style={{
        background:
          "linear-gradient(180deg, #f8fafc 0%, #f2f5f9 44%, #eef2f7 100%)",
        color: "#111827",
      }}
    >
      <header
        className="sticky top-0 z-10"
        style={{
          backgroundColor: "rgba(255, 255, 255, 0.92)",
          borderBottom: "1px solid #e5e7eb",
          backdropFilter: "blur(14px)",
          boxShadow: "0 1px 2px rgba(15, 23, 42, 0.04)",
        }}
      >
        <div
          className="mx-auto flex justify-between"
          style={{
            maxWidth: "1600px",
            padding: "0.875rem 1.5rem",
            alignItems: "center",
          }}
        >
          <div className="flex gap-3 items-center">
            <div
              className="flex items-center justify-center"
              style={{
                width: "2.5rem",
                height: "2.5rem",
                borderRadius: "8px",
                backgroundColor: "#111827",
                color: "#ffffff",
                boxShadow: "0 10px 24px rgba(17, 24, 39, 0.18)",
              }}
            >
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h1 style={{ fontWeight: 700, letterSpacing: "0" }}>
                AI Photo Detector
              </h1>
              <p className="text-sm" style={{ color: "#64748b" }}>
                Forensic checks for generated or edited images
              </p>
            </div>
          </div>

          {currentResult && (
            <Badge
              variant="secondary"
              style={{
                backgroundColor: "#eef2f7",
                color: "#334155",
                border: "1px solid #d8dee8",
              }}
            >
              1 analysis
            </Badge>
          )}
        </div>
      </header>

      <main
        className="mx-auto"
        style={{
          maxWidth: pageMaxWidth,
          width: "100%",
          padding: isResultsView ? "1.5rem 2rem 3rem" : "2rem 1.5rem 3.5rem",
        }}
      >
        <Tabs
          value={currentTab}
          onValueChange={(value) =>
            setCurrentTab(value as "upload" | "results" | "guide")
          }
        >
          <TabsList
            className="mx-auto"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
              width: "min(100%, 420px)",
              height: "auto",
              borderRadius: "999px",
              border: "1px solid #e5e7eb",
              backgroundColor: "#ffffff",
              boxShadow: "0 12px 32px rgba(15, 23, 42, 0.08)",
              padding: "0.25rem",
            }}
          >
            <TabsTrigger
              value="upload"
              style={tabTriggerStyle(currentTab === "upload")}
            >
              Upload
            </TabsTrigger>
            <TabsTrigger
              value="results"
              disabled={!currentResult}
              style={tabTriggerStyle(currentTab === "results")}
            >
              Results
            </TabsTrigger>
            <TabsTrigger
              value="guide"
              style={tabTriggerStyle(currentTab === "guide")}
            >
              How to Use
            </TabsTrigger>
          </TabsList>

          <TabsContent value="upload">
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "1.5rem",
                marginTop: "2rem",
                alignItems: "stretch",
              }}
            >
              <Card
                className="p-8"
                style={{
                  flex: "1 1 560px",
                  borderRadius: "8px",
                  border: "1px solid #e5e7eb",
                  backgroundColor: "#ffffff",
                  boxShadow: "0 20px 60px rgba(15, 23, 42, 0.08)",
                }}
              >
                <UploadZone
                  onUpload={handleFileUpload}
                  isAnalyzing={isAnalyzing}
                />

                {isAnalyzing && (
                  <div className="mt-4">
                    <Progress value={66} />
                    <p className="text-sm" style={{ color: "#475569" }}>
                      Running forensic analysis...
                    </p>
                  </div>
                )}

                {uploadError && (
                  <div
                    className="mt-4"
                    style={{
                      color: "#be123c",
                      display: "flex",
                      gap: "0.75rem",
                      alignItems: "center",
                    }}
                  >
                    {uploadError}
                    <Button onClick={handleRetry}>Retry</Button>
                  </div>
                )}
              </Card>

              <aside
                style={{
                  flex: "1 1 300px",
                  borderRadius: "8px",
                  border: "1px solid #e5e7eb",
                  backgroundColor: "#ffffff",
                  padding: "1.5rem",
                  boxShadow: "0 20px 60px rgba(15, 23, 42, 0.06)",
                }}
              >
                <p
                  style={{
                    color: "#111827",
                    fontWeight: 700,
                    marginBottom: "0.75rem",
                  }}
                >
                  Analysis stack
                </p>
                {[
                  "AI likelihood scoring",
                  "JPEG artifact inconsistency",
                  "Error level heatmap",
                  "Pixel and noise checks",
                ].map((item) => (
                  <div
                    key={item}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      padding: "0.75rem 0",
                      borderTop: "1px solid #eef2f7",
                      color: "#475569",
                    }}
                  >
                    <span
                      style={{
                        width: "0.5rem",
                        height: "0.5rem",
                        borderRadius: "999px",
                        backgroundColor: "#10b981",
                      }}
                    />
                    {item}
                  </div>
                ))}
              </aside>
            </div>
          </TabsContent>

          <TabsContent value="results">
            {currentResult ? (
              <div style={{ marginTop: "1.5rem" }}>
                <div
                  className="flex justify-between items-center"
                  style={{ marginBottom: "1rem" }}
                >
                  <div>
                    <h2 style={{ color: "#111827", fontWeight: 700 }}>
                      Analysis results
                    </h2>
                    <p className="text-sm" style={{ color: "#64748b" }}>
                      Review confidence, forensic signals, and visual evidence.
                    </p>
                  </div>
                  <Button
                    onClick={handleExportPDF}
                    style={{
                      backgroundColor: "#111827",
                      color: "#ffffff",
                      borderRadius: "8px",
                    }}
                  >
                    <Download className="w-4 h-4" />
                    Export PDF
                  </Button>
                </div>

                <ResultsDashboard
                  results={[currentResult]}
                  selectedResult={currentResult}
                  onSelectResult={() => { }}
                />
              </div>
            ) : (
              <Card className="p-6 text-center" style={{ marginTop: "2rem" }}>
                No results yet
              </Card>
            )}
          </TabsContent>

          <TabsContent value="guide">
            <div style={{ marginTop: "2rem" }}>
              <HowToGuide />
            </div>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
