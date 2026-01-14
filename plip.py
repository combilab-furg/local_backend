"""
Local PLIP Backend Runner - Flattened File Structure with Exact Matching
Runs on user's machine - executes jobs from online server
FIXED: Now processes ALL receptors, not just one
"""

import os
import sys
import tempfile
import shutil
import subprocess
import json
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List
import uvicorn
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

app = FastAPI(title="Local PLIP Runner")

# CORS - Allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temp storage for uploaded files
TEMP_STORAGE = {}


@app.get("/")
def root():
    return {
        "service": "Local PLIP Runner",
        "status": "online",
        "version": "3.1.0 (Fixed Multi-Receptor Processing)"
    }


@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.post("/upload-files")
async def upload_files(
    files: List[UploadFile] = File(...),
    file_type: str = Form(...)  # "receptor" or "ligand"
):
    """
    Upload files to temporary storage
    FLATTENS all files to root level (no subfolders)
    Handles name collisions automatically
    """
    if not files:
        raise HTTPException(400, "No files provided")
    
    # Create temp directory for this upload session
    session_id = os.urandom(8).hex()
    temp_dir = os.path.join(tempfile.gettempdir(), f"plip_{file_type}_{session_id}")
    os.makedirs(temp_dir, exist_ok=True)
    
    saved_files = []
    name_count = {}  # Track duplicate names
    
    print(f"\n{'='*80}")
    print(f"[UPLOAD] Starting upload for {file_type}")
    print(f"  Session ID: {session_id}")
    print(f"  Files to process: {len(files)}")
    print(f"{'='*80}")
    
    for f in files:
        # Extract just the filename (flatten folder structure)
        if '/' in f.filename:
            base_name = f.filename.split('/')[-1]  # Get last part of path
        else:
            base_name = f.filename
        
        # Skip non-compatible files
        if not base_name.endswith(('.pdb', '.pdbqt')):
            print(f"[UPLOAD] ⚠️  Skipping non-compatible file: {base_name}")
            continue
        
        # Handle name collisions by appending number
        if base_name in name_count:
            name_count[base_name] += 1
            name, ext = os.path.splitext(base_name)
            final_name = f"{name}_duplicate{name_count[base_name]}{ext}"
            print(f"[UPLOAD] ⚠️  Name collision: {base_name} → {final_name}")
        else:
            name_count[base_name] = 0
            final_name = base_name
        
        # Save to flat temp directory
        target = os.path.join(temp_dir, final_name)
        content = await f.read()
        
        with open(target, "wb") as out:
            out.write(content)
        
        saved_files.append(final_name)
        print(f"[UPLOAD] ✓ Saved: {final_name}")
    
    # Store session info
    TEMP_STORAGE[session_id] = {
        "type": file_type,
        "path": temp_dir,
        "files": saved_files
    }
    
    print(f"\n[UPLOAD] ✅ Upload complete!")
    print(f"  Session {session_id}: Saved {len(saved_files)} {file_type} files")
    print(f"  Location: {temp_dir}")
    print(f"{'='*80}\n")
    
    return {
        "session_id": session_id,
        "file_type": file_type,
        "files": saved_files,
        "count": len(saved_files)
    }


