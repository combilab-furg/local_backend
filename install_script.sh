#!/bin/bash
# Unified Local Backend - Installation Script
# Run with: bash install.sh

set -e

echo "=========================================="
echo "🚀 Unified Local Backend Installer"
echo "=========================================="
echo ""

# Check Python version
echo "📌 Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed!"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✅ Python $PYTHON_VERSION found"

# Check if version is >= 3.8
REQUIRED_VERSION="3.8"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Python 3.8+ required (found $PYTHON_VERSION)"
    exit 1
fi

echo ""

# Install Python packages
echo "📦 Installing Python dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo ""
echo "✅ Python dependencies installed!"
echo ""

# Check external tools
echo "=========================================="
echo "🔍 Checking External Tools"
echo "=========================================="
echo ""

# Check AutoDock Vina
if command -v vina &> /dev/null; then
    echo "✅ AutoDock Vina: Found"
else
    echo "⚠️  AutoDock Vina: NOT FOUND"
    echo "   Install: sudo apt-get install autodock-vina"
fi

# Check Open Babel
if command -v obabel &> /dev/null; then
    echo "✅ Open Babel: Found"
else
    echo "⚠️  Open Babel: NOT FOUND"
    echo "   Install: sudo apt-get install openbabel"
fi

# Check PLIP
if python3 -c "import plip" 2>/dev/null; then
    echo "✅ PLIP: Found"
else
    echo "⚠️  PLIP: NOT FOUND"
    echo "   Install: pip install plip"
fi

# Check RFL-Score
if [ -d "$HOME/rfl-score_v1" ]; then
    echo "✅ RFL-Score: Found at ~/rfl-score_v1"
else
    echo "⚠️  RFL-Score: NOT FOUND"
    echo "   Install: git clone https://github.com/combilab-furg/rfl-score_v1.git ~/rfl-score_v1"
fi

echo ""
echo "=========================================="
echo "✅ Installation Complete!"
echo "=========================================="
echo ""
echo "📝 Next Steps:"
echo ""
echo "1. Update ports in main2.py and main3.py (see PORT_UPDATES.md)"
echo "2. Update frontend URLs to use ports 5005, 5006, 5007"
echo "3. Run: python3 main.py"
echo ""
echo "📚 For more info, read README.md"
echo ""
