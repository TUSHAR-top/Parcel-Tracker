# Parcel Label Extractor

A robust, production-quality parcel label text extraction and scanner status classification system featuring a dual-stage processing pipeline: Multimodal AI (Ollama + LLaVA) with a fallback to Local OCR (EasyOCR + regex patterns).

## Features
- **Dual-Stage Pipeline**: Uses LLaVA via Ollama for multi-modal extraction, falling back automatically to EasyOCR and regex-based layout parsing.
- **Advanced OCR Parsing**: Includes tracking number validation (UPS, FedEx, USPS, DHL), weight/dimension detection, carrier categorization, and 180° rotation retry when labels are upside down.
- **Production FastAPI Backend**: Async file handling, 20 MB size limit, threat-safe in-memory background worker, HTML sanitization, and UUID safety.
- **Test Image Generator**: Generates 18 mock parcel scanner images for clean, blurred, blocked, empty, or multiple parcel scenarios.

---

## Directory Structure
```
parcel-tracker/
├── main.py                    # FastAPI application server
├── processor.py               # Dual-stage AI pipeline
├── generate_test_data.py      # Pillow-based test JPEG generator
├── requirements.txt           # Python dependencies
├── README.md                  # System manual
├── static/                    # Frontend assets (Single-Page App)
│   ├── index.html
│   ├── style.css
│   └── app.js
└── uploads/                   # Temporary upload cache (auto-created)
```

---

## Getting Started

### 1. Installation
Install the required packages from the requirements file:
```bash
pip install -r requirements.txt
```

### 2. Run Ollama (Primary Pipeline)
To use the high-quality LLaVA extraction, make sure Ollama is installed locally and run:
```bash
# Start Ollama service on your local system
ollama serve

# Pull the required multimodal LLaVA model
ollama pull llava
```

### 3. Run EasyOCR Fallback (Secondary Pipeline)
If Ollama is not running, the pipeline gracefully falls back to EasyOCR. 
*Note: EasyOCR requires `PyTorch`. If `pip install easyocr` doesn't automatically configure your CPU/GPU runtime, install torch first:*
```bash
pip install torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu
```

### 4. Running the FastAPI Server
To boot up the application backend and serve the static files:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 3000
```
Open your web browser and navigate to `http://localhost:3000` to interact with the GUI.

---

## Environment Variables
The application reads these variables from your environment.
- `OLLAMA_URL`: URL to your Ollama API instance (Defaults to `http://localhost:11434`).
- `OLLAMA_MODEL`: Multimodal model to call (Defaults to `llava`).

To run with custom values:
```bash
export OLLAMA_URL=http://localhost:11434
export OLLAMA_MODEL=llava
uvicorn main:app --reload
```

---

## API Reference

### 1. Upload Parcel Image
- **Endpoint**: `POST /api/upload`
- **Payload**: Form-Data (`file` containing JPEG, JPG, or PNG image)
- **Response**:
  ```json
  {
    "job_id": "80fb8e49-0cf5-4e78-9ef4-d3ecbc87ec49",
    "status": "pending",
    "progress": 0
  }
  ```

### 2. Poll Job Status
- **Endpoint**: `GET /api/job/{job_id}`
- **Response**:
  ```json
  {
    "job_id": "80fb8e49-0cf5-4e78-9ef4-d3ecbc87ec49",
    "status": "completed",
    "progress": 100,
    "filename": "package.jpg",
    "result": {
      "tracking_number": "1Z999AA10123456784",
      "carrier": "UPS",
      "weight": "12.5 LBS",
      "dimensions": "12x8x6",
      "sender": "AMAZON DISTRIB",
      "recipient": "HELEN SMITH",
      "confidence": 0.95,
      "status": "OK"
    }
  }
  ```

### 3. Download Job CSV
- **Endpoint**: `GET /api/job/{job_id}/download`
- **Output**: File download (`parcel_job_{job_id}.csv`)

### 4. Service Health Check
- **Endpoint**: `GET /api/health`
- **Response**:
  ```json
  {
    "status": "healthy",
    "service": "Parcel Label Extractor"
  }
  ```

---

## Generating Test Data
To generate the 18 synthetic images representing multiple parcel scanner states and view their manifest:
```bash
python generate_test_data.py
```
This creates a folder named `test_images/` containing JPEGs representing clean, blurred, blocked, empty, or multiple parcel scenarios, along with a `manifest.json`.

---

## Scanner Status Definitions
- `OK`: A parcel label was found and successfully read.
- `NO_PARCEL`: The conveyor belt is empty or there are no packages visible.
- `MULTIPLE_PARCELS`: More than one package is visible in the scanner viewport.
- `PARTIAL_PARCEL`: The parcel is cropped, shifted, or cut off.
- `LABEL_BLOCKED`: The parcel label is covered by straps, hands, marker marks, or tape.
- `LABEL_UNREADABLE`: The label is low resolution, crumpled, torn, or highly out-of-focus.
- `NO_LABEL`: The package is visible, but there is no label attached.
- `LOW_CONFIDENCE`: A label was found, but the scanning confidence falls below acceptable levels.
