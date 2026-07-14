// Constants
const POLL_INTERVAL = 1500; // 1.5 seconds

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const progressContainer = document.getElementById('progress-container');
const progressFill = document.getElementById('progress-fill');
const progressLabel = document.getElementById('progress-label');
const progressPercentage = document.getElementById('progress-percentage');
const healthStatus = document.getElementById('health-status');
const tbody = document.getElementById('jobs-tbody');
const btnDownloadAll = document.getElementById('btn-download-all');

// Global job storage
let jobsMap = new Map();
let processedJobs = new Set();
let activePollers = new Map();

// Helpers
function escapeHtml(text) {
    if (!text) return '-';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;');
}

function getStatusBadgeClass(status) {
    switch (status) {
        case 'OK': return 'st-ok';
        case 'NO_PARCEL': return 'st-no_parcel';
        case 'MULTIPLE_PARCELS': return 'st-multiple_parcels';
        case 'PARTIAL_PARCEL': return 'st-partial_parcel';
        case 'LABEL_BLOCKED': return 'st-label_blocked';
        case 'LABEL_UNREADABLE': return 'st-label_unreadable';
        case 'NO_LABEL': return 'st-no_label';
        case 'LOW_CONFIDENCE': return 'st-low_confidence';
        default: return '';
    }
}

// Check backend health on start
async function checkHealth() {
    try {
        const res = await fetch('/api/health');
        if (res.ok) {
            healthStatus.innerHTML = '<span class="indicator" style="background-color: #10b981;"></span> API Connected';
        } else {
            healthStatus.innerHTML = '<span class="indicator" style="background-color: #ef4444;"></span> API Issue';
        }
    } catch {
        healthStatus.innerHTML = '<span class="indicator" style="background-color: #ef4444;"></span> API Disconnected';
    }
}

// Setup drag and drop
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        uploadFiles(Array.from(e.dataTransfer.files));
    }
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        uploadFiles(Array.from(fileInput.files));
    }
});

// Handle Multiple File Uploads in Batch
async function uploadFiles(files) {
    if (!files || files.length === 0) return;

    const allowedExtensions = ['.jpg', '.jpeg', '.png'];
    const validFiles = [];

    for (const file of files) {
        const fileExtension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
        if (!allowedExtensions.includes(fileExtension)) {
            alert(`Unsupported file format for '${file.name}'. Please upload only JPG, JPEG, or PNG.`);
            continue;
        }
        if (file.size > 20 * 1024 * 1024) { // 20MB
            alert(`File '${file.name}' is too large. Maximum size is 20MB.`);
            continue;
        }
        validFiles.push(file);
    }

    if (validFiles.length === 0) return;

    // Reset top progress bar view
    progressContainer.style.display = 'block';
    progressFill.style.width = '20%';
    progressPercentage.textContent = '20%';
    progressLabel.textContent = `Uploading ${validFiles.length} file(s) in batch...`;

    const formData = new FormData();
    validFiles.forEach(file => {
        formData.append('files', file);
    });

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Upload failed');
        }

        const data = await response.json();
        
        progressFill.style.width = '40%';
        progressPercentage.textContent = '40%';
        progressLabel.textContent = `Batch uploaded. Initializing AI scanners...`;

        if (data.jobs && data.jobs.length > 0) {
            // Instantly inject into scanning operations table as pending/processing
            data.jobs.forEach(jobMeta => {
                const initialJob = {
                    job_id: jobMeta.job_id,
                    filename: jobMeta.filename,
                    status: 'pending',
                    progress: 10,
                    result: null
                };
                
                jobsMap.set(jobMeta.job_id, initialJob);
                
                if (!processedJobs.has(jobMeta.job_id)) {
                    appendRowToLogTable(initialJob);
                    processedJobs.add(jobMeta.job_id);
                } else {
                    updateRowInTable(initialJob);
                }
                
                // Trigger background polling for this job
                startPolling(jobMeta.job_id);
            });
        }

    } catch (err) {
        alert(`Error uploading files: ${err.message}`);
        progressContainer.style.display = 'none';
    }
}

