# Unified Trading Platform

This workspace unifies UI, API, and the existing `trading_system` core into a single platform skeleton.

## Structure

- `frontend/` – UI (placeholder)
- `api/` – FastAPI gateway
- `trading_core/` – Thin orchestrator wrapper around existing `trading_system`
- `database/` – ORM models and DB utilities (skeleton)
- `scripts/` – Ops & utilities
- `tests/` – Test suite (placeholder)
- `docs/` – Documentation

## Quick Start

### Prerequisites

- Python 3.9 or higher
- Virtual environment (recommended)

### Step 1: Activate Virtual Environment

If you have an existing virtual environment:

**On macOS/Linux:**
```bash
source venv/bin/activate
```

**On Windows:**
```bash
venv\Scripts\activate
```

If you don't have a virtual environment yet:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 2: Install Dependencies

Make sure all required packages are installed:

```bash
pip install -r requirements.txt
```

This will install:
- FastAPI (for the API framework)
- Uvicorn (for the ASGI server)
- PyYAML (for configuration)
- pandas, numpy (for data processing)
- ibapi (for Interactive Brokers integration)
- Other dependencies

### Step 3: Verify Installation

Test that the API can be imported:

```bash
python -c "from unified_trading_platform.api.main import app; print('✓ API ready')"
```

If this fails, make sure:
- Virtual environment is activated
- All dependencies are installed
- You're in the project root directory

### Step 4: Configure the API (Optional)

Edit `unified_trading_platform/api/api_config.yaml` to customize:
- API metadata (title, description, contact info)
- Default broker settings (host, port, client_id)
- Default contract/order settings (security_type, currency, time_in_force)
- Default data settings (duration, bar_size, market_data_type)
- Default strategy settings (db_path, status)

## Running the API

There are several ways to run the API:

### Method 1: Using the Run Script (Recommended)

**Basic usage:**
```bash
python run_api.py
```

**Development mode with auto-reload:**
```bash
python run_api.py --reload --log-level debug
```

**Custom host and port:**
```bash
python run_api.py --host 127.0.0.1 --port 8080
```

**Production mode with multiple workers:**
```bash
python run_api.py --host 0.0.0.0 --port 8000 --workers 4
```

**Available options:**
- `--host`: Host to bind to (default: 0.0.0.0)
- `--port`: Port number (default: 8000)
- `--reload`: Enable auto-reload for development
- `--workers`: Number of worker processes (default: 1)
- `--log-level`: Log level (critical, error, warning, info, debug, trace)

### Method 2: Using Uvicorn Directly

```bash
uvicorn unified_trading_platform.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Method 3: As a Python Module

```bash
python -m unified_trading_platform.api
```

This runs in development mode with auto-reload on port 8000.

### Method 4: Using Uvicorn with Defaults

```bash
uvicorn unified_trading_platform.api.main:app --reload
```

## Accessing the API

Once the server is running, you can access:

### Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs
  - Interactive API documentation where you can test endpoints
  - Includes request/response examples

- **ReDoc**: http://localhost:8000/redoc
  - Alternative documentation format
  - Better for reading API specifications

### API Endpoints

- **OpenAPI JSON**: http://localhost:8000/api/v1/openapi.json
  - Machine-readable API specification

- **Health Check**: http://localhost:8000/health/ready
  - Verify the API is running

### API Endpoint Groups

The API provides the following endpoint groups:

- `/health` - Health check endpoints
  - Check API availability and status

- `/brokers` - Broker management
  - Connect, disconnect, and manage broker connections
  - Retrieve account information

- `/data` - Market data retrieval
  - Historical data, option chains, real-time subscriptions

- `/orders` - Order management
  - Submit, cancel, and track orders
  - View positions and trade history

- `/strategies` - Strategy execution
  - Initialize, start, stop, and monitor trading strategies
  - View portfolio summaries

See `unified_trading_platform/api/API_SUMMARY.md` for detailed endpoint documentation.

## Quick Start Example

Complete setup and run in one go:

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Install dependencies (if not already installed)
pip install -r requirements.txt

# 3. Run the API
python run_api.py --reload

# 4. Open browser to http://localhost:8000/docs
```

## Development Workflow

For development, use:

```bash
python run_api.py --reload --log-level debug
```

This provides:
- Auto-reload when code changes
- Debug-level logging
- Better error messages

## Production Deployment

For production:

```bash
python run_api.py --host 0.0.0.0 --port 8000 --workers 4
```

Or use a production ASGI server like Gunicorn:

```bash
gunicorn unified_trading_platform.api.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## Testing the API

Once running, test the health endpoint:

```bash
curl http://localhost:8000/health/ready
```

Should return:
```json
{"status": "ok"}
```

## Troubleshooting

### Issue: ModuleNotFoundError (e.g., "No module named 'fastapi'")

**Solution:**
```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
pip list | grep fastapi
```

### Issue: Port Already in Use

**Solution:**
```bash
# Use a different port
python run_api.py --port 8001
```

### Issue: Config File Not Found

**Solution:**
- Ensure `unified_trading_platform/api/api_config.yaml` exists
- Check you're running from the project root directory

### Issue: Import Errors

**Solution:**
- Make sure you're in the project root directory
- Activate the virtual environment
- Verify all dependencies are installed: `pip list | grep fastapi`

### Issue: "No module named 'unified_trading_platform'"

**Solution:**
- Make sure you're running from the project root directory (where `unified_trading_platform/` folder is located)
- Check that the virtual environment is activated
- Try: `python -c "import sys; print(sys.path)"` to verify the project root is in the path

## Next Steps

1. Check the API documentation at http://localhost:8000/docs
2. Review endpoint documentation in `unified_trading_platform/api/API_SUMMARY.md`
3. Connect a broker via `/brokers` endpoint
4. Start using the API endpoints

## Configuration

The API uses `unified_trading_platform/api/api_config.yaml` for all configuration. This includes:

- **API Metadata**: Title, description, version, contact info, license
- **Tag Metadata**: Descriptions for API endpoint groups
- **Default Broker Settings**: Host, port, client_id for broker connections
- **Default Contract/Order Settings**: Security type, currency, time-in-force
- **Default Data Settings**: Duration, bar size, market data type
- **Default Strategy Settings**: Database path, status values
- **Portfolio Defaults**: Initial values for portfolio summaries
- **Allowed Values**: Validation lists for security types, currencies, exchanges, etc.

Changes to the config file take effect on API restart.
