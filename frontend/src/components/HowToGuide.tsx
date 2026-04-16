import { CheckCircle, Download, FileText, Upload } from "lucide-react";

const panelStyle = {
  backgroundColor: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: "8px",
  boxShadow: "0 18px 48px rgba(15, 23, 42, 0.06)",
  padding: "1.5rem",
};

export function HowToGuide() {
  const steps = [
    {
      icon: Upload,
      title: "Upload an image",
      description:
        "Choose a JPG, PNG, or WEBP image and start the forensic scan.",
      tips: [
        "Use clear source images when possible",
        "Keep files under 10 MB",
        "JPEG files provide the strongest compression evidence",
      ],
    },
    {
      icon: CheckCircle,
      title: "Run analysis",
      description:
        "The app checks AI confidence, pixel signals, JPEG artifacts, and ELA evidence.",
      tips: [
        "Scores are strongest when multiple signals agree",
        "Non-JPEG images may have limited compression evidence",
        "Heatmaps highlight regions worth reviewing",
      ],
    },
    {
      icon: FileText,
      title: "Review results",
      description:
        "Use the dashboard to compare model confidence with forensic evidence.",
      tips: [
        "Review the overall confidence first",
        "Check suspicious or inconclusive forensic cards",
        "Use the ELA map for localized visual evidence",
      ],
    },
    {
      icon: Download,
      title: "Export report",
      description:
        "Save a PDF copy of the result for documentation or team review.",
      tips: [
        "Reports include confidence and forensic indicators",
        "Evidence maps are included when available",
        "Use exports for comparison across samples",
      ],
    },
  ];

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <section style={panelStyle}>
        <p
          style={{
            color: "#111827",
            fontSize: "1.5rem",
            fontWeight: 700,
            lineHeight: 1.2,
            marginBottom: "0.5rem",
          }}
        >
          How to use the detector
        </p>
        <p style={{ color: "#64748b" }}>
          A simple workflow for checking whether an image may be generated or edited.
        </p>
      </section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: "1rem",
        }}
      >
        {steps.map((step, index) => {
          const Icon = step.icon;
          return (
            <article key={step.title} style={panelStyle}>
              <div
                className="flex items-center justify-between"
                style={{ marginBottom: "1rem" }}
              >
                <div
                  className="flex items-center justify-center"
                  style={{
                    width: "2.75rem",
                    height: "2.75rem",
                    borderRadius: "8px",
                    backgroundColor: "#111827",
                    color: "#ffffff",
                  }}
                >
                  <Icon className="w-5 h-5" />
                </div>
                <span className="text-sm" style={{ color: "#64748b" }}>
                  Step {index + 1}
                </span>
              </div>

              <h3 style={{ color: "#111827", fontWeight: 700 }}>
                {step.title}
              </h3>
              <p className="text-sm" style={{ color: "#64748b", marginTop: "0.5rem" }}>
                {step.description}
              </p>

              <div
                style={{
                  display: "grid",
                  gap: "0.5rem",
                  marginTop: "1rem",
                  paddingTop: "1rem",
                  borderTop: "1px solid #eef2f7",
                }}
              >
                {step.tips.map((tip) => (
                  <div
                    key={tip}
                    className="flex items-start gap-2"
                    style={{ color: "#475569" }}
                  >
                    <span
                      style={{
                        width: "0.375rem",
                        height: "0.375rem",
                        borderRadius: "999px",
                        backgroundColor: "#10b981",
                        marginTop: "0.55rem",
                        flexShrink: 0,
                      }}
                    />
                    <span className="text-sm">{tip}</span>
                  </div>
                ))}
              </div>
            </article>
          );
        })}
      </section>

      <section
        style={{
          ...panelStyle,
          backgroundColor: "#111827",
          borderColor: "#111827",
        }}
      >
        <h3 style={{ color: "#ffffff", fontWeight: 700 }}>
          Reading the output
        </h3>
        <p className="text-sm" style={{ color: "#cbd5e1", marginTop: "0.5rem" }}>
          Treat the score as a confidence signal, then use forensic cards and heatmaps
          to understand where the evidence is coming from.
        </p>
      </section>
    </div>
  );
}