@app.post("/execute-job")
async def execute_job(
    script: str = Form(...),
    receptor_session: str = Form(...),
    ligand_session: str = Form(...),
    output_folder: str = Form(...),
    max_poses: int = Form(5),
    config: str = Form("{}"),
    max_workers: int = Form(4)
):
    """
    Execute PLIP job with exact receptor-ligand matching
    Matching done HERE in local backend (not in server script)
    """
    print("\n" + "="*80)
    print(f"[EXECUTE] Starting PLIP job with exact matching")
    print(f"  Receptor session: {receptor_session}")
    print(f"  Ligand session: {ligand_session}")
    print(f"  Output folder: {output_folder}")
    print(f"  Max poses: {max_poses}")
    print(f"  Max workers: {max_workers}")
    print("="*80)
    
    # Validate sessions
    if receptor_session not in TEMP_STORAGE:
        raise HTTPException(400, f"Invalid receptor session: {receptor_session}")
    if ligand_session not in TEMP_STORAGE:
        raise HTTPException(400, f"Invalid ligand session: {ligand_session}")
    
    # Get temp storage paths
    receptor_temp_dir = TEMP_STORAGE[receptor_session]["path"]
    ligand_temp_dir = TEMP_STORAGE[ligand_session]["path"]
    
    print(f"\n[EXECUTE] Reading files from temp storage...")
    print(f"  Receptor dir: {receptor_temp_dir}")
    print(f"  Ligand dir: {ligand_temp_dir}")
    
    # Get all files from temp storage (already flattened)
    receptor_files = get_all_pdbqt_files(receptor_temp_dir)
    ligand_files = get_all_pdbqt_files(ligand_temp_dir)
    
    print(f"\n📂 Files found in temp storage:")
    print(f"  Receptors: {len(receptor_files)}")
    for r in receptor_files:
        print(f"    - {os.path.basename(r)}")
    print(f"  Ligands: {len(ligand_files)}")
    for l in ligand_files:
        print(f"    - {os.path.basename(l)}")
    
    if not receptor_files:
        raise HTTPException(400, "No receptor files found")
    if not ligand_files:
        raise HTTPException(400, "No ligand files found")
    
    # MATCH receptors with ligands based on naming convention
    print(f"\n🔗 Starting matching process...")
    matched_combinations = match_receptors_to_ligands(receptor_files, ligand_files)
    
    if not matched_combinations:
        print("❌ No matching receptor-ligand pairs found!")
        raise HTTPException(400, 
            "No matching pairs found. Ensure ligands are named like: "
            "{receptor_prefix}_{compound}_{score}.pdbqt")
    
    print(f"\n{'='*80}")
    print(f"✅ Matching Complete! Found {len(matched_combinations)} combination(s):")
    print(f"{'='*80}")
    for i, combo in enumerate(matched_combinations, 1):
        print(f"  {i}. {combo['receptor_name']} × {combo['ligand_name']}")
    print(f"{'='*80}\n")
    
    # Create main job directory
    job_id = os.urandom(4).hex()
    job_dir = os.path.join(output_folder, f"plip_job_{job_id}")
    os.makedirs(job_dir, exist_ok=True)
    
    # Save matching summary
    summary_path = os.path.join(job_dir, "combinations_summary.json")
    with open(summary_path, 'w') as f:
        json.dump({
            "total_combinations": len(matched_combinations),
            "combinations": [
                {
                    "receptor": c["receptor_name"],
                    "ligand": c["ligand_name"],
                    "matched_identifier": c["matched_identifier"]
                }
                for c in matched_combinations
            ]
        }, f, indent=2)
    print(f"✓ Saved combinations summary: {summary_path}\n")
    
    # Create temp script directory
    temp_script_dir = tempfile.mkdtemp(prefix="plip_script_")
    script_path = os.path.join(temp_script_dir, "plip_script.py")
    with open(script_path, "w") as f:
        f.write(script)
    
    # Prepare output directories for each combination
    for combo in matched_combinations:
        combo_name = f"{combo['receptor_name'].replace('.pdbqt', '').replace('.pdb', '')}__{combo['ligand_name'].replace('.pdbqt', '').replace('.pdb', '')}"
        combo_dir = os.path.join(job_dir, combo_name)
        os.makedirs(combo_dir, exist_ok=True)
        combo["output_dir"] = combo_dir
        combo["combo_name"] = combo_name
    
    # Execute combinations in parallel
    print(f"🚀 Processing {len(matched_combinations)} combination(s) in parallel...")
    print(f"   Using {max_workers} worker(s)\n")
    
    start_time = time.time()
    results = []
    failed = []
    
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_combo = {
                executor.submit(
                    execute_single_combination,
                    script_path,
                    combo,
                    max_poses
                ): combo
                for combo in matched_combinations
            }
            
            for i, future in enumerate(as_completed(future_to_combo), 1):
                combo = future_to_combo[future]
                try:
                    result = future.result()
                    results.append(result)
                    print(f"[{i}/{len(matched_combinations)}] ✅ {combo['combo_name']}")
                except Exception as e:
                    error_info = {
                        "combo_name": combo['combo_name'],
                        "receptor": combo['receptor_name'],
                        "ligand": combo['ligand_name'],
                        "error": str(e)
                    }
                    failed.append(error_info)
                    print(f"[{i}/{len(matched_combinations)}] ❌ {combo['combo_name']} - {e}")
    
    finally:
        # Cleanup temp script
        try:
            if os.path.exists(temp_script_dir):
                shutil.rmtree(temp_script_dir)
                print(f"\n[CLEANUP] ✅ Deleted temp script directory")
        except Exception as e:
            print(f"[CLEANUP] ⚠️ Failed to delete temp script: {e}")
    
    elapsed_time = time.time() - start_time
    
    print(f"\n{'='*80}")
    print(f"🎉 Job Complete!")
    print(f"  Job ID: {job_id}")
    print(f"  Job Directory: {job_dir}")
    print(f"  Total combinations: {len(matched_combinations)}")
    print(f"  ✅ Successful: {len(results)}")
    print(f"  ❌ Failed: {len(failed)}")
    print(f"  ⏱️  Time: {elapsed_time:.2f}s")
    print(f"{'='*80}\n")
    
    # Cleanup temp files
    cleanup_session(receptor_session)
    cleanup_session(ligand_session)
    
    return {
        "job_id": job_id,
        "job_dir": job_dir,
        "status": "completed",
        "total_combinations": len(matched_combinations),
        "successful": len(results),
        "failed": len(failed),
        "execution_time_seconds": round(elapsed_time, 2),
        "results": results,
        "failed_combinations": failed
    }


