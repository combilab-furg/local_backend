#!/usr/bin/env python3
"""
Local RFL-Score Backend - Script Executor
Runs on user's machine (Port 5005)
Role: "Dumb Executor" - Receives scripts from server and executes them
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from typing import List, Optional
import os
import sys
import json
import subprocess
import tempfile
import shutil
import uuid
from pathlib import Path
from datetime import datetime
import traceback
import uvicorn

app = FastAPI(title="Local RFL-Score Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# CONFIGURATION
# ============================================================================
UPLOAD_BASE = Path(tempfile.gettempdir()) / "rfl_score_uploads"
UPLOAD_BASE.mkdir(exist_ok=True)

# RFL-Score installation path
RFL_SCORE_PATH = Path.home() / "rfl-score_v1"

# Session storage (in-memory)
SESSIONS = {}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def check_rfl_score_installation():
    """Check if RFL-Score is properly installed."""
    if not RFL_SCORE_PATH.exists():
        return {
            "installed": False,
            "message": f"❌ RFL-Score not found at {RFL_SCORE_PATH}"
        }
    
    sf160_script = RFL_SCORE_PATH / "sf160.py"
    if not sf160_script.exists():
        return {
            "installed": False,
            "message": f"❌ sf160.py not found at {sf160_script}"
        }
    
    return {
        "installed": True,
        "message": f"✅ RFL-Score found at {RFL_SCORE_PATH}",
        "path": str(RFL_SCORE_PATH)
    }

def check_dependencies():
    """Check if required dependencies are installed."""
    missing = []
    
    # Check Python packages
    try:
        import Bio
    except ImportError:
        missing.append("biopython")
    
    try:
        import matplotlib
    except ImportError:
        missing.append("matplotlib")
    
    # Check Open Babel
    result = subprocess.run(["which", "obabel"], capture_output=True)
    if result.returncode != 0:
        missing.append("openbabel")
    
    return missing

# ============================================================================
# ROUTES
# ============================================================================

@app.get("/")
def home():
    """Health check endpoint."""
    rfl_check = check_rfl_score_installation()
    missing_deps = check_dependencies()
    
    return {
        "status": "running",
        "version": "2.0.0",
        "role": "Script Executor",
        "rfl_score": rfl_check,
        "missing_dependencies": missing_deps,
        "active_sessions": len(SESSIONS)
    }

@app.post("/upload-files")
async def upload_files(
    files: List[UploadFile] = File(...),
    file_type: str = Form(...)
):
    """
    Receive files from frontend and store in session directory.
    
    Form data:
    - files: Multiple file uploads
    - file_type: "receptor", "ligand", or "fasta"
    
    Returns:
    - session_id: Unique session identifier
    - file_count: Number of files uploaded
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    # Create session directory
    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_BASE / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Save files
    saved_files = []
    for file in files:
        if file.filename:
            filepath = session_dir / file.filename
            with open(filepath, "wb") as f:
                content = await file.read()
                f.write(content)
            saved_files.append(file.filename)
    
    # Store session metadata
    SESSIONS[session_id] = {
        "created": datetime.now().isoformat(),
        "type": file_type,
        "directory": str(session_dir),
        "files": saved_files
    }
    
    return {
        "session_id": session_id,
        "file_count": len(saved_files),
        "files": saved_files
    }

@app.post("/execute-rfl-script")
async def execute_rfl_script(request: dict):
    """
    Receive and execute RFL-Score preparation script from server backend.
    
    JSON body:
    - script: Complete Python script as string
    - timeout: Execution timeout in seconds (default: 3600)
    
    Returns:
    - JSON result from script execution
    """
    try:
        # Extract data from request
        script_content = request.get("script")
        timeout = request.get("timeout", 3600)
        
        if not script_content:
            raise HTTPException(status_code=400, detail="Script content is empty or missing")
        
        print(f"\n{'='*80}")
        print(f"📥 Received script execution request")
        print(f"Script length: {len(script_content)} characters")
        print(f"Timeout: {timeout} seconds")
        print(f"{'='*80}\n")
        
        # Create temporary script file
        script_dir = UPLOAD_BASE / "scripts"
        script_dir.mkdir(exist_ok=True)
        
        script_id = str(uuid.uuid4())
        script_file = script_dir / f"rfl_script_{script_id}.py"
        
        # Write script to file
        with open(script_file, "w") as f:
            f.write(script_content)
        
        print(f"✓ Script saved to: {script_file}")
        print(f"🚀 Executing script...\n")
        
        # Execute script with subprocess isolation
        result = subprocess.run(
            [sys.executable, str(script_file)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(script_dir)
        )
        
        # Parse output
        output = result.stdout
        stderr = result.stderr
        
        print(f"\n{'='*80}")
        print("📋 Script Output:")
        print(f"{'='*80}")
        print(output)
        
        if stderr:
            print(f"\n{'='*80}")
            print("⚠️  Script Errors/Warnings:")
            print(f"{'='*80}")
            print(stderr)
        
        print(f"\n{'='*80}")
        print(f"✅ Script execution completed (return code: {result.returncode})")
        print(f"{'='*80}\n")
        
        # Extract JSON result from output
        json_result = None
        if "JSON_RESULT_START" in output:
            try:
                json_start = output.find("JSON_RESULT_START") + len("JSON_RESULT_START")
                json_end = output.find("JSON_RESULT_END")
                json_str = output[json_start:json_end].strip()
                json_result = json.loads(json_str)
                print("✓ Successfully parsed JSON result")
            except Exception as e:
                print(f"⚠️  Failed to parse JSON result: {e}")
        
        # Cleanup script file
        try:
            script_file.unlink()
        except:
            pass
        
        if json_result:
            return json_result
        else:
            # Fallback: return raw output
            return {
                "status": "completed" if result.returncode == 0 else "error",
                "return_code": result.returncode,
                "output": output,
                "stderr": stderr
            }
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"Script execution timeout after {timeout} seconds")
        
    except Exception as e:
        print(f"\n❌ Script execution failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download")