// Setup polling for specific job ID
function startPolling(jobId) {
    if (activePollers.has(jobId)) {
        clearInterval(activePollers.get(jobId));
        activePollers.delete(jobId);
    }

    pollJobStatus(jobId);
    const interval = setInterval(() => pollJobStatus(jobId), POLL_INTERVAL);
    activePollers.set(jobId, interval);
}

async function pollJobStatus(jobId) {
    try {
        const response = await fetch(`/api/job/${jobId}`);
        if (!response.ok) {
            if (activePollers.has(jobId)) {
                clearInterval(activePollers.get(jobId));
                activePollers.delete(jobId);
            }
            throw new Error('Could not fetch job status');
        }

        const job = await response.json();
        
        // Save to global job database
        jobsMap.set(jobId, job);

        // Update overall top header progress bar based on active items
        updateGlobalProgress();

        // Dynamically update the row in scanning table log to reflect progress
        updateRowInTable(job);

        // Terminate polling if job has completed or failed
        if (job.status === 'completed' || job.status === 'failed') {
            if (activePollers.has(jobId)) {
                clearInterval(activePollers.get(jobId));
                activePollers.delete(jobId);
            }
        }

        // Always show complete batch CSV download if we have completed items
        updateDownloadAllVisibility();

    } catch (err) {
        if (activePollers.has(jobId)) {
            clearInterval(activePollers.get(jobId));
            activePollers.delete(jobId);
        }
        console.error(err);
    }
}

// Update top global progress bar based on active items in memory
function updateGlobalProgress() {
    if (jobsMap.size === 0) {
        progressContainer.style.display = 'none';
        return;
    }

    const jobs = Array.from(jobsMap.values());
    const totalJobs = jobs.length;
    const completedJobs = jobs.filter(j => j.status === 'completed' || j.status === 'failed').length;
    
    // Sum progress of all jobs
    const sumProgress = jobs.reduce((acc, j) => acc + (j.progress || 0), 0);
    const avgProgress = Math.round(sumProgress / totalJobs);

    progressFill.style.width = `${avgProgress}%`;
    progressPercentage.textContent = `${avgProgress}%`;

    if (completedJobs === totalJobs) {
        progressLabel.textContent = `All ${totalJobs} scanning tasks completed successfully!`;
        setTimeout(() => {
            progressContainer.style.fadeOut = 'slow';
            setTimeout(() => { progressContainer.style.display = 'none'; }, 500);
        }, 3000);
    } else {
        progressLabel.textContent = `Processing batch: ${completedJobs}/${totalJobs} files completed...`;
    }
}

// Append new scanning operation to history log dynamically (Incremental)
function appendRowToLogTable(job) {
    const tr = document.createElement('tr');
    tr.id = `row-${job.job_id}`;
    tr.innerHTML = getRowHtml(job);

    // Prepend to show most recent first
    if (tbody.firstChild) {
        tbody.insertBefore(tr, tbody.firstChild);
    } else {
        tbody.appendChild(tr);
    }
}

function updateRowInTable(job) {
    const tr = document.getElementById(`row-${job.job_id}`);
    if (tr) {
        tr.innerHTML = getRowHtml(job);
    }
}

