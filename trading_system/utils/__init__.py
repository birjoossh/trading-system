"""
Utility modules for the trading system.
"""

from .rest_client import RESTClient, RESTResponse, RESTClientBuilder, create_rest_client, create_rest_client_builder
from .auth_manager import (
    AuthManager, APIKeyAuth, BearerTokenAuth, OAuth2Auth, HMACAuth, 
    CustomHeaderAuth, MultiAuthManager, NoAuth,
    create_api_key_auth, create_bearer_auth, create_oauth2_auth,
    create_hmac_auth, create_custom_auth, create_no_auth
)
# Rate limiter and API client modules not yet implemented
# from .rate_limiter import (
#     RateLimiter, FixedWindowRateLimiter, SlidingWindowRateLimiter,
#     TokenBucketRateLimiter, AdaptiveRateLimiter,
#     create_fixed_window_limiter, create_sliding_window_limiter,
#     create_token_bucket_limiter, create_adaptive_limiter
# )
# from .api_client import APIClient, TradingAPIClient, create_api_client, create_trading_api_client
from .websocket_client import (
    WebSocketClient, WebSocketMessage, ConnectionState
)

__all__ = [
    # REST Client
    'RESTClient', 'RESTResponse', 'RESTClientBuilder', 
    'create_rest_client', 'create_rest_client_builder',
    
    # Authentication
    'AuthManager', 'APIKeyAuth', 'BearerTokenAuth', 'OAuth2Auth', 
    'HMACAuth', 'CustomHeaderAuth', 'MultiAuthManager', 'NoAuth',
    'create_api_key_auth', 'create_bearer_auth', 'create_oauth2_auth',
    'create_hmac_auth', 'create_custom_auth', 'create_no_auth',
    
    # Rate Limiting (not yet implemented)
    # 'RateLimiter', 'FixedWindowRateLimiter', 'SlidingWindowRateLimiter',
    # 'TokenBucketRateLimiter', 'AdaptiveRateLimiter',
    # 'create_fixed_window_limiter', 'create_sliding_window_limiter',
    # 'create_token_bucket_limiter', 'create_adaptive_limiter',
    
    # API Client (not yet implemented)
    # 'APIClient', 'TradingAPIClient', 'create_api_client', 'create_trading_api_client',
    
    # WebSocket Client
    'WebSocketClient', 'WebSocketMessage', 'ConnectionState'
]