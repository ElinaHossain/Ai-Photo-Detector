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

function getForensicArtifactMaps(result: AnalysisResult) {
  return (result.forensic_tests ?? [])
    .map((test) => {
      const url = getArtifactMapUrl(test.details || {});
      return url ? { title: `${test.test_name} Map`, url } : null;
    })
    .filter((entry): entry is { title: string; url: string } => entry !== null);
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

  const resultText = result.isAIGenerated ? "AI Generated" : "Low AI Signal";
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

  if (result.modelEvidence) {
    yPosition = sectionTitle(pdf, "Model Evidence", yPosition);
    pdf.setFontSize(10);
    pdf.setTextColor(75, 85, 99);
    pdf.text(`Provider: ${result.modelEvidence.provider ?? "Unknown"}`, PAGE_MARGIN, yPosition);
    yPosition += 7;
    pdf.text(`Raw AI Probability: ${result.modelEvidence.rawAiProbability.toFixed(1)}%`, PAGE_MARGIN, yPosition);
    yPosition += 7;
    pdf.text(`Provider Verdict: ${result.modelEvidence.providerVerdict ?? "Not supplied"}`, PAGE_MARGIN, yPosition);
    yPosition += 7;
    pdf.text(`Threshold: ${result.modelEvidence.threshold.toFixed(1)}%`, PAGE_MARGIN, yPosition);
    yPosition += 7;
    pdf.text(`Fallback Used: ${result.modelEvidence.usedFallback ? "Yes" : "No"}`, PAGE_MARGIN, yPosition);
    yPosition += 9;
    yPosition = writeWrappedText(
      pdf,
      result.modelEvidence.explanation,
      PAGE_MARGIN,
      yPosition,
      pageWidth - PAGE_MARGIN * 2,
      5
    ) + 5;
  }

  if (result.reliability) {
    yPosition = sectionTitle(pdf, "Result Reliability", yPosition);
    pdf.setFontSize(10);
    pdf.setTextColor(75, 85, 99);
    pdf.text(`${result.reliability.label}: ${result.reliability.score.toFixed(1)}%`, PAGE_MARGIN, yPosition);
    yPosition += 8;
    yPosition = writeWrappedText(
      pdf,
      result.reliability.explanation,
      PAGE_MARGIN,
      yPosition,
      pageWidth - PAGE_MARGIN * 2,
      5
    ) + 4;
    result.reliability.factors.slice(0, 4).forEach((factor) => {
      yPosition = ensureSpace(pdf, yPosition, 8);
      pdf.text(`- ${factor}`, PAGE_MARGIN, yPosition);
      yPosition += 6;
    });
    yPosition += 5;
  }

  if (result.robustness) {
    yPosition = sectionTitle(pdf, "Robustness / Stability Check", yPosition);
    pdf.setFontSize(10);
    pdf.setTextColor(75, 85, 99);
    pdf.text(`Status: ${result.robustness.label}`, PAGE_MARGIN, yPosition);
    yPosition += 7;
    pdf.text(`Consistency Index: ${(result.robustness.score * 100).toFixed(0)}/100`, PAGE_MARGIN, yPosition);
    yPosition += 7;
    if (typeof result.robustness.spread === "number") {
      pdf.text(`Raw AI Score Spread: ${result.robustness.spread.toFixed(1)}%`, PAGE_MARGIN, yPosition);
      yPosition += 7;
    }
    yPosition = writeWrappedText(
      pdf,
      result.robustness.explanation,
      PAGE_MARGIN,
      yPosition,
      pageWidth - PAGE_MARGIN * 2,
      5
    ) + 5;
  }

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

  const forensicArtifactMaps = getForensicArtifactMaps(result);
  forensicArtifactMaps.forEach((artifactMap) => {
    yPosition = addDataUrlImage(
      pdf,
      artifactMap.title,
      artifactMap.url,
      yPosition,
      pageWidth
    );
  });

  const hasElaForensicMap = forensicArtifactMaps.some((artifactMap) => {
    const title = artifactMap.title.toLowerCase();
    return title.includes("error level") || title.includes("ela");
  });
  const elaHeatmapUrl = result.ela?.heatmap?.url;
  if (elaHeatmapUrl && !hasElaForensicMap) {
    yPosition = addDataUrlImage(pdf, "ELA Heatmap", elaHeatmapUrl, yPosition, pageWidth);
  }

  yPosition = sectionTitle(pdf, "Analysis Summary", yPosition);
  pdf.setFontSize(10);
  pdf.setTextColor(75, 85, 99);
  const summaryText = result.isAIGenerated
    ? "The model score and supporting evidence checks suggest this image is likely AI-generated. Forensic maps highlight edit, clone, compression, or noise evidence when available. These results are assistive signals, not proof on their own."
    : "The model did not strongly flag this image as AI-generated. Clean forensic checks do not prove camera origin, and AI generation is still possible when metadata or watermarks are absent.";
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
