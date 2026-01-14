import os
import sys
import uuid
import tempfile
import subprocess
import threading
import re
from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from typing import List
import shutil
import json

app = FastAPI(title="Local Docking Backend (Run Script Only)")

@app.post("/upload-run-files")
async def upload_run_files(
    ligands: List[UploadFile] = File(default=[]),
    receptors: List[UploadFile] = File(default=[])
):
    """
    Accepts ligand and receptor files (multiple). Saves them into a unique temp job folder:
      /tmp/vdock_upload_{job_id}/ligands/
      /tmp/vdock_upload_{job_id}/receptors/

    Returns job_id and backend directories (absolute paths).
    """
    if (not ligands) and (not receptors):
        raise HTTPException(status_code=400, detail="No files uploaded (ligands or receptors)")

    job_id = uuid.uuid4().hex[:10]
    job_dir = os.path.join(tempfile.gettempdir(), f"vdock_upload_{job_id}")
    lig_dir = os.path.join(job_dir, "ligands")
    rec_dir = os.path.join(job_dir, "receptors")
    os.makedirs(lig_dir, exist_ok=True)
    os.makedirs(rec_dir, exist_ok=True)

    try:
        # Save ligand files
        saved_ligands = []
        for f in ligands:
            # sanitize filename
            fname = os.path.basename(f.filename)
            target = os.path.join(lig_dir, fname)
            with open(target, "wb") as out:
                content = await f.read()
                out.write(content)
            saved_ligands.append(fname)

        # Save receptor files
        saved_receptors = []
        for f in receptors:
            fname = os.path.basename(f.filename)
            target = os.path.join(rec_dir, fname)
            with open(target, "wb") as out:
                content = await f.read()
                out.write(content)
            saved_receptors.append(fname)

    except Exception as e:
        # cleanup on failure
        try:
            shutil.rmtree(job_dir)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded files: {e}")

    return {
        "job_id": job_id,
        "job_dir": job_dir,
        "ligand_dir": lig_dir,
        "receptor_dir": rec_dir,
        "ligands": saved_ligands,
        "receptors": saved_receptors
    }


@app.delete("/cleanup/{job_id}")
def cleanup_job_upload(job_id: str):
    """
    Remove a previous upload job by job_id. This deletes /tmp/vdock_upload_{job_id}/
    """
    job_dir = os.path.join(tempfile.gettempdir(), f"vdock_upload_{job_id}")
    if not os.path.exists(job_dir):
        return {"status": "not_found", "detail": f"{job_dir} does not exist"}
    try:
        shutil.rmtree(job_dir)
        return {"status": "deleted", "job_dir": job_dir}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete job dir: {e}")



# Allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Job memory
JOBS = {}   # job_id -> dict(status, log, progress, etc)

# Installer jobs
INSTALL_JOBS = {}   # install_id -> dict(status, log)


# ============================================================
# CHECK IF EXECUTABLE EXISTS
# ============================================================
def has_exec(name):
    return subprocess.call(
        f"which {name}", shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    ) == 0