function getRowHtml(job) {
    const result = job.result || {};
    
    // If the job is pending or processing, show dynamic inline loaders!
    if (job.status === 'pending' || job.status === 'processing') {
        const pct = job.progress || 10;
        const statusLabel = job.status === 'pending' ? 'Queued' : `Scanning (${pct}%)`;
        const badgeClass = job.status === 'pending' ? 'st-badge st-pending animate-pulse' : 'st-badge st-processing animate-pulse';
        
        return `
            <td><strong>${escapeHtml(job.filename)}</strong></td>
            <td class="text-muted italic">Identifying...</td>
            <td class="text-muted italic font-mono text-xs">Extracting...</td>
            <td class="text-muted">-</td>
            <td class="text-muted">-</td>
            <td>
                <div style="display: flex; flex-direction: column; gap: 4px; width: 140px; margin-top: 4px;">
                    <span class="${badgeClass}" style="display: inline-flex; align-items: center; gap: 6px; background-color: rgba(59, 130, 246, 0.08); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.15); font-size: 11px;">
                        <span class="spinner-small"></span> ${statusLabel}
                    </span>
                    <div style="width: 100%; background: #e2e8f0; height: 5px; border-radius: 9999px; overflow: hidden;">
                        <div style="width: ${pct}%; background: #2563eb; height: 100%; transition: width 0.4s ease;"></div>
                    </div>
                </div>
            </td>
            <td style="text-align: right; padding-right: 1.5rem;">
                <span class="text-muted italic" style="font-size: 11px;">Loading AI...</span>
            </td>
        `;
    }

    // Finished Row (OK or Fail states)
    const trackingNum = result.tracking_number || 'N/A';
    const carrierName = result.carrier || 'UNKNOWN';
    const finalStatus = result.status || (job.status === 'failed' ? 'LABEL_UNREADABLE' : 'OK');

    return `
        <td><strong>${escapeHtml(job.filename)}</strong></td>
        <td>${escapeHtml(carrierName)}</td>
        <td class="font-mono text-xs font-bold text-blue-600">${escapeHtml(trackingNum)}</td>
        <td>${escapeHtml(result.weight || 'N/A')}</td>
        <td>${escapeHtml(result.dimensions || 'N/A')}</td>
        <td><span class="st-badge ${getStatusBadgeClass(finalStatus)}">${escapeHtml(finalStatus)}</span></td>
        <td style="text-align: right; padding-right: 1.5rem;">
            <a class="action-link" href="/api/job/${job.job_id}/download" style="font-weight: 600; text-decoration: none; padding: 4px 8px; background-color: rgba(37, 99, 235, 0.08); border-radius: 6px; font-size: 11px; display: inline-block;">Download CSV</a>
        </td>
    `;
}

// Show/hide and wire the Complete Batch CSV button
function updateDownloadAllVisibility() {
    if (jobsMap.size > 0 && btnDownloadAll) {
        btnDownloadAll.style.display = 'inline-flex';
    } else if (btnDownloadAll) {
        btnDownloadAll.style.display = 'none';
    }
}

// Client-side batch CSV generator
if (btnDownloadAll) {
    btnDownloadAll.onclick = () => {
        if (jobsMap.size === 0) {
            alert('No scanned items available for download yet.');
            return;
        }

        const headers = ["Original Filename", "Status", "Carrier", "Tracking Number", "Weight", "Dimensions"];
        const rows = [];

        for (const job of jobsMap.values()) {
            const res = job.result || {};
            rows.push([
                job.filename,
                res.status || job.status || "UNKNOWN",
                res.carrier || "UNKNOWN",
                res.tracking_number || "",
                res.weight || "",
                res.dimensions || ""
            ]);
        }

        const csvContent = [
            headers.join(","),
            ...rows.map(row => row.map(val => {
                const str = String(val === null || val === undefined ? "" : val).replace(/"/g, '""');
                return `"${str}"`;
            }).join(","))
        ].join("\n");

        const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        link.setAttribute("download", `parcel_batch_report_${new Date().toISOString().slice(0, 10)}.csv`);
        link.style.visibility = "hidden";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };
}

// Deep linking shared URL check on initialization
function handleSharedUrl() {
    const params = new URLSearchParams(window.location.search);
    const jobId = params.get('job_id');
    if (jobId) {
        const mockJob = {
            job_id: jobId,
            filename: 'Retrieved Scan',
            status: 'pending',
            progress: 10,
            result: null
        };
        jobsMap.set(jobId, mockJob);
        appendRowToLogTable(mockJob);
        processedJobs.add(jobId);
        startPolling(jobId);
    }
}

// Run initial configurations
checkHealth();
handleSharedUrl();
updateDownloadAllVisibility();