def execute_single_combination(script_path, combo, max_poses):
    """Execute PLIP analysis for a single receptor-ligand combination"""
    # Copy original files to combination output directory first
    original_files_dir = os.path.join(combo["output_dir"], "original_files")
    os.makedirs(original_files_dir, exist_ok=True)
    
    # Keep original filenames (no prefix)
    receptor_copy = os.path.join(original_files_dir, combo['receptor_name'])
    ligand_copy = os.path.join(original_files_dir, combo['ligand_name'])
    
    shutil.copy2(combo["receptor_path"], receptor_copy)
    shutil.copy2(combo["ligand_path"], ligand_copy)
    
    # Set environment variables for script
    env = {
        "RECEPTOR_PATH": combo["receptor_path"],
        "LIGAND_PATH": combo["ligand_path"],
        "OUTPUT_DIR": combo["output_dir"],
        "MAX_POSES": str(max_poses),
    }
    
    # Execute script
    result = subprocess.run(
        [sys.executable, script_path],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=900  # 15 minutes per combination
    )
    
    if result.returncode != 0:
        raise Exception(f"Script failed: {result.stderr}")
    
    # Parse results from script output
    try:
        # Get last line which should be JSON output
        output_lines = result.stdout.strip().split('\n')
        json_line = output_lines[-1]
        output_data = json.loads(json_line)
    except (json.JSONDecodeError, IndexError) as e:
        print(f"Warning: Could not parse script output, scanning directory instead: {e}")
        output_data = scan_output_directory(combo["output_dir"])
    
    return {
        "combo_name": combo["combo_name"],
        "receptor": combo["receptor_name"],
        "ligand": combo["ligand_name"],
        "output_dir": combo["output_dir"],
        **output_data
    }