# ============================================================
# INSTALLATION BACKGROUND HANDLER
# ============================================================
def run_install(job_id, tool):
    job = INSTALL_JOBS[job_id]
    job["status"] = "running"

    cmds = {
        "vina": "sudo apt-get install -y autodock-vina",
        "openbabel": "sudo apt-get install -y openbabel",
        "mgltools": "sudo apt-get install -y mgltools"
    }

    if tool not in cmds:
        job["status"] = "failed"
        job["log"].append(f"Unknown tool: {tool}")
        return

    try:
        process = subprocess.Popen(
            cmds[tool],
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
    except Exception as e:
        job["log"].append(f"Install failed to start: {e}")
        job["status"] = "failed"
        return

    for line in iter(process.stdout.readline, ""):
        job["log"].append(line)
        if len(job["log"]) > 200:
            job["log"] = job["log"][-150:]

    process.wait()

    if process.returncode == 0:
        job["status"] = "done"
    else:
        job["status"] = "failed"


# ============================================================
# ADD: /check-dependencies
# ============================================================
@app.get("/check-dependencies")
def check_dependencies():
    checks = {
        "vina": has_exec("vina"),
        "openbabel": has_exec("obabel"),
        "mgltools": has_exec("prepare_receptor4.py"),
        "python": has_exec("python3"),
        "local_generator": True
    }
    return {"checks": checks}


# ============================================================
# ADD: /install-dependency
# ============================================================
@app.post("/install-dependency")
def install_dependency(name: str):
    install_id = uuid.uuid4().hex[:10]

    INSTALL_JOBS[install_id] = {
        "status": "starting",
        "log": []
    }

    threading.Thread(
        target=run_install,
        args=(install_id, name),
        daemon=True
    ).start()

    return {"install_id": install_id, "message": "Installation started"}


# ============================================================
# ADD: /install-status/{install_id}
# ============================================================
@app.get("/install-status/{install_id}")
def install_status(install_id: str):
    if install_id not in INSTALL_JOBS:
        raise HTTPException(status_code=404, detail="Installer job not found")

    job = INSTALL_JOBS[install_id]

    return {
        "install_id": install_id,
        "status": job["status"],
        "log_tail": job["log"][-40:]
    }


# ============================================================
# EXISTING CODE (UNCHANGED)
# STREAM SCRIPT OUTPUT + REAL-TIME PROGRESS ESTIMATION
# ============================================================
def stream_output(job_id, process):
    job = JOBS[job_id]
    job["status"] = "running"
    job["progress"] = 0
    job["completed_tasks"] = 0
    job["total_tasks"] = None

    try:
        for raw_line in iter(process.stdout.readline, ""):
            if not raw_line:
                break

            line = raw_line.rstrip()
            lower = line.lower()
            job["log"].append(line)

            # Limit memory footprint
            if len(job["log"]) > 1000:
                job["log"] = job["log"][-800:]

            # Detect total tasks
            if "total tasks in this chunk" in lower:
                try:
                    parts = line.split(":")
                    total = int(parts[1].strip())
                    job["total_tasks"] = total
                except:
                    pass

            # Vina grid computation
            if "computing vina grid" in lower:
                job["progress"] = max(job["progress"], 10)

            # Docking start
            if "performing docking" in lower:
                job["progress"] = max(job["progress"], 20)

            # Map explicit Vina % → global %
            match = re.search(r"(\d+)%", line)
            if match:
                vina_percent = int(match.group(1))
                mapped = 20 + int(vina_percent * 0.7)
                job["progress"] = max(job["progress"], mapped)

            # Task finished
            if "done in" in lower:
                job["completed_tasks"] += 1

                if job["total_tasks"]:
                    pct = int((job["completed_tasks"] / job["total_tasks"]) * 100)
                    job["progress"] = max(job["progress"], min(95, pct))
                else:
                    job["progress"] = min(95, job["progress"] + 10)

            job["progress"] = min(job["progress"], 99)

    except Exception as e:
        job["log"].append(f"Output read error: {e}")

    # Process finished
    process.wait()
    if process.returncode == 0:
        job["status"] = "finished"
        job["progress"] = 100
    else:
        job["status"] = "failed"


# ============================================================
# ROOT
# ============================================================
@app.get("/")
def root():
    return {"message": "Local backend is running"}


# ============================================================
# RUN SCRIPT
# ============================================================
@app.post("/run-script")
async def run_script(script_content: str = Form(...)):

    job_id = uuid.uuid4().hex[:10]
    job_dir = os.path.join(tempfile.gettempdir(), f"vdock_{job_id}")
    os.makedirs(job_dir, exist_ok=True)

    script_path = os.path.join(job_dir, "vsframework.py")

    # Save script
    try:
        with open(script_path, "w") as f:
            f.write(script_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save script: {e}")

    # Start process
    try:
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=job_dir
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start script: {e}")

    # Register job
    JOBS[job_id] = {
        "status": "starting",
        "log": [],
        "progress": 0,
        "process": process,
        "script_path": script_path,
        "job_dir": job_dir,
        "completed_tasks": 0,
        "total_tasks": None
    }

    # Output reader
    threading.Thread(
        target=stream_output,
        args=(job_id, process),
        daemon=True
    ).start()

    return {"job_id": job_id, "message": "Script started"}


# ============================================================
# GET SCRIPT STATUS
# ============================================================
@app.get("/run-status/{job_id}")
def run_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    job = JOBS[job_id]

    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": int(job.get("progress", 0)),
        "log_tail": job["log"][-40:],
        "script_path": job["script_path"],
        "job_dir": job["job_dir"]
    }


# ============================================================
# RUN SERVER
# ============================================================
if __name__ == "__main__":
    import uvicorn
    print("="*80)
    print("🚀 Local Docking Backend Starting...")
    print("="*80)
    print("Port: 5006")
    print("\nFeatures:")
    print("  ✓ AutoDock Vina integration")
    print("  ✓ File upload support")
    print("  ✓ Real-time progress tracking")
    print("  ✓ Dependency checking")
    print("  ✓ Script execution with live logs")
    print("="*80 + "\n")
    
    uvicorn.run(
        app,  # Changed from "main:app" to app
        host="127.0.0.1",
        port=5006,  # Changed from 5005 to 5006
        log_level="info"
    )
