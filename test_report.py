import json
import uuid

from backend.detector.evidence_summary import generate_user_summary
from backend.detector.preprocess import preprocess_image
from backend.detector.predict import predict_scores
from backend.detector.evidence_summary import generate_final_report
from backend.detector.report_builder import generate_official_analysis_report


def main() -> None:
    # INPUT IMAGE (CHANGE THIS DURING TESTING)
    image_path = "test_images/PASTA.webp"

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    mime_type = "image/webp"
    request_id = str(uuid.uuid4())

    # ============================================================
    # STEP 1: PREPROCESS + RUN ALL FORENSIC DETECTORS
    # ============================================================
    preprocess_output = preprocess_image(
        image_bytes=image_bytes,
        mime_type=mime_type,
        request_id=request_id,
        deterministic=True,
    )

    # ============================================================
    # STEP 2: RUN AI MODEL PREDICTION
    # ============================================================
    prediction = predict_scores(
        model_input=preprocess_output.model_input,
        metadata={
            **preprocess_output.metadata,
            "image_bytes": image_bytes,
            "mime_type": mime_type,
        },
        deterministic_seed=42,
        allow_fallback=True,
    )

    # ============================================================
    # STEP 3: COLLECT FORENSIC RESULTS
    # ============================================================
    forensic_tests = preprocess_output.metadata.get("forensic_tests", [])

    # ============================================================
    # STEP 4: BUILD FINAL SYSTEM REPORT (INTERNAL STRUCTURE)
    # ============================================================
    report = generate_final_report(prediction, forensic_tests)

    # ============================================================
    # STEP 5: BUILD OFFICIAL REPORT (FOR DOWNLOAD / PDF)
    # ============================================================
    # IMPORTANT FOR TEAM:
    # This is the FULL professional report.
    # This will be used later by frontend to:
    # - show a detailed report page OR
    # - generate a downloadable PDF
    # This is NOT for quick UI display.
    official_report = generate_official_analysis_report(image_path, report)

    # ============================================================
    # DEBUG OUTPUT: FORENSIC TEST RESULTS (FOR DEVELOPERS ONLY)
    # ============================================================
    # IMPORTANT:
    # This section is ONLY for backend/dev debugging.
    # It shows raw detector behavior.
    # DO NOT expose this directly to users.
    print("\n==============================")
    print("FORENSIC TEST RESULTS (DEV ONLY)")
    print("==============================")

    for test in report["forensic_results"]:
        print(f"\n--- {test['test_name']} ---")
        print(f"Verdict   : {test['verdict']}")
        print(f"Score     : {test['score']}")
        print(f"Confidence: {test['confidence']}")

        details = test.get("details", {})

        if "explanation" in details:
            print(f"Explanation: {details['explanation']}")

        if "metrics" in details:
            print("Metrics:")
            for k, v in details["metrics"].items():
                print(f"  - {k}: {v}")

    # ============================================================
    # OFFICIAL REPORT OUTPUT (PDF / DOWNLOAD VERSION)
    # ============================================================
    print("\n==============================")
    print("OFFICIAL ANALYSIS REPORT (FOR DOWNLOAD)")
    print("==============================")
    print(official_report)

    # ============================================================
    # FINAL USER RESPONSE (FRONTEND RESPONSE)
    # ============================================================
    # IMPORTANT FOR TEAM:
    # This is the response that frontend should display immediately
    # after user uploads an image.
    # This should be:
    # - fast
    # - simple
    # - user-friendly
    # This is NOT the full report.
    print("\n==============================")
    print("FINAL USER REPORT (UI RESPONSE)")
    print("==============================")

    user_view = generate_user_summary(report)
    print(json.dumps(user_view, indent=2))


if __name__ == "__main__":
    main()
