"""
WebSocket client utility for real-time data streaming.
Provides connection management, message handling, and reconnection logic.
"""

import asyncio
import websockets
import json
import time
import threading
import logging
from typing import Dict, Any, Optional, Callable, List, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import ssl
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, AsyncRetrying

# Import websockets exceptions properly
try:
    from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI
except ImportError:
    # Fallback for older versions or different exception structure
    try:
        from websockets import ConnectionClosed, InvalidHandshake, InvalidURI
    except ImportError:
        # Define fallback exceptions if websockets doesn't have them
        class ConnectionClosed(Exception):
            pass
        class InvalidHandshake(Exception):
            pass
        class InvalidURI(Exception):
            pass

class ConnectionState(Enum):
    """WebSocket connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"

@dataclass
class WebSocketMessage:
    """WebSocket message wrapper"""
    data: Any
    message_type: str = "text"
    timestamp: datetime = None
    connection_id: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class WebSocketClient:
    """Generic WebSocket client with reconnection and message handling"""
    
    def __init__(self, 
                 uri: str,
                 auto_reconnect: bool = True,
                 max_reconnect_attempts: int = 10,
                 reconnect_delay: float = 1.0,
                 max_reconnect_delay: float = 60.0,
                 ping_interval: float = 20.0,
                 ping_timeout: float = 10.0,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize WebSocket client
        
        Args:
            uri: WebSocket URI (ws:// or wss://)
            auto_reconnect: Enable automatic reconnection
            max_reconnect_attempts: Maximum reconnection attempts (0 = unlimited)
            reconnect_delay: Initial delay between reconnection attempts
            max_reconnect_delay: Maximum delay between reconnection attempts
            ping_interval: Interval for ping messages
            ping_timeout: Timeout for ping responses
            logger: Logger instance
        """
        self.uri = uri
        self.auto_reconnect = auto_reconnect
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.logger = logger or logging.getLogger(__name__)
        
        # Connection state
        self.state = ConnectionState.DISCONNECTED
        self.websocket = None
        self.connection_id = None
        
        # Event handlers
        self.on_connect: Optional[Callable] = None
        self.on_disconnect: Optional[Callable] = None
        self.on_message: Optional[Callable[[WebSocketMessage], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        self.on_reconnect: Optional[Callable] = None
        
        # Reconnection state
        self.reconnect_attempts = 0
        self.current_reconnect_delay = reconnect_delay
        
        # Threading
        self._loop = None
        self._thread = None
        self._stop_event = threading.Event()
        self._reconnect_task = None
        
        # Message queue for reconnection
        self._message_queue: List[Any] = []
        self._queue_lock = threading.Lock()
    
    def set_on_connect(self, callback: Callable):
        """Set connection callback"""
        self.on_connect = callback
    
    def set_on_disconnect(self, callback: Callable):
        """Set disconnection callback"""
        self.on_disconnect = callback
    
    def set_on_message(self, callback: Callable[[WebSocketMessage], None]):
        """Set message callback"""
        self.on_message = callback
    
    def set_on_error(self, callback: Callable[[Exception], None]):
        """Set error callback"""
        self.on_error = callback
    
    def set_on_reconnect(self, callback: Callable):
        """Set reconnection callback"""
        self.on_reconnect = callback
    
    def connect(self) -> bool:
        """Connect to WebSocket server"""
        if self.state == ConnectionState.CONNECTED:
            self.logger.warning("Already connected")
            return True
        
        if self.state == ConnectionState.CONNECTING:
            self.logger.warning("Connection already in progress")
            return False
        
        self.state = ConnectionState.CONNECTING
        self._stop_event.clear()
        
        # Start event loop in separate thread
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
        
        # Wait for connection
        timeout = 10
        start_time = time.time()
        while self.state == ConnectionState.CONNECTING and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        return self.state == ConnectionState.CONNECTED
    
    def disconnect(self):
        """Disconnect from WebSocket server"""
        self.logger.info("Disconnecting from WebSocket")
        self.state = ConnectionState.DISCONNECTED
        self._stop_event.set()
        
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._close_connection(), self._loop)
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
    
    def send(self, message: Union[str, dict, bytes]) -> bool:
        """Send message to WebSocket server"""
        if self.state != ConnectionState.CONNECTED:
            self.logger.warning("Not connected, queuing message")
            with self._queue_lock:
                self._message_queue.append(message)
            return False
        
        try:
            if isinstance(message, dict):
                message = json.dumps(message)
            elif isinstance(message, bytes):
                pass  # Send as binary
            else:
                message = str(message)
            
            if self._loop and not self._loop.is_closed():
                asyncio.run_coroutine_threadsafe(self._send_message(message), self._loop)
                return True
            else:
                self.logger.error("Event loop not available")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            if self.on_error:
                self.on_error(e)
            return False
    
    def send_json(self, data: dict) -> bool:
        """Send JSON message"""
        return self.send(data)
    
    def send_text(self, text: str) -> bool:
        """Send text message"""
        return self.send(text)
    
    def send_binary(self, data: bytes) -> bool:
        """Send binary message"""
        return self.send(data)
    
    def is_connected(self) -> bool:
        """Check if connected"""
        return self.state == ConnectionState.CONNECTED
    
    def get_connection_id(self) -> Optional[str]:
        """Get connection ID"""
        return self.connection_id
    
    def _run_event_loop(self):
        """Run asyncio event loop in separate thread"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        try:
            self._loop.run_until_complete(self._connect_and_run())
        except Exception as e:
            self.logger.error(f"Event loop error: {e}")
            if self.on_error:
                self.on_error(e)
        finally:
            self._loop.close()
    
    async def _connect_and_run(self):
        """Connect and run WebSocket client with tenacity retry logic"""
        while not self._stop_event.is_set():
            try:
                if not self.auto_reconnect:
                    # Single connection attempt without retry
                    await self._single_connection_attempt()
                    break  # Exit after single attempt
                else:
                    # Use tenacity for automatic reconnection
                    await self._connect_with_tenacity()
                    break  # Exit after successful connection
                    
            except Exception as e:
                self.logger.error(f"Connection failed: {e}")
                if not self.auto_reconnect:
                    break
                # For auto-reconnect, wait a bit before trying again
                self.logger.info("Waiting before retry...")
                await asyncio.sleep(1)
    
    async def _single_connection_attempt(self):
        """Single connection attempt without retry"""
        try:
            await self._establish_connection()
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.state = ConnectionState.ERROR
            if self.on_error:
                try:
                    self.on_error(e)
                except Exception as callback_error:
                    self.logger.error(f"Error in on_error callback: {callback_error}")
    
    async def _connect_with_tenacity(self):
        """Connect with tenacity retry logic"""
        # Configure retry strategy
        max_attempts = self.max_reconnect_attempts if self.max_reconnect_attempts > 0 else None
        stop_strategy = stop_after_attempt(max_attempts) if max_attempts else None
        
        # Create async retry decorator
        retry_decorator = AsyncRetrying(
            stop=stop_strategy,
            wait=wait_exponential(
                multiplier=self.reconnect_delay,
                min=1,
                max=self.max_reconnect_delay
            ),
            retry=retry_if_exception_type((
                ConnectionClosed,
                InvalidHandshake,
                InvalidURI,
                OSError,
                ConnectionError
            )),
            reraise=True
        )
        
        async for attempt in retry_decorator:
            try:
                with attempt:
                    await self._establish_connection()
                    # If we get here, connection was successful
                    return
            except Exception as e:
                self.logger.warning(f"Connection attempt {attempt.retry_state.attempt_number} failed: {e}")
                self.state = ConnectionState.RECONNECTING
                self.reconnect_attempts = attempt.retry_state.attempt_number
                
                # Trigger reconnect callback
                if self.on_reconnect:
                    try:
                        self.on_reconnect()
                    except Exception as callback_error:
                        self.logger.error(f"Error in on_reconnect callback: {callback_error}")
                
                # If this is the last attempt, handle final failure
                if attempt.retry_state.attempt_number >= (max_attempts or float('inf')):
                    self.logger.error("Maximum reconnection attempts reached")
                    self.state = ConnectionState.ERROR
                    if self.on_error:
                        try:
                            self.on_error(e)
                        except Exception as callback_error:
                            self.logger.error(f"Error in on_error callback: {callback_error}")
                    break
    
    async def _establish_connection(self):
        """Establish WebSocket connection"""
        if self._stop_event.is_set():
            return
            
        self.logger.info(f"Connecting to {self.uri}")
        self.state = ConnectionState.CONNECTING
        
        # Create SSL context for wss://
        ssl_context = None
        if self.uri.startswith('wss://'):
            ssl_context = ssl.create_default_context()
        
        # Connect to WebSocket
        websocket = await websockets.connect(
            self.uri,
            ssl=ssl_context,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
            close_timeout=10
        )
        
        try:
            self.websocket = websocket
            self.state = ConnectionState.CONNECTED
            self.connection_id = f"ws_{int(time.time())}"
            self.reconnect_attempts = 0
            self.current_reconnect_delay = self.reconnect_delay
            
            self.logger.info("WebSocket connected")
            
            # Send queued messages
            await self._send_queued_messages()
            
            # Trigger connect callback
            if self.on_connect:
                try:
                    self.on_connect()
                except Exception as e:
                    self.logger.error(f"Error in on_connect callback: {e}")
            
            # Listen for messages - this will run until connection is closed or stop_event is set
            await self._listen_for_messages()
            
        except ConnectionClosed as e:
            self.logger.info(f"Connection closed during message listening: {e}")
            self.state = ConnectionState.DISCONNECTED
            if self.on_disconnect:
                try:
                    self.on_disconnect()
                except Exception as callback_error:
                    self.logger.error(f"Error in on_disconnect callback: {callback_error}")
            # Re-raise to trigger reconnection logic
            raise
        except Exception as e:
            self.logger.error(f"Error during connection: {e}")
            self.state = ConnectionState.ERROR
            if self.on_error:
                try:
                    self.on_error(e)
                except Exception as callback_error:
                    self.logger.error(f"Error in on_error callback: {callback_error}")
            # Re-raise to trigger reconnection logic
            raise
        finally:
            # Close the connection when done
            if websocket and not (hasattr(websocket, 'closed') and websocket.closed):
                await websocket.close()
    
    async def _listen_for_messages(self):
        """Listen for incoming messages"""
        try:
            self.logger.info("Starting message listener...")
            
            async for message in self.websocket:
                if self._stop_event.is_set():
                    self.logger.info("Stop event set, exiting message listener")
                    break
                
                # Create message wrapper
                ws_message = WebSocketMessage(
                    data=message,
                    message_type="text" if isinstance(message, str) else "binary",
                    connection_id=self.connection_id
                )
                
                # Trigger message callback
                if self.on_message:
                    try:
                        self.on_message(ws_message)
                    except Exception as e:
                        self.logger.error(f"Error in on_message callback: {e}")
            
            self.logger.info("Message listener loop ended")
                        
        except ConnectionClosed as e:
            self.logger.info(f"Connection closed during message listening: {e}")
            raise  # Re-raise to trigger reconnection
        except Exception as e:
            self.logger.error(f"Error listening for messages: {e}")
            raise  # Re-raise to trigger reconnection
    
    async def _send_message(self, message: Union[str, bytes]):
        """Send message through WebSocket"""
        if self.websocket and not (hasattr(self.websocket, 'closed') and self.websocket.closed):
            await self.websocket.send(message)
        else:
            self.logger.warning("WebSocket not available for sending")
    
    async def _send_queued_messages(self):
        """Send queued messages after reconnection"""
        with self._queue_lock:
            if self._message_queue:
                self.logger.info(f"Sending {len(self._message_queue)} queued messages")
                for message in self._message_queue:
                    await self._send_message(message)
                self._message_queue.clear()
    
    
    async def _close_connection(self):
        """Close WebSocket connection"""
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()

# Example usage
if __name__ == "__main__":
    # Example usage
    def on_message(message: WebSocketMessage):
        print(f"Received: {message.data}")
    
    def on_connect():
        print("Connected to WebSocket")
    
    def on_disconnect():
        print("Disconnected from WebSocket")
    
    # Create client
    client = WebSocketClient("wss://echo.websocket.org")
    client.set_on_message(on_message)
    client.set_on_connect(on_connect)
    client.set_on_disconnect(on_disconnect)
    
    # Connect and send message
    if client.connect():
        for _ in range(1000):
            print("sending msg ...")
            client.send("Hello WebSocket!")
            time.sleep(1)
        client.disconnect()
