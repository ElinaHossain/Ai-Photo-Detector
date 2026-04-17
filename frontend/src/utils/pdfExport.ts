import { jsPDF } from "jspdf";
import { AnalysisResult } from "../App";

type PdfColor = [number, number, number];
type DetailRecord = Record<string, unknown>;

const PAGE_MARGIN = 20;
const LINE_HEIGHT = 6;

function ensureSpace(pdf: jsPDF, yPosition: number, requiredHeight: number) {
  const pageHeight = pdf.internal.pageSize.getHeight();
  if (yPosition + requiredHeight <= pageHeight - PAGE_MARGIN) {
    return yPosition;
  }

  pdf.addPage();
  return PAGE_MARGIN;
}

function writeWrappedText(
  pdf: jsPDF,
  text: string,
  x: number,
  yPosition: number,
  maxWidth: number,
  lineHeight = LINE_HEIGHT
) {
  const lines = pdf.splitTextToSize(text, maxWidth) as string[];
  pdf.text(lines, x, yPosition);
  return yPosition + lines.length * lineHeight;
}

function sectionTitle(pdf: jsPDF, title: string, yPosition: number) {
  yPosition = ensureSpace(pdf, yPosition, 18);
  pdf.setFontSize(14);
  pdf.setTextColor(31, 41, 55);
  pdf.text(title, PAGE_MARGIN, yPosition);
  return yPosition + 10;
}

function getDetailRecord(value: unknown): DetailRecord | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as DetailRecord)
    : null;
}

function getArtifactMapUrl(details: DetailRecord) {
  const artifactMap = getDetailRecord(details.artifact_map);
  return typeof artifactMap?.url === "string" ? artifactMap.url : null;
}

function getCompressionArtifactTest(result: AnalysisResult) {
  return result.forensic_tests?.find((test) => {
    const name = test.test_name.toLowerCase();
    return name.includes("compression") && name.includes("artifact");
  });
}

function imageFormatFromDataUrl(dataUrl: string) {
  if (dataUrl.startsWith("data:image/jpeg") || dataUrl.startsWith("data:image/jpg")) {
    return "JPEG";
  }
  return "PNG";
}

function addDataUrlImage(
  pdf: jsPDF,
  title: string,
  dataUrl: string,
  yPosition: number,
  pageWidth: number
) {
  if (!dataUrl.startsWith("data:image/")) {
    return yPosition;
  }

  yPosition = sectionTitle(pdf, title, yPosition);

  const maxWidth = pageWidth - PAGE_MARGIN * 2;
  const maxHeight = 105;

  try {
    const imageProperties = pdf.getImageProperties(dataUrl);
    const aspectRatio = imageProperties.width / imageProperties.height || 1;
    let imageWidth = maxWidth;
    let imageHeight = imageWidth / aspectRatio;

    if (imageHeight > maxHeight) {
      imageHeight = maxHeight;
      imageWidth = imageHeight * aspectRatio;
    }

    yPosition = ensureSpace(pdf, yPosition, imageHeight + 10);
    pdf.addImage(
      dataUrl,
      imageFormatFromDataUrl(dataUrl),
      PAGE_MARGIN,
      yPosition,
      imageWidth,
      imageHeight
    );
    return yPosition + imageHeight + 12;
  } catch {
    pdf.setFontSize(10);
    pdf.setTextColor(75, 85, 99);
    return writeWrappedText(
      pdf,
      `${title} could not be embedded in this PDF export.`,
      PAGE_MARGIN,
      yPosition,
      maxWidth
    ) + 6;
  }
}

function addFooter(pdf: jsPDF) {
  const pageCount = pdf.getNumberOfPages();
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();

  for (let page = 1; page <= pageCount; page += 1) {
    pdf.setPage(page);
    pdf.setFontSize(8);
    pdf.setTextColor(156, 163, 175);
    pdf.text(
      `Generated on ${new Date().toLocaleString()} | AI Photo Detector | Page ${page} of ${pageCount}`,
      pageWidth / 2,
      pageHeight - 10,
      { align: "center" }
    );
  }
}

function safeFileBaseName(fileName: string) {
  return fileName.replace(/\.[^/.]+$/, "").replace(/[^\w-]+/g, "_") || "image";
}

