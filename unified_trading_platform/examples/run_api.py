#!/usr/bin/env python3
"""
Run script for the Unified Trading Platform API.
"""

import uvicorn
import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from unified_trading_platform.api.main import app

def main():
    """Main entry point for running the API"""
    parser = argparse.ArgumentParser(description="Run the Unified Trading Platform API")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Log level (default: info)",
    )

    args = parser.parse_args()

    print(f"Starting Unified Trading Platform API...")
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Docs: http://{args.host}:{args.port}/docs")
    print(f"ReDoc: http://{args.host}:{args.port}/redoc")
    print(f"API: http://{args.host}:{args.port}/api/v1/openapi.json")
    print(f"Reload: {args.reload}")
    print("-" * 50)

    uvicorn.run(
        "unified_trading_platform.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level=args.log_level,
    )

if __name__ == "__main__":
    main()
