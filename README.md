# AI Photo Detector

A web app prototype for analyzing uploaded images and estimating whether they are AI-generated.

> **Current status:** Frontend is implemented and runnable. Backend API contract and initial FastAPI service foundation are now defined.

## Features

- Drag-and-drop image upload with multi-file selection UI.
- Simulated image analysis flow with loading state.
- Result dashboard showing:
  - AI/real classification badge
  - confidence score
  - per-indicator status (pass/warning/fail)
- PDF export of a detection report.
- "How to Use" guide tab in the app.
- Backend FastAPI scaffold with `/api/detect` and health endpoints.

## Tech Stack

- **Frontend:** React + TypeScript + Vite
- **Backend:** FastAPI + Uvicorn
- **UI:** Radix UI primitives + custom styled components
- **Icons:** Lucide React
- **PDF generation:** jsPDF

## Backend API Contract

### Endpoint

- `POST /api/detect`
- `Content-Type: multipart/form-data`
- Upload field name: `file`

### Request Expectations

- Exactly one uploaded image file.
- Accepted MIME types:
  - `image/jpeg`
  - `image/png`
  - `image/webp`
- Max file size: `10 MB` (`10 * 1024 * 1024` bytes).

### Success Response Schema (`200`)

```json
{
  "isAIGenerated": true,
  "confidence": 84.62,
  "indicators": [
    {
      "label": "Pixel Consistency",
      "value": 88.39,
      "status": "pass"
    }
  ],
  "metadata": {
    "requestId": "66c9e8b5-c6f8-434d-b95f-22eb8b21a6a9",
    "fileName": "portrait.png",
    "fileSize": 245103,
    "mimeType": "image/png"
  }
}
```

- `isAIGenerated: boolean`
- `confidence: number` (0-100)
- `indicators: Array<{ label: string; value: number; status: "pass" | "warning" | "fail" }>`
- `metadata?: { requestId, fileName, fileSize, mimeType }`

### Error Response Schema (`4xx/5xx`)

```json
{
  "error_code": "UNSUPPORTED_MEDIA_TYPE",
  "message": "Unsupported file type.",
  "details": {
    "requestId": "ec9124bc-8784-49f1-b2db-fb10861f6f3d",
    "mimeType": "image/gif",
    "acceptedMimeTypes": ["image/jpeg", "image/png", "image/webp"]
  }
}
```

- `error_code: string`
- `message: string`
- `details?: object`

### Frontend Alignment

The response field names intentionally align with `frontend/src/App.tsx` `AnalysisResult` mapping:

- `isAIGenerated`
- `confidence`
- `indicators[].label`
- `indicators[].value`
- `indicators[].status`

Backend also returns optional `metadata` to support request tracing.

## Getting Started

### Prerequisites

- Node.js 18+
- npm 9+
- Python 3.11+

### Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

### Run the Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Health checks:

- `GET /health`
- `GET /api/health`

## Project Structure

```text
.
|-- frontend/        # Runnable web UI
|-- backend/         # FastAPI service and detector pipeline stubs
|-- model/           # Model config/artifacts scaffold
|-- scripts/         # Utility scripts
`-- tests/           # Test scaffold
```

## Notes

- Detector scoring currently uses a deterministic placeholder pipeline (`preprocess -> predict -> postprocess`) until model inference is integrated.
- API contract is documented to unblock frontend/backend integration before full model implementation.

## License

This project is licensed under the terms in [`LICENSE`](./LICENSE).
