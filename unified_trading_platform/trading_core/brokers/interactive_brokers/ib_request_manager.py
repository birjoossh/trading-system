import threading
from concurrent.futures import Future
from typing import Any, Dict, Optional, TypeVar, Union

from unified_trading_platform.trading_core.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

class IBRequestManager:
    """
    Manages asynchronous requests to Interactive Brokers API.
    Maps request IDs (reqId) to Future objects, allowing synchronous-style
    awaiting of async API responses.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._requests: Dict[int, Future] = {}
        # Start reqId from a safe number to avoid conflicts with system IDs
        self._next_req_id = 1000  
        
    def get_new_req_id(self) -> int:
        """Get a thread-safe unique request ID."""
        with self._lock:
            req_id = self._next_req_id
            self._next_req_id += 1
            return req_id

    def create_request(self, req_id: Optional[int] = None) -> Future:
        """
        Create a Future for a specific request ID.
        If req_id is not provided, generates a new one.
        Returns (req_id, Future) tuple.
        """
        with self._lock:
            if req_id is None:
                req_id = self.get_new_req_id()
            
            if req_id in self._requests:
                logger.warning(f"Request ID {req_id} already exists. Overwriting.")
            
            future = Future()
            self._requests[req_id] = future
            return req_id, future

    def get_request(self, req_id: int) -> Optional[Future]:
        """Get the Future associated with a request ID."""
        with self._lock:
            return self._requests.get(req_id)

    def set_result(self, req_id: int, result: Any) -> bool:
        """
        Set the result for a request and remove it from tracking.
        Returns True if successful, False if request not found.
        """
        with self._lock:
            future = self._requests.pop(req_id, None)
            
        if future and not future.done():
            future.set_result(result)
            return True
        return False

    def set_error(self, req_id: int, error: Union[str, Exception]) -> bool:
        """
        Set an exception for a request and remove it from tracking.
        Returns True if successful, False if request not found.
        """
        with self._lock:
            future = self._requests.pop(req_id, None)
        
        if future and not future.done():
            if isinstance(error, str):
                error = Exception(error)
            future.set_exception(error)
            return True
        return False
        
    def clear_all(self):
        """Cancel all pending requests (e.g., on disconnect)."""
        with self._lock:
            for req_id, future in self._requests.items():
                if not future.done():
                    future.set_exception(Exception("RequestManager cleared (disconnected)"))
            self._requests.clear()
