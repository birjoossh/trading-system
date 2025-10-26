# Trading System Utilities

This module provides comprehensive utility classes for HTTP REST API operations, WebSocket connections, authentication, and rate limiting for the trading system.

## Features

### REST Client (`rest_client.py`)
- **GET, POST, PUT, PATCH, DELETE** operations
- **Automatic retry logic** with exponential backoff
- **Authentication** integration
- **Connection pooling** with session management
- **Comprehensive error handling**
- **Builder pattern** for easy configuration

### Authentication Manager (`auth_manager.py`)
- **API Key** authentication
- **Bearer Token** authentication
- **OAuth 2.0** with automatic token refresh
- **HMAC** authentication for secure APIs
- **Custom header** authentication
- **Multiple authentication** methods support

### WebSocket Client (`websocket_client.py`)
- **Real-time** data streaming
- **Automatic reconnection** with exponential backoff
- **Message queuing** during disconnections
- **SSL/TLS** support (wss://)
- **Ping/pong** heartbeat mechanism

### API Client (`api_client.py`)
- **High-level** API client combining REST, auth, and rate limiting
- **Trading-specific** operations (orders, positions, market data)
- **Integrated** error handling and logging

## Quick Start

### Basic REST Client

```python
from trading_system.utils import create_rest_client, create_api_key_auth

# Create authentication
auth = create_api_key_auth("your-api-key", "X-API-Key")

# Create REST client
client = create_rest_client(
    base_url="https://api.example.com",
    auth_manager=auth,
    timeout=30
)

# Make requests
response = client.get("/users/123")
response = client.post("/users", json_data={"name": "John"})
response = client.put("/users/123", json_data={"name": "Jane"})
response = client.patch("/users/123", json_data={"email": "new@email.com"})
response = client.delete("/users/123")

client.close()
```

### WebSocket Client

```python
from trading_system.utils import create_websocket_client

# Create WebSocket client
ws_client = create_websocket_client("wss://stream.example.com")

# Set up event handlers
def on_message(message):
    print(f"Received: {message.data}")

ws_client.set_on_message(on_message)

# Connect and send messages
if ws_client.connect():
    ws_client.send("Hello WebSocket!")
    ws_client.send_json({"type": "subscribe", "symbol": "AAPL"})
```

## Advanced Configuration

### Builder Pattern

```python
from trading_system.utils import create_rest_client_builder

client = (create_rest_client_builder()
          .base_url("https://api.example.com")
          .timeout(60)
          .max_retries(5)
          .retry_delay(2.0)
          .rate_limit(1000)
          .auth_manager(create_bearer_auth("token"))
          .build())
```
### Multiple Authentication

```python
from trading_system.utils import create_api_key_auth, create_bearer_auth, MultiAuthManager

# Multiple authentication methods
auth1 = create_api_key_auth("api-key", "X-API-Key")
auth2 = create_bearer_auth("bearer-token")
multi_auth = MultiAuthManager([auth1, auth2])
```

## Error Handling

All clients provide comprehensive error handling:

```python
response = client.get("/data")

if response.success:
    print(f"Data: {response.data}")
else:
    print(f"Error: {response.error_message}")
    print(f"Status: {response.status_code}")
```

## WebSocket Reconnection

WebSocket clients automatically handle reconnections:

```python
def on_reconnect():
    print("Reconnected!")
    # Resubscribe to data streams
    trading_ws.resubscribe_all()

trading_ws.set_on_reconnect(on_reconnect)
```

## Thread Safety

All utilities are thread-safe and can be used in multi-threaded environments:

```python
import threading

def worker():
    response = client.get("/data")
    print(f"Thread {threading.current_thread().name}: {response.data}")

# Multiple threads can use the same client
threads = [threading.Thread(target=worker) for _ in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

## Logging

All utilities support custom logging:

```python
import logging

logger = logging.getLogger("my_app")
client = create_rest_client(
    base_url="https://api.example.com",
    logger=logger
)
```

## Examples

See `example_usage.py` for comprehensive examples of all utilities.

## Requirements

- Python 3.7+
- requests
- websockets
- asyncio

## Installation

```bash
pip install requests websockets
```

## License

Part of the Trading System project.
