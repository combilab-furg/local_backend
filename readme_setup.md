#  Unified Local Backend

This package contains **three molecular modeling backends** that run simultaneously on your local machine.

##  What's Included

| Service | Port | Description |
|---------|------|-------------|
| **PLIP Backend** | 5005 | Protein-Ligand Interaction Profiler |
| **Docking Backend** | 5006 | AutoDock Vina Molecular Docking |
| **RFL-Score Backend** | 5007 | Binding Affinity Prediction |

##  Quick Start

### 1️⃣ Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2️⃣ Run All Backends

```bash
python3 main.py
```

That's it! All three services will start automatically.

---

## 🔧 Installation Requirements

### Python Requirements
- **Python 3.8+** (required)
- All packages in `requirements.txt`

### External Tools (Required by specific backends)

#### For Docking Backend (main2.py):
```bash
# Ubuntu/Debian
sudo apt-get install autodock-vina openbabel mgltools

# macOS
brew install autodock-vina open-babel
# MGLTools: download from http://mgltools.scripps.edu/
```

#### For RFL-Score Backend (main3.py):
```bash
# Install Open Babel
sudo apt-get install openbabel  # Ubuntu/Debian
brew install open-babel         # macOS

# Clone RFL-Score repository
git clone https://github.com/combilab-furg/rfl-score_v1.git ~/rfl-score_v1
```

#### For PLIP Backend (main1.py):
```bash
# PLIP installation instructions
pip install plip
# Or follow: https://github.com/pharmai/plip
```

---

## 📁 File Structure

```
local-backend/
├── main.py              ← RUN THIS (Master orchestrator)
├── plip.py             (PLIP Backend - Port 5005)
├── Docking.py             (Docking Backend - Port 5006)
├── rfl.py             (RFL-Score Backend - Port 5007)
├── requirements.txt     (Python dependencies)
└── README.md           (This file)
```

---

---

##  Usage

### Starting Services
```bash
python3 main.py
```

You'll see:
```
🚀 Unified Local Backend Orchestrator
==========================================
✅ PLIP Backend started successfully!
   🌐 Running at: http://127.0.0.1:5005

✅ Docking Backend started successfully!
   🌐 Running at: http://127.0.0.1:5006

✅ RFL-Score Backend started successfully!
   🌐 Running at: http://127.0.0.1:5007

🎉 Successfully started 3/3 services!
```

### Stopping Services
Press `Ctrl+C` in the terminal. All services will shut down gracefully.

---

##  Troubleshooting

### Port Already in Use
If you see `❌ Port XXXX is already in use!`:
1. Close any application using that port
2. Or change the port in the respective `mainX.py` file

### Service Won't Start
Check the error message for missing dependencies:
```bash
# Check if tools are installed
which vina
which obabel
python3 -c "import Bio; print('✅ BioPython installed')"
```

### Permission Denied
On Linux/macOS, you might need to make files executable:
```bash
chmod +x main.py main1.py main2.py main3.py
```

---

---

## Advanced Configuration

### Changing Ports

Edit the `SERVICES` list in `main.py`:

```python
SERVICES = [
    {"name": "PLIP Backend", "file": "plip.py", "port": 5005},
    {"name": "Docking Backend", "file": "Docking.py", "port": 5006},
    {"name": "RFL-Score Backend", "file": "rfl.py", "port": 5007}
]
```

Then update the port in each `mainX.py` file at the bottom:
```python
uvicorn.run("main:app", host="127.0.0.1", port=XXXX)
```

---

##  Development Notes

### Running Services Individually
If you need to run just one service for testing:
```bash
python3 plip.py  # PLIP only
python3 Docking.py  # Docking only
python3 rfl.py  # RFL-Score only
```

### Logs
Each service outputs logs to the terminal. Check the orchestrator output for any errors.

---