# ============================================================================
# MATCHING LOGIC - ENHANCED DEBUG VERSION
# ============================================================================

def get_receptor_identifiers(receptor_filename):
    """
    Extract possible identifiers from receptor name
    
    Examples:
    - 7MS2_edit.pdbqt → ["7MS2_edit", "7MS2"]
    - HLE14413_1.pdbqt → ["HLE14413_1", "HLE14413", "HLE"]
    - GAB.pdbqt → ["GAB"]
    """
    base = receptor_filename.replace('.pdbqt', '').replace('.pdb', '')
    identifiers = [base]  # Full name
    
    # Add progressively shorter prefixes
    if '_' in base:
        parts = base.split('_')
        # Add cumulative prefixes: A, A_B, A_B_C, etc.
        for i in range(len(parts)):
            prefix = '_'.join(parts[:i+1])
            if prefix and prefix not in identifiers:
                identifiers.append(prefix)
        
        # Also add just the first part separately
        if parts[0] not in identifiers:
            identifiers.append(parts[0])
    
    # Sort by length (longest first for better matching)
    identifiers.sort(key=len, reverse=True)
    
    return identifiers


def match_receptors_to_ligands(receptor_files, ligand_files):
    """
    Match receptors to ligands based on naming convention
    FLEXIBLE MATCHING: Handles partial name matches
    """
    combinations = []
    skipped_receptors = []
    
    print(f"\n{'='*80}")
    print(f"🔍 MATCHING PROCESS STARTED (Flexible Mode)")
    print(f"{'='*80}")
    print(f"  Total receptors to process: {len(receptor_files)}")
    print(f"  Total ligands available: {len(ligand_files)}")
    print(f"{'='*80}\n")
    
    # Process each receptor
    for idx, receptor_path in enumerate(receptor_files, 1):
        receptor_name = os.path.basename(receptor_path)
        identifiers = get_receptor_identifiers(receptor_name)
        
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"[{idx}/{len(receptor_files)}] Processing Receptor: {receptor_name}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  Full path: {receptor_path}")
        print(f"  Extracted identifiers: {identifiers}")
        print(f"  Checking {len(ligand_files)} ligand(s)...\n")
        
        matches_found = 0
        
        # Check each ligand
        for ligand_path in ligand_files:
            ligand_name = os.path.basename(ligand_path)
            
            # Try exact match first
            matched_identifier = None
            for identifier in identifiers:
                if ligand_name.startswith(f"{identifier}_"):
                    matched_identifier = identifier
                    break
            
            # If no exact match, try flexible matching (check if identifier is CONTAINED in ligand name start)
            if not matched_identifier:
                for identifier in identifiers:
                    # Check if ligand starts with identifier (even if partial)
                    ligand_prefix = ligand_name.split('_')[0] if '_' in ligand_name else ligand_name.split('.')[0]
                    
                    # Flexible match: ligand prefix contains receptor identifier
                    # Example: "7MS" in ligand matches "7MS2" in receptor
                    if identifier.startswith(ligand_prefix) and len(ligand_prefix) >= 3:
                        matched_identifier = f"{identifier} (flexible: {ligand_prefix})"
                        break
            
            if matched_identifier:
                combinations.append({
                    "receptor_path": receptor_path,
                    "receptor_name": receptor_name,
                    "ligand_path": ligand_path,
                    "ligand_name": ligand_name,
                    "matched_identifier": matched_identifier
                })
                matches_found += 1
                print(f"    ✅ Match #{matches_found}: {ligand_name}")
                print(f"       Matched via: '{matched_identifier}'")
        
        # Summary for this receptor
        print(f"\n  {'─'*76}")
        if matches_found == 0:
            print(f"  ⚠️  NO MATCHES FOUND for {receptor_name}")
            print(f"  This receptor will be SKIPPED")
            skipped_receptors.append(receptor_name)
        else:
            print(f"  ✅ Total matches for {receptor_name}: {matches_found}")
        print(f"  {'─'*76}\n")
    
    # Final summary
    print(f"{'='*80}")
    print(f"🏁 MATCHING PROCESS COMPLETE")
    print(f"{'='*80}")
    print(f"  Total combinations created: {len(combinations)}")
    print(f"  Receptors successfully matched: {len(receptor_files) - len(skipped_receptors)}")
    print(f"  Receptors skipped (no matches): {len(skipped_receptors)}")
    print(f"{'='*80}\n")
    
    if skipped_receptors:
        print(f"⚠️  The following receptor(s) had NO matching ligands:")
        for i, rec in enumerate(skipped_receptors, 1):
            print(f"    {i}. {rec}")
        print()
    
    return combinations


