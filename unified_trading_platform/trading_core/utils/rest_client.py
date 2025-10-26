"""
REST API client utility for HTTP operations.
Provides GET, POST, PUT, DELETE operations with proper error handling.
"""

import requests
import json
import time
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass
from datetime import datetime
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@dataclass
class RESTResponse:
    """Response object for REST API calls"""
    status_code: int
    data: Any
    headers: Dict[str, str]
    success: bool
    error_message: Optional[str] = None
    response_time: float = 0.0
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class RESTClient:
    """REST API client with comprehensive error handling and features"""
    
    def __init__(self, 
                 base_url: str = "",
                 timeout: int = 30,
                 max_retries: int = 3,
                 retry_delay: float = 1.0,
                 rate_limit: Optional[int] = None,
                 auth_manager: Optional['AuthManager'] = None,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize REST client
        
        Args:
            base_url: Base URL for all requests
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            retry_delay: Delay between retries in seconds
            rate_limit: Maximum requests per minute (None for no limit)
            auth_manager: Authentication manager instance
            logger: Logger instance
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.rate_limit = rate_limit
        self.auth_manager = auth_manager
        self.logger = logger or logging.getLogger(__name__)
        
        # Session for connection pooling
        self.session = requests.Session()
        
        # Rate limiting
        self._request_times = []
        
        # Default headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'TradingSystem/1.0'
        })
    
    def _check_rate_limit(self):
        """Check if we're within rate limits"""
        if self.rate_limit is None:
            return
        
        current_time = time.time()
        # Remove requests older than 1 minute
        self._request_times = [t for t in self._request_times if current_time - t < 60]
        
        if len(self._request_times) >= self.rate_limit:
            sleep_time = 60 - (current_time - self._request_times[0])
            if sleep_time > 0:
                self.logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
    
    def _make_request(self, 
                      method: str, 
                      url: str, 
                      **kwargs) -> RESTResponse:
        """Make HTTP request with retry logic using tenacity"""
        # Ensure URL is absolute
        if not url.startswith('http'):
            url = f"{self.base_url}/{url.lstrip('/')}"
        
        # Check rate limits
        self._check_rate_limit()
        
        # Add authentication if available
        if self.auth_manager:
            auth_headers = self.auth_manager.get_auth_headers()
            if auth_headers:
                kwargs.setdefault('headers', {}).update(auth_headers)
        
        # Set default timeout
        kwargs.setdefault('timeout', self.timeout)
        
        start_time = time.time()
        
        # Create retry decorator with exponential backoff
        retry_decorator = retry(
            stop=stop_after_attempt(self.max_retries + 1),
            wait=wait_exponential(multiplier=self.retry_delay, min=1, max=60),
            retry=retry_if_exception_type(requests.exceptions.RequestException),
            reraise=True
        )
        
        @retry_decorator
        def _execute_request():
            """Execute the actual HTTP request"""
            self.logger.debug(f"Making {method} request to {url}")
            
            response = self.session.request(method, url, **kwargs)
            
            # Record request time for rate limiting
            self._request_times.append(time.time())
            
            response_time = time.time() - start_time
            
            # Parse response
            try:
                data = response.json()
            except (ValueError, json.JSONDecodeError):
                data = response.text
            
            success = 200 <= response.status_code < 300
            
            result = RESTResponse(
                status_code=response.status_code,
                data=data,
                headers=dict(response.headers),
                success=success,
                error_message=None if success else f"HTTP {response.status_code}",
                response_time=response_time
            )
            
            if success:
                self.logger.debug(f"Request successful: {response.status_code}")
            else:
                self.logger.warning(f"Request failed: {response.status_code} - {data}")
            
            return result
        
        try:
            return _execute_request()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"All retry attempts failed: {e}")
            response_time = time.time() - start_time
            return RESTResponse(
                status_code=0,
                data=None,
                headers={},
                success=False,
                error_message=str(e),
                response_time=response_time
            )
    
    def get(self, 
            url: str, 
            params: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None,
            **kwargs) -> RESTResponse:
        """Make GET request"""
        return self._make_request('GET', url, params=params, headers=headers, **kwargs)
    
    def post(self, 
             url: str, 
             data: Optional[Union[Dict[str, Any], str]] = None,
             json_data: Optional[Dict[str, Any]] = None,
             headers: Optional[Dict[str, str]] = None,
             **kwargs) -> RESTResponse:
        """Make POST request"""
        if json_data is not None:
            kwargs['json'] = json_data
        elif data is not None:
            kwargs['data'] = data
        
        return self._make_request('POST', url, headers=headers, **kwargs)
    
    def put(self, 
            url: str, 
            data: Optional[Union[Dict[str, Any], str]] = None,
            json_data: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None,
            **kwargs) -> RESTResponse:
        """Make PUT request"""
        if json_data is not None:
            kwargs['json'] = json_data
        elif data is not None:
            kwargs['data'] = data
        
        return self._make_request('PUT', url, headers=headers, **kwargs)
    
    def delete(self, 
               url: str, 
               headers: Optional[Dict[str, str]] = None,
               **kwargs) -> RESTResponse:
        """Make DELETE request"""
        return self._make_request('DELETE', url, headers=headers, **kwargs)
    
    def patch(self, 
              url: str, 
              data: Optional[Union[Dict[str, Any], str]] = None,
              json_data: Optional[Dict[str, Any]] = None,
              headers: Optional[Dict[str, str]] = None,
              **kwargs) -> RESTResponse:
        """Make PATCH request"""
        if json_data is not None:
            kwargs['json'] = json_data
        elif data is not None:
            kwargs['data'] = data
        
        return self._make_request('PATCH', url, headers=headers, **kwargs)
    
    def set_auth(self, auth_manager: 'AuthManager'):
        """Set authentication manager"""
        self.auth_manager = auth_manager
    
    def set_base_url(self, base_url: str):
        """Set base URL"""
        self.base_url = base_url.rstrip('/')
    
    def add_header(self, key: str, value: str):
        """Add default header"""
        self.session.headers[key] = value
    
    def remove_header(self, key: str):
        """Remove default header"""
        self.session.headers.pop(key, None)
    
    def close(self):
        """Close the session"""
        self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class RESTClientBuilder:
    """Builder pattern for REST client configuration"""
    
    def __init__(self):
        self._config = {}
    
    def base_url(self, url: str) -> 'RESTClientBuilder':
        """Set base URL"""
        self._config['base_url'] = url
        return self
    
    def timeout(self, seconds: int) -> 'RESTClientBuilder':
        """Set timeout"""
        self._config['timeout'] = seconds
        return self
    
    def max_retries(self, count: int) -> 'RESTClientBuilder':
        """Set max retries"""
        self._config['max_retries'] = count
        return self
    
    def retry_delay(self, seconds: float) -> 'RESTClientBuilder':
        """Set retry delay"""
        self._config['retry_delay'] = seconds
        return self
    
    def rate_limit(self, requests_per_minute: int) -> 'RESTClientBuilder':
        """Set rate limit"""
        self._config['rate_limit'] = requests_per_minute
        return self
    
    def auth_manager(self, auth_manager: 'AuthManager') -> 'RESTClientBuilder':
        """Set auth manager"""
        self._config['auth_manager'] = auth_manager
        return self
    
    def logger(self, logger: logging.Logger) -> 'RESTClientBuilder':
        """Set logger"""
        self._config['logger'] = logger
        return self
    
    def build(self) -> RESTClient:
        """Build REST client"""
        return RESTClient(**self._config)


# Convenience functions
def create_rest_client(base_url: str = "", **kwargs) -> RESTClient:
    """Create a REST client with default configuration"""
    return RESTClient(base_url=base_url, **kwargs)

def create_rest_client_builder() -> RESTClientBuilder:
    """Create a REST client builder"""
    return RESTClientBuilder()
