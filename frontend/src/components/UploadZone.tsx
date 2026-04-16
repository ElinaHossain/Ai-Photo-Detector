import { useCallback, useState } from "react";
import { FileCheck, Image as ImageIcon, Upload, X } from "lucide-react";
import { Button } from "./ui/button";

interface UploadZoneProps {
  onUpload: (files: File[]) => void;
  isAnalyzing: boolean;
}

export function UploadZone({ onUpload, isAnalyzing }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);

    const files = Array.from(event.dataTransfer.files).filter((file) =>
      file.type.startsWith("image/")
    );

    if (files.length > 0) {
      setSelectedFiles(files);
    }
  }, []);

  const handleFileInput = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      setSelectedFiles(Array.from(event.target.files));
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles((files) => files.filter((_, fileIndex) => fileIndex !== index));
  };

  const handleAnalyze = () => {
    if (selectedFiles.length > 0) {
      onUpload(selectedFiles);
      setSelectedFiles([]);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <p
          style={{
            color: "#111827",
            fontSize: "1.5rem",
            fontWeight: 700,
            lineHeight: 1.2,
            marginBottom: "0.5rem",
          }}
        >
          Upload an image
        </p>
        <p style={{ color: "#64748b" }}>
          Run AI detection, JPEG artifact analysis, and ELA evidence mapping.
        </p>
      </div>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{
          border: `1.5px dashed ${isDragging ? "#2563eb" : "#cbd5e1"}`,
          borderRadius: "8px",
          backgroundColor: isDragging ? "#eff6ff" : "#f8fafc",
          padding: "2.5rem",
          textAlign: "center",
          transition: "border-color 160ms ease, background-color 160ms ease, box-shadow 160ms ease",
          boxShadow: isDragging ? "0 16px 40px rgba(37, 99, 235, 0.12)" : "none",
        }}
      >
        <input
          type="file"
          id="file-upload"
          className="hidden"
          accept="image/*"
          multiple
          onChange={handleFileInput}
          disabled={isAnalyzing}
        />

        <div className="flex flex-col items-center gap-4">
          <div
            className="flex items-center justify-center"
            style={{
              width: "4rem",
              height: "4rem",
              borderRadius: "8px",
              backgroundColor: "#111827",
              color: "#ffffff",
              boxShadow: "0 14px 30px rgba(17, 24, 39, 0.18)",
            }}
          >
            <Upload className="w-8 h-8" />
          </div>

          <div>
            <p style={{ color: "#111827", fontWeight: 700, marginBottom: "0.25rem" }}>
              Drop image files here
            </p>
            <p className="text-sm" style={{ color: "#64748b" }}>
              JPG, PNG, and WEBP files up to 10 MB.
            </p>
          </div>

          <label
            htmlFor="file-upload"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              minHeight: "2.5rem",
              padding: "0 1rem",
              borderRadius: "8px",
              backgroundColor: "#ffffff",
              border: "1px solid #d8dee8",
              color: "#111827",
              fontWeight: 600,
              cursor: isAnalyzing ? "not-allowed" : "pointer",
              boxShadow: "0 8px 20px rgba(15, 23, 42, 0.06)",
            }}
          >
            Browse files
          </label>
        </div>
      </div>

      {selectedFiles.length > 0 && (
        <div style={{ marginTop: "1.25rem" }}>
          <div className="flex items-center justify-between" style={{ marginBottom: "0.75rem" }}>
            <p className="text-sm" style={{ color: "#475569" }}>
              {selectedFiles.length} {selectedFiles.length === 1 ? "file" : "files"} selected
            </p>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedFiles([])}
              style={{ color: "#475569" }}
            >
              Clear all
            </Button>
          </div>

          <div className="space-y-2 max-h-48 overflow-y-auto">
            {selectedFiles.map((file, index) => (
              <div
                key={`${file.name}-${index}`}
                className="flex items-center gap-3"
                style={{
                  padding: "0.75rem",
                  backgroundColor: "#ffffff",
                  border: "1px solid #e5e7eb",
                  borderRadius: "8px",
                }}
              >
                <div
                  className="flex items-center justify-center flex-shrink-0"
                  style={{
                    width: "2.5rem",
                    height: "2.5rem",
                    borderRadius: "8px",
                    backgroundColor: "#ecfdf5",
                    color: "#047857",
                  }}
                >
                  <ImageIcon className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-900 truncate">{file.name}</p>
                  <p className="text-xs" style={{ color: "#64748b" }}>
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeFile(index)}
                  disabled={isAnalyzing}
                >
                  <X className="w-4 h-4 text-gray-400" />
                </Button>
              </div>
            ))}
          </div>

          <Button
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            className="w-full"
            size="lg"
            style={{
              marginTop: "1rem",
              backgroundColor: "#111827",
              color: "#ffffff",
              borderRadius: "8px",
            }}
          >
            <FileCheck className="w-4 h-4" />
            {isAnalyzing ? "Analyzing..." : "Analyze image"}
          </Button>
        </div>
      )}
    </div>
  );
}