async def download_file(path: str = Query(...)):
    """
    Download output files.
    
    Query params:
    - path: Absolute path to file
    """
    if not path:
        raise HTTPException(status_code=400, detail="No path provided")
    
    filepath = Path(path)
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=str(filepath),
        filename=filepath.name,
        media_type="application/octet-stream"
    )

@app.get("/sessions")
def list_sessions():
    """List all active sessions."""
    return {
        "count": len(SESSIONS),
        "sessions": SESSIONS
    }

@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    """Delete a session and its files."""
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_info = SESSIONS[session_id]
    session_dir = Path(session_info["directory"])
    
    # Delete files
    if session_dir.exists():
        shutil.rmtree(session_dir)
    
    # Remove from memory
    del SESSIONS[session_id]
    
    return {"status": "deleted", "session_id": session_id}

@app.post("/cleanup")
def cleanup_old_sessions(max_age_hours: int = 24):
    """Clean up sessions older than X hours."""
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    
    deleted = []
    for session_id, info in list(SESSIONS.items()):
        created = datetime.fromisoformat(info["created"])
        if created < cutoff:
            session_dir = Path(info["directory"])
            if session_dir.exists():
                shutil.rmtree(session_dir)
            del SESSIONS[session_id]
            deleted.append(session_id)
    
    return {
        "deleted": len(deleted),
        "sessions": deleted
    }

# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    print("="*80)
    print("🚀 Local RFL-Score Backend Starting...")
    print("="*80)
    print("Version: 2.0.0 (Script Executor)")
    print("Port: 5005")
    print(f"RFL-Score Path: {RFL_SCORE_PATH}")
    print(f"Upload Directory: {UPLOAD_BASE}")
    print("\nRole: Dumb Executor")
    print("  ✓ Receives files from frontend")
    print("  ✓ Receives preparation script from server")
    print("  ✓ Executes script locally")
    print("  ✓ Returns results")
    print("\nAll preparation logic is in the script (generated by server)")
    print("="*80 + "\n")
    
    # Check RFL-Score installation
    rfl_check = check_rfl_score_installation()
    print(rfl_check["message"])
    
    # Check dependencies
    missing_deps = check_dependencies()
    if missing_deps:
        print(f"\n⚠️  Missing dependencies: {', '.join(missing_deps)}")
        print("\nInstall with:")
        for dep in missing_deps:
            if dep == "biopython":
                print("  pip install biopython")
            elif dep == "matplotlib":
                print("  pip install matplotlib")
            elif dep == "openbabel":
                print("  # Ubuntu/Debian: sudo apt install openbabel")
                print("  # macOS: brew install open-babel")
                print("  # Conda: conda install -c conda-forge openbabel")
    else:
        print("✅ All dependencies installed")
    
    if not rfl_check["installed"]:
        print("\n" + "="*80)
        print("📚 RFL-Score Installation Instructions")
        print("="*80)
        print("\n1. Clone the repository:")
        print(f"   git clone https://github.com/combilab-furg/rfl-score_v1.git {RFL_SCORE_PATH}")
        print("\n2. Follow installation instructions in the repository")
        print("\n3. Test installation:")
        print(f"   cd {RFL_SCORE_PATH}")
        print("   python sf160.py --help")
        print("\n" + "="*80)
        print("\n⚠️  WARNING: Backend will start but RFL-Score jobs will FAIL!")
        print("="*80 + "\n")
    
    print("\n🌐 Starting FastAPI server on http://127.0.0.1:5005")
    print("="*80 + "\n")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=5007,
        log_level="info"
    )
