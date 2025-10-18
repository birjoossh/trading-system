"""
Example usage of the trading system utility classes.
Demonstrates REST client, WebSocket client, authentication, and rate limiting.
"""

import time
import logging
from typing import Dict, Any
from trading_core.utils import (
    # REST Client
    create_rest_client, create_rest_client_builder,
    # Authentication
    create_api_key_auth, create_bearer_auth, create_hmac_auth,
    # Rate Limiting
    create_sliding_window_limiter, create_adaptive_limiter,
    # API Client
    create_api_client, create_trading_api_client,
    # WebSocket Client
    create_websocket_client, create_trading_websocket_client,
    WebSocketMessage
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def example_rest_client():
    """Example of using REST client with authentication and rate limiting"""
    print("\n=== REST Client Example ===")
    
    # Create authentication
    auth = create_api_key_auth("your-api-key", "X-API-Key")
    
    # Create rate limiter (100 requests per minute)
    rate_limiter = create_sliding_window_limiter(100, 60)
    
    # Create REST client
    client = create_rest_client(
        base_url="https://api.example.com",
        auth_manager=auth,
        rate_limiter=rate_limiter,
        timeout=30,
        max_retries=3
    )
    
    try:
        # GET request
        response = client.get("/users/123")
        print(f"GET Response: {response.status_code} - {response.data}")
        
        # POST request with JSON data
        user_data = {
            "name": "John Doe",
            "email": "john@example.com",
            "age": 30
        }
        response = client.post("/users", json_data=user_data)
        print(f"POST Response: {response.status_code} - {response.data}")
        
        # PUT request (replace entire resource)
        updated_user = {
            "name": "John Smith",
            "email": "john.smith@example.com",
            "age": 31,
            "address": "123 Main St"
        }
        response = client.put("/users/123", json_data=updated_user)
        print(f"PUT Response: {response.status_code} - {response.data}")
        
        # PATCH request (partial update)
        patch_data = {"email": "newemail@example.com"}
        response = client.patch("/users/123", json_data=patch_data)
        print(f"PATCH Response: {response.status_code} - {response.data}")
        
        # DELETE request
        response = client.delete("/users/123")
        print(f"DELETE Response: {response.status_code} - {response.data}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

def example_trading_api_client():
    """Example of using trading API client"""
    print("\n=== Trading API Client Example ===")
    
    # Create authentication for trading API
    auth = create_hmac_auth("api-key", "secret-key")
    
    # Create rate limiter for trading (more restrictive)
    rate_limiter = create_adaptive_limiter(50, 60, min_requests=1, max_requests=200)
    
    # Create trading API client
    trading_client = create_trading_api_client(
        base_url="https://api.trading.com",
        auth_manager=auth,
        rate_limiter=rate_limiter
    )
    
    try:
        # Get account info
        response = trading_client.get_account_info()
        print(f"Account Info: {response.status_code} - {response.data}")
        
        # Get positions
        response = trading_client.get_positions()
        print(f"Positions: {response.status_code} - {response.data}")
        
        # Submit order
        order_data = {
            "symbol": "AAPL",
            "quantity": 100,
            "side": "buy",
            "type": "limit",
            "price": 150.00
        }
        response = trading_client.submit_order(order_data)
        print(f"Order Submitted: {response.status_code} - {response.data}")
        
        # Get market data
        response = trading_client.get_market_data("AAPL")
        print(f"Market Data: {response.status_code} - {response.data}")
        
        # Get historical data
        response = trading_client.get_historical_data(
            "AAPL", "2024-01-01", "2024-01-31", "1d"
        )
        print(f"Historical Data: {response.status_code} - {response.data}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        trading_client.close()

def example_websocket_client():
    """Example of using WebSocket client"""
    print("\n=== WebSocket Client Example ===")
    
    # Create WebSocket client
    ws_client = create_websocket_client("wss://echo.websocket.org")
    
    # Set up event handlers
    def on_connect():
        print("WebSocket connected!")
    
    def on_disconnect():
        print("WebSocket disconnected!")
    
    def on_message(message: WebSocketMessage):
        print(f"Received message: {message.data}")
    
    def on_error(error: Exception):
        print(f"WebSocket error: {error}")
    
    ws_client.set_on_connect(on_connect)
    ws_client.set_on_disconnect(on_disconnect)
    ws_client.set_on_message(on_message)
    ws_client.set_on_error(on_error)
    
    try:
        # Connect
        if ws_client.connect():
            print("Connected to WebSocket")
            
            # Send some messages
            ws_client.send_text("Hello WebSocket!")
            ws_client.send_json({"type": "test", "message": "JSON message"})
            
            # Wait for responses
            time.sleep(2)
            
            # Disconnect
            ws_client.disconnect()
            print("Disconnected from WebSocket")
        else:
            print("Failed to connect to WebSocket")
            
    except Exception as e:
        print(f"Error: {e}")

def example_trading_websocket_client():
    """Example of using trading WebSocket client"""
    print("\n=== Trading WebSocket Client Example ===")
    
    # Create trading WebSocket client
    trading_ws = create_trading_websocket_client("wss://stream.trading.com")
    
    def on_connect():
        print("Trading WebSocket connected!")
        # Subscribe to quotes and trades
        trading_ws.subscribe_to_quotes(["AAPL", "MSFT", "GOOGL"])
        trading_ws.subscribe_to_trades(["AAPL", "MSFT"])
    
    def on_disconnect():
        print("Trading WebSocket disconnected!")
    
    def on_message(message: WebSocketMessage):
        print(f"Trading data: {message.data}")
    
    def on_reconnect():
        print("Reconnecting...")
        # Resubscribe to all previous subscriptions
        trading_ws.resubscribe_all()
    
    trading_ws.set_on_connect(on_connect)
    trading_ws.set_on_disconnect(on_disconnect)
    trading_ws.set_on_message(on_message)
    trading_ws.set_on_reconnect(on_reconnect)
    
    try:
        # Connect
        if trading_ws.connect():
            print("Connected to trading WebSocket")
            
            # Wait for some data
            time.sleep(5)
            
            # Unsubscribe from some symbols
            trading_ws.unsubscribe_from_quotes(["GOOGL"])
            
            # Wait a bit more
            time.sleep(2)
            
            # Disconnect
            trading_ws.disconnect()
            print("Disconnected from trading WebSocket")
        else:
            print("Failed to connect to trading WebSocket")
            
    except Exception as e:
        print(f"Error: {e}")

def example_advanced_rest_client():
    """Example of advanced REST client configuration"""
    print("\n=== Advanced REST Client Example ===")
    
    # Create client using builder pattern
    client = (create_rest_client_builder()
              .base_url("https://api.advanced.com")
              .timeout(60)
              .max_retries(5)
              .retry_delay(2.0)
              .rate_limit(1000)  # 1000 requests per minute
              .auth_manager(create_bearer_auth("your-token"))
              .logger(logger)
              .build())
    
    try:
        # Make requests with custom headers
        response = client.get("/data", headers={"X-Custom-Header": "value"})
        print(f"Advanced GET: {response.status_code}")
        
        # Make request with query parameters
        response = client.get("/search", params={"q": "trading", "limit": 10})
        print(f"Search: {response.status_code}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

def example_rate_limiting():
    """Example of different rate limiting strategies"""
    print("\n=== Rate Limiting Example ===")
    
    # Fixed window rate limiter
    fixed_limiter = create_sliding_window_limiter(10, 60)  # 10 requests per minute
    
    # Adaptive rate limiter
    adaptive_limiter = create_adaptive_limiter(50, 60, min_requests=1, max_requests=200)
    
    print("Testing rate limiters...")
    
    # Test fixed window limiter
    for i in range(15):
        if fixed_limiter.acquire():
            print(f"Fixed limiter: Request {i+1} allowed")
        else:
            print(f"Fixed limiter: Request {i+1} blocked")
    
    print(f"Remaining requests: {fixed_limiter.get_remaining_requests()}")
    
    # Test adaptive limiter
    for i in range(5):
        if adaptive_limiter.acquire():
            print(f"Adaptive limiter: Request {i+1} allowed")
            # Simulate response time
            adaptive_limiter.record_response_time("default", 0.5)  # Fast response
        else:
            print(f"Adaptive limiter: Request {i+1} blocked")

def main():
    """Run all examples"""
    print("Trading System Utilities Examples")
    print("=" * 50)
    
    # Run examples
    example_rest_client()
    example_trading_api_client()
    example_websocket_client()
    example_trading_websocket_client()
    example_advanced_rest_client()
    example_rate_limiting()
    
    print("\nAll examples completed!")

if __name__ == "__main__":
    main()