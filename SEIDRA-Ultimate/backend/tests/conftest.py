import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Enable the system user fallback in the test environment so existing
# API tests keep operating without real JWT tokens.
os.environ.setdefault("SEIDRA_ALLOW_SYSTEM_FALLBACK", "1")