export function exportToPDF(result: AnalysisResult) {
  const pdf = new jsPDF();
  const pageWidth = pdf.internal.pageSize.getWidth();
  let yPosition = PAGE_MARGIN;

  pdf.setFontSize(20);
  pdf.setTextColor(31, 41, 55);
  pdf.text("AI Photo Detection Report", PAGE_MARGIN, yPosition);

  yPosition += 12;
  pdf.setDrawColor(229, 231, 235);
  pdf.setLineWidth(0.5);
  pdf.line(PAGE_MARGIN, yPosition, pageWidth - PAGE_MARGIN, yPosition);
  yPosition += 14;

  yPosition = sectionTitle(pdf, "File Information", yPosition);
  pdf.setFontSize(10);
  pdf.setTextColor(75, 85, 99);
  pdf.text(`File Name: ${result.fileName}`, PAGE_MARGIN, yPosition);
  yPosition += 7;
  pdf.text(`Upload Date: ${result.uploadDate.toLocaleString()}`, PAGE_MARGIN, yPosition);
  yPosition += 7;
  pdf.text(`File Size: ${(result.fileSize / 1024 / 1024).toFixed(2)} MB`, PAGE_MARGIN, yPosition);
  yPosition += 7;
  pdf.text(`Format: ${result.fileName.split(".").pop()?.toUpperCase() ?? "UNKNOWN"}`, PAGE_MARGIN, yPosition);
  yPosition += 14;

  yPosition = sectionTitle(pdf, "Detection Result", yPosition);

  const resultText = result.isAIGenerated ? "AI Generated" : "Real Photo";
  const resultColor: PdfColor = result.isAIGenerated ? [220, 38, 38] : [22, 163, 74];

  pdf.setFillColor(...resultColor);
  pdf.setTextColor(255, 255, 255);
  pdf.setFontSize(12);
  pdf.rect(PAGE_MARGIN, yPosition - 5, 64, 10, "F");
  pdf.text(resultText, PAGE_MARGIN + 32, yPosition + 2, { align: "center" });
  yPosition += 15;

  pdf.setFontSize(10);
  pdf.setTextColor(75, 85, 99);
  pdf.text(`Model Confidence: ${result.confidence.toFixed(1)}%`, PAGE_MARGIN, yPosition);
  yPosition += 10;

  const barWidth = 100;
  const barHeight = 6;
  pdf.setFillColor(229, 231, 235);
  pdf.rect(PAGE_MARGIN, yPosition - 3, barWidth, barHeight, "F");
  pdf.setFillColor(59, 130, 246);
  pdf.rect(PAGE_MARGIN, yPosition - 3, (barWidth * result.confidence) / 100, barHeight, "F");
  yPosition += 15;

  if (result.forensic_tests?.length) {
    yPosition = sectionTitle(pdf, "Forensic Evidence", yPosition);

    result.forensic_tests.forEach((test) => {
      yPosition = ensureSpace(pdf, yPosition, 30);
      const details = test.details || {};
      const explanation =
        typeof details.explanation === "string" ? details.explanation : null;

      pdf.setFontSize(11);
      pdf.setTextColor(31, 41, 55);
      pdf.text(test.test_name, PAGE_MARGIN, yPosition);

      pdf.setFontSize(10);
      pdf.setTextColor(75, 85, 99);
      pdf.text(
        `Verdict: ${test.verdict} | Signal: ${(test.score * 100).toFixed(1)}% | Test confidence: ${(test.confidence * 100).toFixed(1)}%`,
        PAGE_MARGIN,
        yPosition + 7
      );
      yPosition += 14;

      if (explanation) {
        yPosition = writeWrappedText(
          pdf,
          explanation,
          PAGE_MARGIN,
          yPosition,
          pageWidth - PAGE_MARGIN * 2,
          5
        ) + 5;
      }
    });
  }

  const compressionTest = getCompressionArtifactTest(result);
  const compressionDetails = compressionTest?.details || {};
  const compressionArtifactMapUrl = getArtifactMapUrl(compressionDetails);
  if (compressionArtifactMapUrl) {
    yPosition = addDataUrlImage(
      pdf,
      "Compression Artifact Map",
      compressionArtifactMapUrl,
      yPosition,
      pageWidth
    );
  }

  const elaHeatmapUrl = result.ela?.heatmap?.url;
  if (elaHeatmapUrl) {
    yPosition = addDataUrlImage(pdf, "ELA Heatmap", elaHeatmapUrl, yPosition, pageWidth);
  }

  yPosition = sectionTitle(pdf, "Analysis Summary", yPosition);
  pdf.setFontSize(10);
  pdf.setTextColor(75, 85, 99);
  const summaryText = `The model score and local forensic checks suggest this image is ${result.isAIGenerated ? "likely AI-generated" : "likely real"}. Forensic maps highlight compression or recompression evidence when available. These results are assistive signals, not proof on their own.`;
  yPosition = writeWrappedText(
    pdf,
    summaryText,
    PAGE_MARGIN,
    yPosition,
    pageWidth - PAGE_MARGIN * 2
  );

  addFooter(pdf);
  pdf.save(`AI_Detection_Report_${safeFileBaseName(result.fileName)}.pdf`);
}
