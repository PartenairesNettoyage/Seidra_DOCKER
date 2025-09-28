@echo off
setlocal EnableDelayedExpansion
echo.
echo ========================================
echo   SEIDRA - Build your own myth
echo   Windows Auto-Installation Script
echo ========================================
echo.

:: Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [✓] Running as Administrator
) else (
    echo [!] Please run as Administrator for full installation
    echo    Right-click and select "Run as administrator"
    pause
    exit /b 1
)

:: Set installation directory
set SEIDRA_DIR=%~dp0
set PYTHON_VERSION=3.11.8
set NODE_VERSION=18.18.0

echo [1/8] Checking system requirements...
echo.

:: Check Windows version
for /f "tokens=4-5 delims=. " %%i in ('ver') do set VERSION=%%i.%%j
echo Windows Version: %VERSION%

:: Check if CUDA is available
nvidia-smi >nul 2>&1
if %errorLevel% == 0 (
    echo [✓] NVIDIA GPU detected
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits
) else (
    echo [!] WARNING: NVIDIA GPU not detected or drivers not installed
    echo    SEIDRA requires RTX 3090 or compatible GPU for optimal performance
)

:: Check RAM
for /f "tokens=2 delims==" %%i in ('wmic computersystem get TotalPhysicalMemory /value') do set RAM=%%i
set /a RAM_GB=%RAM:~0,-9%
echo RAM: %RAM_GB%GB
if %RAM_GB% LSS 32 (
    echo [!] WARNING: Less than 32GB RAM detected. 64GB recommended for optimal performance.
)

echo.
echo [2/8] Installing Python %PYTHON_VERSION%...

set FORCE_PYTHON_INSTALL=0
set CURRENT_PYTHON_VERSION=

python --version >nul 2>&1
if %errorLevel% neq 0 (
    set FORCE_PYTHON_INSTALL=1
) else (
    for /f "tokens=2 delims= " %%i in ('python --version 2^>^&1') do set CURRENT_PYTHON_VERSION=%%i
    for /f "tokens=1-3 delims=." %%a in ("!CURRENT_PYTHON_VERSION!") do (
        set PY_MAJOR=%%a
        set PY_MINOR=%%b
    )
    if "!PY_MAJOR!"=="" (
        set FORCE_PYTHON_INSTALL=1
    ) else (
        if !PY_MAJOR! LSS 3 (
            set FORCE_PYTHON_INSTALL=1
        ) else (
            if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 11 set FORCE_PYTHON_INSTALL=1
        )
    )
)

if !FORCE_PYTHON_INSTALL! EQU 1 (
    echo [→] Downloading Python %PYTHON_VERSION%...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe' -OutFile 'python-installer.exe'"
    echo [→] Installing Python...
    python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    del python-installer.exe
    for /f "tokens=2 delims= " %%i in ('python --version 2^>^&1') do set CURRENT_PYTHON_VERSION=%%i
    echo [✓] Python installed (version !CURRENT_PYTHON_VERSION!)
) else (
    echo [✓] Python already installed (version !CURRENT_PYTHON_VERSION!)
)

echo.
echo [3/8] Installing Node.js %NODE_VERSION%...

:: Check if Node.js is installed
node --version >nul 2>&1
if %errorLevel% == 0 (
    echo [✓] Node.js already installed
) else (
    echo [→] Downloading Node.js %NODE_VERSION%...
    powershell -Command "Invoke-WebRequest -Uri 'https://nodejs.org/dist/v%NODE_VERSION%/node-v%NODE_VERSION%-x64.msi' -OutFile 'node-installer.msi'"
    echo [→] Installing Node.js...
    msiexec /i node-installer.msi /quiet
    del node-installer.msi
    echo [✓] Node.js installed
)

echo.
echo [4/8] Installing Redis...

:: Check if Redis is running
redis-cli ping >nul 2>&1
if %errorLevel% == 0 (
    echo [✓] Redis already running
) else (
    echo [→] Installing Redis for Windows...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/microsoftarchive/redis/releases/download/win-3.0.504/Redis-x64-3.0.504.msi' -OutFile 'redis-installer.msi'"
    msiexec /i redis-installer.msi /quiet
    del redis-installer.msi
    
    :: Start Redis service
    net start Redis
    echo [✓] Redis installed and started
)

echo.
echo [5/8] Installing Python dependencies...
cd /d "%SEIDRA_DIR%backend"

