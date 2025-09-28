#!/bin/bash

# SEIDRA Linux Auto-Installation Script
# Supports Ubuntu, Debian, Arch Linux, CentOS/RHEL

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# SEIDRA ASCII Art
echo -e "${PURPLE}"
echo "========================================"
echo "   SEIDRA - Build your own myth"
echo "   Linux Auto-Installation Script"
echo "========================================"
echo -e "${NC}"

# Get script directory
SEIDRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_TARGET_MAJOR=3
PYTHON_TARGET_MINOR=11
PYTHON_VERSION_LABEL="${PYTHON_TARGET_MAJOR}.${PYTHON_TARGET_MINOR}"
PYTHON_CMD=""
PYTHON_VERSION_DETECTED=""
NODE_VERSION="18"
SYSTEMCTL_AVAILABLE=0

if command -v systemctl &> /dev/null && [[ -d /run/systemd/system ]]; then
    SYSTEMCTL_AVAILABLE=1
fi

check_python_version() {
    local version="$1"
    local major minor
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)

    if [[ -z "$major" || -z "$minor" ]]; then
        return 1
    fi

    if [[ ! "$major" =~ ^[0-9]+$ || ! "$minor" =~ ^[0-9]+$ ]]; then
        return 1
    fi

    if (( major > PYTHON_TARGET_MAJOR )); then
        return 0
    fi

    if (( major == PYTHON_TARGET_MAJOR && minor >= PYTHON_TARGET_MINOR )); then
        return 0
    fi

    return 1
}

detect_python_command() {
    local candidates=("python${PYTHON_TARGET_MAJOR}.${PYTHON_TARGET_MINOR}" python3 python)
    for candidate in "${candidates[@]}"; do
        if command -v "$candidate" &> /dev/null; then
            local raw_version
            raw_version=$("$candidate" --version 2>&1 | awk '{print $2}')
            if check_python_version "$raw_version"; then
                PYTHON_CMD="$candidate"
                PYTHON_VERSION_DETECTED="$raw_version"
                return 0
            fi
        fi
    done
    return 1
}

# Detect Linux distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
    VERSION=$VERSION_ID
else
    echo -e "${RED}[!] Cannot detect Linux distribution${NC}"
    exit 1
fi

echo -e "${CYAN}[INFO] Detected: $PRETTY_NAME${NC}"

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    echo -e "${YELLOW}[!] Running as root. Some operations may require sudo.${NC}"
fi

echo -e "${BLUE}[1/8] Checking system requirements...${NC}"

# Check CPU
CPU_CORES=$(nproc)
echo "CPU Cores: $CPU_CORES"

# Check RAM
RAM_GB=$(free -g | awk '/^Mem:/{print $2}')
echo "RAM: ${RAM_GB}GB"
if [ "$RAM_GB" -lt 32 ]; then
    echo -e "${YELLOW}[!] WARNING: Less than 32GB RAM detected. 64GB recommended for optimal performance.${NC}"
fi

# Check GPU
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}[✓] NVIDIA GPU detected${NC}"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits
else
    echo -e "${YELLOW}[!] WARNING: NVIDIA GPU not detected or drivers not installed${NC}"
    echo "    SEIDRA requires RTX 3090 or compatible GPU for optimal performance"
fi

# Check disk space
DISK_SPACE=$(df -BG "$SEIDRA_DIR" | awk 'NR==2 {print $4}' | sed 's/G//')
echo "Available disk space: ${DISK_SPACE}GB"
if [ "$DISK_SPACE" -lt 50 ]; then
    echo -e "${YELLOW}[!] WARNING: Less than 50GB disk space available. 100GB+ recommended.${NC}"
fi

echo -e "${BLUE}[2/8] Installing system dependencies...${NC}"

# Update package manager
case $DISTRO in
    ubuntu|debian)
        sudo apt update
        sudo apt install -y curl wget git build-essential software-properties-common
        ;;
    arch|manjaro)
        sudo pacman -Sy --noconfirm curl wget git base-devel
        ;;
    centos|rhel|fedora)
        sudo dnf install -y curl wget git gcc gcc-c++ make
        ;;
    *)
        echo -e "${RED}[!] Unsupported distribution: $DISTRO${NC}"
        exit 1
        ;;
esac

echo -e "${BLUE}[3/8] Vérification/installation de Python ≥ ${PYTHON_VERSION_LABEL}...${NC}"

