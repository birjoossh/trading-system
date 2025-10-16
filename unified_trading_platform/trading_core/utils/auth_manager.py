"""
Authentication manager for REST API clients.
Supports various authentication methods including API keys, OAuth, and custom headers.
"""

import time
import hashlib
import hmac
import base64
from typing import Dict, Any, Optional, Callable
from abc import ABC, abstractmethod
import logging

class AuthManager(ABC):
    """Abstract base class for authentication managers"""
    
    @abstractmethod
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        pass
    
    @abstractmethod
    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        pass
    
    @abstractmethod
    def refresh_auth(self) -> bool:
        """Refresh authentication if needed"""
        pass

class APIKeyAuth(AuthManager):
    """API Key authentication"""
    
    def __init__(self, api_key: str, header_name: str = "X-API-Key"):
        self.api_key = api_key
        self.header_name = header_name
        self.logger = logging.getLogger(__name__)
    
    def get_auth_headers(self) -> Dict[str, str]:
        return {self.header_name: self.api_key}
    
    def is_authenticated(self) -> bool:
        return bool(self.api_key)
    
    def refresh_auth(self) -> bool:
        return True  # API keys don't need refresh

class BearerTokenAuth(AuthManager):
    """Bearer token authentication"""
    
    def __init__(self, token: str, token_type: str = "Bearer"):
        self.token = token
        self.token_type = token_type
        self.logger = logging.getLogger(__name__)
    
    def get_auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"{self.token_type} {self.token}"}
    
    def is_authenticated(self) -> bool:
        return bool(self.token)
    
    def refresh_auth(self) -> bool:
        return True  # Static tokens don't need refresh

class OAuth2Auth(AuthManager):
    """OAuth 2.0 authentication with automatic token refresh"""
    
    def __init__(self, 
                 client_id: str,
                 client_secret: str,
                 token_url: str,
                 scope: Optional[str] = None,
                 token_refresh_callback: Optional[Callable] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.scope = scope
        self.token_refresh_callback = token_refresh_callback
        
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = 0
        self.logger = logging.getLogger(__name__)
    
    def get_auth_headers(self) -> Dict[str, str]:
        if not self.is_authenticated():
            return {}
        
        return {"Authorization": f"Bearer {self.access_token}"}
    
    def is_authenticated(self) -> bool:
        return (self.access_token is not None and 
                time.time() < self.token_expires_at)
    
    def refresh_auth(self) -> bool:
        """Refresh OAuth token"""
        if not self.refresh_token:
            self.logger.error("No refresh token available")
            return False
        
        try:
            # This would typically make a request to the token endpoint
            # For now, we'll use a callback if provided
            if self.token_refresh_callback:
                return self.token_refresh_callback(self)
            
            # Default implementation would go here
            self.logger.warning("OAuth token refresh not implemented")
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to refresh OAuth token: {e}")
            return False

class HMACAuth(AuthManager):
    """HMAC authentication for secure API access"""
    
    def __init__(self, 
                 api_key: str, 
                 secret_key: str,
                 header_name: str = "X-API-Key",
                 signature_header: str = "X-Signature",
                 timestamp_header: str = "X-Timestamp"):
        self.api_key = api_key
        self.secret_key = secret_key
        self.header_name = header_name
        self.signature_header = signature_header
        self.timestamp_header = timestamp_header
        self.logger = logging.getLogger(__name__)
    
    def get_auth_headers(self) -> Dict[str, str]:
        timestamp = str(int(time.time()))
        signature = self._generate_signature(timestamp)
        
        return {
            self.header_name: self.api_key,
            self.signature_header: signature,
            self.timestamp_header: timestamp
        }
    
    def _generate_signature(self, timestamp: str) -> str:
        """Generate HMAC signature"""
        message = f"{self.api_key}{timestamp}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def is_authenticated(self) -> bool:
        return bool(self.api_key and self.secret_key)
    
    def refresh_auth(self) -> bool:
        return True  # HMAC doesn't need refresh

class CustomHeaderAuth(AuthManager):
    """Custom header authentication"""
    
    def __init__(self, headers: Dict[str, str]):
        self.headers = headers
        self.logger = logging.getLogger(__name__)
    
    def get_auth_headers(self) -> Dict[str, str]:
        return self.headers.copy()
    
    def is_authenticated(self) -> bool:
        return bool(self.headers)
    
    def refresh_auth(self) -> bool:
        return True  # Custom headers don't need refresh

class MultiAuthManager(AuthManager):
    """Multiple authentication methods"""
    
    def __init__(self, auth_managers: list[AuthManager]):
        self.auth_managers = auth_managers
        self.logger = logging.getLogger(__name__)
    
    def get_auth_headers(self) -> Dict[str, str]:
        headers = {}
        for auth_manager in self.auth_managers:
            if auth_manager.is_authenticated():
                headers.update(auth_manager.get_auth_headers())
        return headers
    
    def is_authenticated(self) -> bool:
        return any(auth_manager.is_authenticated() for auth_manager in self.auth_managers)
    
    def refresh_auth(self) -> bool:
        success = False
        for auth_manager in self.auth_managers:
            if auth_manager.refresh_auth():
                success = True
        return success

class NoAuth(AuthManager):
    """No authentication"""
    
    def get_auth_headers(self) -> Dict[str, str]:
        return {}
    
    def is_authenticated(self) -> bool:
        return True  # No auth means always "authenticated"
    
    def refresh_auth(self) -> bool:
        return True

# Factory functions
def create_api_key_auth(api_key: str, header_name: str = "X-API-Key") -> APIKeyAuth:
    """Create API key authentication"""
    return APIKeyAuth(api_key, header_name)

def create_bearer_auth(token: str, token_type: str = "Bearer") -> BearerTokenAuth:
    """Create bearer token authentication"""
    return BearerTokenAuth(token, token_type)

def create_oauth2_auth(client_id: str, 
                      client_secret: str, 
                      token_url: str,
                      scope: Optional[str] = None) -> OAuth2Auth:
    """Create OAuth 2.0 authentication"""
    return OAuth2Auth(client_id, client_secret, token_url, scope)

def create_hmac_auth(api_key: str, 
                    secret_key: str,
                    header_name: str = "X-API-Key",
                    signature_header: str = "X-Signature") -> HMACAuth:
    """Create HMAC authentication"""
    return HMACAuth(api_key, secret_key, header_name, signature_header)

def create_custom_auth(headers: Dict[str, str]) -> CustomHeaderAuth:
    """Create custom header authentication"""
    return CustomHeaderAuth(headers)

def create_no_auth() -> NoAuth:
    """Create no authentication"""
    return NoAuth()