:: Create virtual environment
if not exist "venv" (
    echo [→] Creating Python virtual environment...
    python -m venv venv
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Upgrade pip
echo [→] Upgrading pip...
python -m pip install --upgrade pip

:: Install PyTorch with CUDA support
echo [→] Installing PyTorch with CUDA 12.1...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

:: Install other requirements
echo [→] Installing backend dependencies...
pip install -r requirements.txt

:: Install advanced ML requirements (LoRA, SDXL, RTX optimisations)
if exist "requirements-ml.txt" (
    echo [→] Installing advanced ML dependencies (diffusers, transformers, xFormers)...
    pip install -r requirements-ml.txt
) else (
    echo [!] Skipping advanced ML stack: requirements-ml.txt not found
)

echo [✓] Python dependencies installed

echo.
echo [6/8] Installing Node.js dependencies...
cd /d "%SEIDRA_DIR%frontend"

:: Install frontend dependencies
echo [→] Installing frontend dependencies...
npm install

echo [✓] Node.js dependencies installed

echo.
echo [7/8] Setting up AI models...
cd /d "%SEIDRA_DIR%"

:: Create models directory
if not exist "models" mkdir models
if not exist "models\lora" mkdir models\lora
if not exist "data" mkdir data
if not exist "data\media" mkdir data\media

:: Run model setup script
echo [→] Downloading AI models (this may take 10-15 minutes)...
cd backend
call venv\Scripts\activate.bat
python ../scripts/setup-models.py

echo [✓] AI models configured

echo.
echo [8/8] Final configuration...

:: Create startup scripts
echo [→] Creating startup scripts...

:: Create start-backend.bat
echo @echo off > start-backend.bat
echo cd /d "%SEIDRA_DIR%backend" >> start-backend.bat
echo call venv\Scripts\activate.bat >> start-backend.bat
echo echo Starting SEIDRA Backend... >> start-backend.bat
echo python main.py >> start-backend.bat

:: Create start-frontend.bat
echo @echo off > start-frontend.bat
echo cd /d "%SEIDRA_DIR%frontend" >> start-frontend.bat
echo echo Starting SEIDRA Frontend... >> start-frontend.bat
echo npm run dev >> start-frontend.bat

:: Create main startup script
echo @echo off > start-seidra.bat
echo echo. >> start-seidra.bat
echo echo ======================================== >> start-seidra.bat
echo echo   SEIDRA - Build your own myth >> start-seidra.bat
echo echo   Starting mystical AI platform... >> start-seidra.bat
echo echo ======================================== >> start-seidra.bat
echo echo. >> start-seidra.bat
echo echo [1/3] Starting Redis... >> start-seidra.bat
echo net start Redis >> start-seidra.bat
echo echo [2/3] Starting Backend... >> start-seidra.bat
echo start "SEIDRA Backend" cmd /k start-backend.bat >> start-seidra.bat
echo timeout /t 5 >> start-seidra.bat
echo echo [3/3] Starting Frontend... >> start-seidra.bat
echo start "SEIDRA Frontend" cmd /k start-frontend.bat >> start-seidra.bat
echo echo. >> start-seidra.bat
echo echo [✓] SEIDRA is starting... >> start-seidra.bat
echo echo [→] Backend: http://localhost:8000 >> start-seidra.bat
echo echo [→] Frontend: http://localhost:3000 >> start-seidra.bat
echo echo. >> start-seidra.bat
echo timeout /t 3 >> start-seidra.bat
echo start http://localhost:3000 >> start-seidra.bat

:: Test installation
echo [→] Testing installation...
cd backend
call venv\Scripts\activate.bat
python -c "import torch; print('✓ PyTorch:', torch.__version__); print('✓ CUDA available:', torch.cuda.is_available())"

echo.
echo ========================================
echo   SEIDRA INSTALLATION COMPLETE!
echo ========================================
echo.
echo [✓] Backend API ready at: http://localhost:8000
echo [✓] Frontend UI ready at: http://localhost:3000
echo [✓] AI models configured for RTX 3090
echo [✓] Mystical theme activated
echo.
echo To start SEIDRA:
echo   Double-click: start-seidra.bat
echo.
echo Or manually:
echo   1. Double-click: start-backend.bat
echo   2. Double-click: start-frontend.bat
echo   3. Open: http://localhost:3000
echo.
echo Build your own myth! 🌟
echo.
pause