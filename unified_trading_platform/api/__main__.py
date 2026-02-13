"""
Entry point for running the API as a module.
Usage: python -m unified_trading_platform.api
"""

import uvicorn
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    uvicorn.run(
        "unified_trading_platform.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
