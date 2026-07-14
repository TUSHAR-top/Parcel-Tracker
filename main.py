import os
import re
import uuid
import csv
import io
import shutil
import logging
import threading
from typing import Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import processor
try:
    from processor import process_image
except ImportError:
    from .processor import process_image

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("parcel_api")

app = FastAPI(title="Parcel Label Extractor API")

# Enable CORS for convenience
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# Thread-safe job store
job_store_lock = threading.Lock()
job_store: Dict[str, Dict[str, Any]] = {}

# Constants
MAX_FILE_SIZE = 20 * 1024 * 1024 # 20 MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

class JobResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    result: Any = None

def escape_html(text: str) -> str:
    """Escape HTML tags to protect against XSS."""
    if not text or not isinstance(text, str):
        return text
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#x27;")

def process_job_task(job_id: str, file_path: str):
    """Background task to run image processing and update job store."""
    try:
        logger.info(f"Starting background job: {job_id} on {file_path}")
        
        # Phase 1: Reading file (20% progress)
        with job_store_lock:
            job_store[job_id]["progress"] = 20
            job_store[job_id]["status"] = "processing"

        # Phase 2: Running extraction (60% progress)
        raw_result = process_image(file_path)

        with job_store_lock:
            job_store[job_id]["progress"] = 80

        # Escape HTML fields in result to prevent XSS
        cleaned_result = {}
        for key, val in raw_result.items():
            if isinstance(val, str):
                cleaned_result[key] = escape_html(val)
            else:
                cleaned_result[key] = val

        # Phase 3: Done (100% progress)
        with job_store_lock:
            job_store[job_id]["progress"] = 100
            job_store[job_id]["status"] = "completed"
            job_store[job_id]["result"] = cleaned_result
            
        logger.info(f"Completed background job: {job_id}")

    except Exception as e:
        logger.error(f"Error processing job {job_id}: {e}")
        with job_store_lock:
            job_store[job_id]["status"] = "failed"
            job_store[job_id]["progress"] = 100
            job_store[job_id]["result"] = {
                "status": "LABEL_UNREADABLE",
                "tracking_number": None,
                "carrier": "UNKNOWN",
                "weight": None,
                "dimensions": None,
                "sender": "UNKNOWN SENDER",
                "recipient": "UNKNOWN RECIPIENT",
                "confidence": 0.0,
                "error": f"Internal process error: {str(e)}"
            }
    finally:
        # Cleanup file after processing
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up temporary file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete temporary file {file_path}: {e}")

@app.get("/api/health")
def get_health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Parcel Label Extractor"}

from typing import List, Optional

@app.post("/api/upload")
async def upload_images(
    background_tasks: BackgroundTasks, 
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None)
):
    """Uploads single or multiple parcel images, validates them, and triggers background extraction jobs."""
    # Collect all uploaded files
    uploaded_files = []
    if file:
        uploaded_files.append(file)
    if files:
        uploaded_files.extend(files)

    if not uploaded_files:
        raise HTTPException(status_code=400, detail="No files uploaded. Please attach at least one JPG, JPEG, or PNG image.")

    created_jobs = []

    for f in uploaded_files:
        filename = f.filename
        _, ext = os.path.splitext(filename.lower())
        if ext not in ALLOWED_EXTENSIONS:
            if len(uploaded_files) == 1:
                raise HTTPException(status_code=400, detail="Unsupported file format. Please upload JPG, JPEG, or PNG.")
            continue

        job_id = str(uuid.uuid4())
        temp_filename = f"{job_id}{ext}"
        dest_path = os.path.join(UPLOAD_DIR, temp_filename)

        if os.path.basename(dest_path) != temp_filename:
            continue

        size = 0
        try:
            with open(dest_path, "wb") as buffer:
                while chunk := await f.read(1024 * 1024):  # 1MB chunks
                    size += len(chunk)
                    if size > MAX_FILE_SIZE:
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        raise HTTPException(status_code=413, detail=f"File '{filename}' too large. Max allowed size is 20 MB.")
                    buffer.write(chunk)
        except HTTPException:
            raise
        except Exception as e:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            continue

        # Initialize job store entry
        with job_store_lock:
            job_store[job_id] = {
                "job_id": job_id,
                "status": "pending",
                "progress": 0,
                "filename": escape_html(filename),
                "result": None
            }

        # Register background extraction task
        background_tasks.add_task(process_job_task, job_id, dest_path)
        
        created_jobs.append({
            "job_id": job_id, 
            "status": "pending", 
            "progress": 0,
            "filename": filename
        })

    if not created_jobs:
        raise HTTPException(status_code=400, detail="No valid image files were processed.")

    return {"jobs": created_jobs}

@app.get("/api/job/{job_id}")
def get_job(job_id: str):
    """Retrieve job processing status, progress, and results."""
    # Prevent path traversal on job ID
    if not re.match(r"^[a-f0-9\-]{36}$", job_id):
        raise HTTPException(status_code=400, detail="Invalid Job ID format.")

    with job_store_lock:
        if job_id not in job_store:
            raise HTTPException(status_code=404, detail="Job not found.")
        return job_store[job_id]

@app.get("/api/job/{job_id}/download")
def download_job_csv(job_id: str):
    """Download single job results as a standard CSV format without Job ID."""
    # Prevent path traversal on job ID
    if not re.match(r"^[a-f0-9\-]{36}$", job_id):
        raise HTTPException(status_code=400, detail="Invalid Job ID format.")

    with job_store_lock:
        if job_id not in job_store:
            raise HTTPException(status_code=404, detail="Job not found.")
        job = job_store[job_id]

    if job["status"] != "completed" or not job["result"]:
        raise HTTPException(status_code=400, detail="Job is not completed yet.")

    res = job["result"]
    
    # Generate CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers (No Job ID!)
    writer.writerow(["Original Filename", "Status", "Carrier", "Tracking Number", "Weight", "Dimensions"])
    
    # Row (No Job ID!)
    writer.writerow([
        job.get("filename", "unknown"),
        res.get("status", ""),
        res.get("carrier", ""),
        res.get("tracking_number", ""),
        res.get("weight", ""),
        res.get("dimensions", "")
    ])
    
    output.seek(0)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=parcel_job_{job_id}.csv"}
    )

@app.get("/api/batch/download")
def download_batch_csv():
    """Download all completed job results in a single batch CSV format."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers (No Job ID!)
    writer.writerow(["Original Filename", "Status", "Carrier", "Tracking Number", "Weight", "Dimensions"])
    
    with job_store_lock:
        completed_jobs = [job for job in job_store.values() if job["status"] == "completed" and job.get("result")]
        
    for job in completed_jobs:
        res = job["result"]
        
        writer.writerow([
            job.get("filename", "unknown"),
            res.get("status", ""),
            res.get("carrier", ""),
            res.get("tracking_number", ""),
            res.get("weight", ""),
            res.get("dimensions", "")
        ])
        
    output.seek(0)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=parcel_batch_report.csv"}
    )

# Serve static directory for index.html/app.js/style.css
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