if ! detect_python_command; then
    case $DISTRO in
        ubuntu|debian)
            if ! sudo apt install -y python${PYTHON_VERSION_LABEL} python${PYTHON_VERSION_LABEL}-venv python${PYTHON_VERSION_LABEL}-dev python${PYTHON_VERSION_LABEL}-distutils; then
                echo -e "${YELLOW}[!] Python ${PYTHON_VERSION_LABEL} introuvable dans les dépôts par défaut. Ajout du PPA deadsnakes...${NC}"
                if command -v add-apt-repository &> /dev/null; then
                    if sudo add-apt-repository ppa:deadsnakes/ppa -y; then
                        sudo apt update
                    else
                        echo -e "${RED}[!] Impossible d'ajouter le PPA deadsnakes. Installez Python ${PYTHON_VERSION_LABEL} manuellement puis relancez le script.${NC}"
                        exit 1
                    fi
                else
                    echo -e "${RED}[!] L'outil add-apt-repository est indisponible. Installez-le (paquet software-properties-common) ou installez Python ${PYTHON_VERSION_LABEL} manuellement.${NC}"
                    exit 1
                fi
                if ! sudo apt install -y python${PYTHON_VERSION_LABEL} python${PYTHON_VERSION_LABEL}-venv python${PYTHON_VERSION_LABEL}-dev python${PYTHON_VERSION_LABEL}-distutils; then
                    echo -e "${RED}[!] Impossible d'installer Python ${PYTHON_VERSION_LABEL}. Vérifiez l'accès réseau aux dépôts deadsnakes ou installez Python manuellement.${NC}"
                    exit 1
                fi
            fi
            ;;
        arch|manjaro)
            sudo pacman -S --noconfirm python python-pip python-virtualenv
            ;;
        centos|rhel|fedora)
            if ! sudo dnf install -y python${PYTHON_VERSION_LABEL} python${PYTHON_VERSION_LABEL}-devel python${PYTHON_VERSION_LABEL}-pip; then
                echo -e "${YELLOW}[!] Activation du module python:3.11...${NC}"
                sudo dnf module enable -y python:3.11 || true
                if ! sudo dnf install -y python${PYTHON_VERSION_LABEL} python${PYTHON_VERSION_LABEL}-devel python${PYTHON_VERSION_LABEL}-pip; then
                    echo -e "${RED}[!] Impossible d'installer Python ${PYTHON_VERSION_LABEL}. Installez-le manuellement puis relancez le script.${NC}"
                    exit 1
                fi
            fi
            ;;
    esac

    if ! detect_python_command; then
        echo -e "${RED}[!] Python ${PYTHON_VERSION_LABEL} ou supérieur est requis mais reste introuvable.${NC}"
        exit 1
    fi
    echo -e "${GREEN}[✓] Python installé: ${PYTHON_CMD} ${PYTHON_VERSION_DETECTED}${NC}"
else
    echo -e "${GREEN}[✓] Python détecté: ${PYTHON_CMD} ${PYTHON_VERSION_DETECTED}${NC}"
fi

echo -e "${BLUE}[4/8] Installing Node.js $NODE_VERSION...${NC}"

# Install Node.js
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | sudo -E bash -
    case $DISTRO in
        ubuntu|debian)
            sudo apt install -y nodejs
            ;;
        arch|manjaro)
            sudo pacman -S --noconfirm nodejs npm
            ;;
        centos|rhel|fedora)
            sudo dnf install -y nodejs npm
            ;;
    esac
fi

echo -e "${GREEN}[✓] Node.js installed: $(node --version)${NC}"

echo -e "${BLUE}[5/8] Installing Redis...${NC}"

# Install Redis
case $DISTRO in
    ubuntu|debian)
        sudo apt install -y redis-server
        if [[ $SYSTEMCTL_AVAILABLE -eq 1 ]]; then
            sudo systemctl enable redis-server
            sudo systemctl start redis-server
        else
            echo -e "${YELLOW}[!] systemd non détecté, impossible d'activer Redis via systemctl.${NC}"
            echo "    Lancez Redis manuellement après l'installation (ex: redis-server --daemonize yes)."
        fi
        ;;
    arch|manjaro)
        sudo pacman -S --noconfirm redis
        if [[ $SYSTEMCTL_AVAILABLE -eq 1 ]]; then
            sudo systemctl enable redis
            sudo systemctl start redis
        else
            echo -e "${YELLOW}[!] systemd non détecté, impossible d'activer Redis via systemctl.${NC}"
            echo "    Lancez Redis manuellement après l'installation (ex: redis-server --daemonize yes)."
        fi
        ;;
    centos|rhel|fedora)
        sudo dnf install -y redis
        if [[ $SYSTEMCTL_AVAILABLE -eq 1 ]]; then
            sudo systemctl enable redis
            sudo systemctl start redis
        else
            echo -e "${YELLOW}[!] systemd non détecté, impossible d'activer Redis via systemctl.${NC}"
            echo "    Lancez Redis manuellement après l'installation (ex: redis-server --daemonize yes)."
        fi
        ;;
esac

if [[ $SYSTEMCTL_AVAILABLE -eq 1 ]]; then
    echo -e "${GREEN}[✓] Redis installed and started${NC}"
else
    echo -e "${YELLOW}[!] Redis installed. Démarrage manuel requis dans cet environnement sans systemd.${NC}"
fi

echo -e "${BLUE}[6/8] Installing Python dependencies...${NC}"

