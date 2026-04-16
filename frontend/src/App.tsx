import { useEffect, useState } from "react";
import { FileText } from "lucide-react";
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

/* =======================
   MAIN RESULT TYPE
======================= */
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

/* =======================
   MAIN COMPONENT
======================= */
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

  /* =======================
     CLEAN UP IMAGE MEMORY
  ======================= */
  useEffect(() => {
    return () => {
      if (currentResult?.imageUrl) {
        URL.revokeObjectURL(currentResult.imageUrl);
      }
    };
  }, [currentResult]);

  /* =======================
     HANDLE FILE UPLOAD
  ======================= */
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

  /* =======================
     RETRY UPLOAD
  ======================= */
  const handleRetry = () => {
    if (lastUploadedFile) {
      void handleFileUpload([lastUploadedFile]);
    }
  };

  /* =======================
     EXPORT PDF
  ======================= */
  const handleExportPDF = () => {
    if (currentResult) {
      exportToPDF(currentResult);
    }
  };

  const isResultsView = currentTab === "results";

  /* =======================
     UI
  ======================= */
  return (
    <div className="min-h-screen bg-gradient-to-br from-[#b690e6] via-[#a280cc] to-[#8d70b3]">
      <header className="bg-white/80 backdrop-blur-md border-b border-[#8d70b3]/30 sticky top-0 z-10 shadow-sm">
        <div
          className="mx-auto px-4 py-4 flex justify-between"
          style={{
            maxWidth: isResultsView ? "none" : "80rem",
          }}
        >
          <div className="flex gap-3 items-center">
            <div className="w-10 h-10 bg-gradient-to-br from-[#8d70b3] to-[#655080] rounded-lg flex items-center justify-center shadow-md">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1>AI Photo Detector</h1>
              <p className="text-sm text-[#655080]">
                Detect AI-generated images with confidence
              </p>
            </div>
          </div>

          {currentResult && (
            <Badge variant="secondary">1 Analysis</Badge>
          )}
        </div>
      </header>

      <main
        className="mx-auto px-4 py-8"
        style={{
          maxWidth: isResultsView ? "none" : "80rem",
          width: "100%",
        }}
      >
        <Tabs
          value={currentTab}
          onValueChange={(v) =>
            setCurrentTab(v as "upload" | "results" | "guide")
          }
        >
          <TabsList className="grid grid-cols-3 max-w-md mx-auto">
            <TabsTrigger value="upload">Upload</TabsTrigger>
            <TabsTrigger value="results" disabled={!currentResult}>
              Results
            </TabsTrigger>
            <TabsTrigger value="guide">How to Use</TabsTrigger>
          </TabsList>

          {/* =======================
             UPLOAD TAB
          ======================= */}
          <TabsContent value="upload">
            <Card className="p-8 text-center">
              <UploadZone
                onUpload={handleFileUpload}
                isAnalyzing={isAnalyzing}
              />

              {isAnalyzing && (
                <div className="mt-4">
                  <Progress value={66} />
                  <p className="text-sm">Analyzing image...</p>
                </div>
              )}

              {uploadError && (
                <div className="mt-4 text-red-500">
                  {uploadError}
                  <Button onClick={handleRetry}>Retry</Button>
                </div>
              )}
            </Card>
          </TabsContent>

          {/* =======================
             RESULTS TAB
          ======================= */}
          <TabsContent value="results">
            {currentResult ? (
              <>
                <div
                  className="flex justify-between items-center"
                  style={{
                    margin: "1rem auto",
                    width: "min(100%, 1440px)",
                  }}
                >
                  <h2 className="text-white">Analysis Results</h2>
                  <Button onClick={handleExportPDF}>
                    Export PDF
                  </Button>
                </div>

                <ResultsDashboard
                  results={[currentResult]}
                  selectedResult={currentResult}
                  onSelectResult={() => { }}
                />
              </>
            ) : (
              <Card className="p-6 text-center">
                No Results Yet
              </Card>
            )}
          </TabsContent>

          {/* =======================
             GUIDE TAB
          ======================= */}
          <TabsContent value="guide">
            <HowToGuide />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