def get_all_pdbqt_files(directory):
    """Get all .pdb and .pdbqt files from directory (already flat)"""
    if not os.path.exists(directory):
        print(f"ERROR: Directory does not exist: {directory}")
        return []
    
    files = []
    try:
        for fname in os.listdir(directory):
            if fname.endswith(('.pdb', '.pdbqt')):
                full_path = os.path.join(directory, fname)
                files.append(full_path)
    except Exception as e:
        print(f"ERROR reading directory {directory}: {e}")
        return []
    
    return sorted(files)


def scan_output_directory(job_dir):
    """Scan output directory and categorize files"""
    poses = []
    
    for item in sorted(os.listdir(job_dir)):
        item_path = os.path.join(job_dir, item)
        if os.path.isdir(item_path) and item.startswith("pose_"):
            try:
                pose_num = int(item.split("_")[1])
            except (IndexError, ValueError):
                continue
            
            files = os.listdir(item_path)
            categorized = {
                "pose": pose_num,
                "folder": item_path,
                "csv_files": [f for f in files if f.endswith('.csv')],
                "json_files": [f for f in files if f.endswith('.json')],
                "png_files": [f for f in files if f.endswith('.png')],
                "xml_files": [f for f in files if f.endswith('.xml')],
                "txt_files": [f for f in files if f.endswith('.txt')],
                "pdb_files": [f for f in files if f.endswith('.pdb')],
                "pdbqt_files": [f for f in files if f.endswith('.pdbqt')],
            }
            poses.append(categorized)
    
    return {
        "poses_analyzed": len(poses),
        "poses": poses
    }


@app.get("/download")
def download_file(path: str):
    """Download a result file"""
    if not os.path.exists(path):
        raise HTTPException(404, f"File not found: {path}")
    
    return FileResponse(
        path=path,
        filename=os.path.basename(path),
        media_type='application/octet-stream'
    )


@app.delete("/cleanup/{session_id}")
def cleanup_session(session_id: str):
    """Cleanup temporary session files"""
    if session_id not in TEMP_STORAGE:
        return {"status": "not_found"}
    
    session = TEMP_STORAGE[session_id]
    try:
        if os.path.exists(session["path"]):
            shutil.rmtree(session["path"])
        del TEMP_STORAGE[session_id]
        return {"status": "cleaned", "session_id": session_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("="*80)
    print("🚀 Local PLIP Runner Starting...")
    print("="*80)
    print("Version: 3.1.0 (Fixed Multi-Receptor Processing)")
    print("\nFeatures:")
    print("  ✓ Flattened file structure (no subfolders)")
    print("  ✓ Exact receptor-ligand matching")
    print("  ✓ Multi-receptor support (FIXED)")
    print("  ✓ Parallel processing")
    print("  ✓ Auto-handles name collisions")
    print("  ✓ Preserves original filenames")
    print("  ✓ Enhanced debug output")
    print("  ✓ Local execution (no cloud upload)")
    print("="*80 + "\n")
    
    uvicorn.run(
        app,  # Changed from "main:app" to app
        host="127.0.0.1",
        port=5008,
        log_level="info"
    )