cd "$SEIDRA_DIR/backend"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "[→] Creating Python virtual environment..."
    $PYTHON_CMD -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
echo "[→] Upgrading pip..."
pip install --upgrade pip

# Install PyTorch with CUDA support
echo "[→] Installing PyTorch with CUDA 12.1..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Install other requirements
echo "[→] Installing backend dependencies..."
pip install -r requirements.txt

# Install advanced machine learning stack (LoRA, SDXL, RTX optimizations)
if [ -f "requirements-ml.txt" ]; then
    echo "[→] Installing advanced ML dependencies..."
    pip install -r requirements-ml.txt
fi

echo -e "${GREEN}[✓] Python dependencies installed${NC}"

echo -e "${BLUE}[7/8] Installing Node.js dependencies...${NC}"

cd "$SEIDRA_DIR/frontend"

# Install frontend dependencies
echo "[→] Installing frontend dependencies..."
npm install

echo -e "${GREEN}[✓] Node.js dependencies installed${NC}"

echo -e "${BLUE}[8/8] Setting up AI models...${NC}"

cd "$SEIDRA_DIR"

# Create directories
mkdir -p models/lora data/media

# Run model setup script
echo "[→] Downloading AI models (this may take 10-15 minutes)..."
cd backend
source venv/bin/activate
python ../scripts/setup-models.py

echo -e "${GREEN}[✓] AI models configured${NC}"

echo -e "${BLUE}[9/9] Final configuration...${NC}"

# Create startup scripts
echo "[→] Creating startup scripts..."

# Create start-backend.sh
cat > start-backend.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")/backend"
source venv/bin/activate
echo "Starting SEIDRA Backend..."
python main.py
EOF

# Create start-frontend.sh
cat > start-frontend.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")/frontend"
echo "Starting SEIDRA Frontend..."
npm run dev
EOF

# Create main startup script
cat > start-seidra.sh << 'EOF'
#!/bin/bash

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo -e "${PURPLE}"
echo "========================================"
echo "   SEIDRA - Build your own myth"
echo "   Starting mystical AI platform..."
echo "========================================"
echo -e "${NC}"

echo -e "${BLUE}[1/3] Starting Redis...${NC}"
if command -v systemctl &> /dev/null && [[ -d /run/systemd/system ]]; then
    sudo systemctl start redis
else
    echo -e "${YELLOW}[!] systemd non détecté : démarrez Redis manuellement (redis-server --daemonize yes).${NC}"
fi

echo -e "${BLUE}[2/3] Starting Backend...${NC}"
gnome-terminal --title="SEIDRA Backend" -- bash -c "./start-backend.sh; exec bash" 2>/dev/null || \
xterm -title "SEIDRA Backend" -e "./start-backend.sh" 2>/dev/null || \
konsole --title "SEIDRA Backend" -e "./start-backend.sh" 2>/dev/null || \
./start-backend.sh &

sleep 5

echo -e "${BLUE}[3/3] Starting Frontend...${NC}"
gnome-terminal --title="SEIDRA Frontend" -- bash -c "./start-frontend.sh; exec bash" 2>/dev/null || \
xterm -title "SEIDRA Frontend" -e "./start-frontend.sh" 2>/dev/null || \
konsole --title "SEIDRA Frontend" -e "./start-frontend.sh" 2>/dev/null || \
./start-frontend.sh &

echo
echo -e "${GREEN}[✓] SEIDRA is starting...${NC}"
echo -e "${BLUE}[→] Backend: http://localhost:8000${NC}"
echo -e "${BLUE}[→] Frontend: http://localhost:3000${NC}"
echo

sleep 3

# Open browser
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:3000
elif command -v open &> /dev/null; then
    open http://localhost:3000
fi
EOF

# Make scripts executable
chmod +x start-backend.sh start-frontend.sh start-seidra.sh

# Test installation
echo "[→] Testing installation..."
cd backend
source venv/bin/activate
python -c "import torch; print('✓ PyTorch:', torch.__version__); print('✓ CUDA available:', torch.cuda.is_available())"

echo
echo -e "${PURPLE}========================================"
echo "   SEIDRA INSTALLATION COMPLETE!"
echo "========================================${NC}"
echo
echo -e "${GREEN}[✓] Backend API ready at: http://localhost:8000${NC}"
echo -e "${GREEN}[✓] Frontend UI ready at: http://localhost:3000${NC}"
echo -e "${GREEN}[✓] AI models configured for RTX 3090${NC}"
echo -e "${GREEN}[✓] Mystical theme activated${NC}"
echo
echo "To start SEIDRA:"
echo "  ./start-seidra.sh"
echo
echo "Or manually:"
echo "  1. ./start-backend.sh"
echo "  2. ./start-frontend.sh"
echo "  3. Open: http://localhost:3000"
echo
echo -e "${PURPLE}Build your own myth! 🌟${NC}"
echo
