# API Endpoints Summary

This document provides an overview of all available API endpoints in the Unified Trading Platform.

## Base URL

All endpoints are prefixed with the base API path. The API uses FastAPI with automatic OpenAPI documentation available at `/docs`.

## Data Models

All endpoints use consistent request/response models defined in `api/models.py`:
- **ErrorResponse**: Standard error format
- **SuccessResponse**: Standard success format
- **ContractRequest/ContractInfo**: Contract specifications
- **OrderRequest/OrderResponse/OrderInfo**: Order management
- **PositionInfo**: Position information
- **TradeInfo**: Trade execution details
- **StrategyStatusResponse**: Strategy status
- **PortfolioSummaryResponse**: Portfolio summary

## Endpoint Groups

### 1. Health (`/health`)
- `GET /health/ready` - Check if API is ready
- `GET /health/live` - Check if API is live

### 2. Brokers (`/brokers`)
Manages broker connections and account information.

- `GET /brokers` - List all registered brokers
- `POST /brokers` - Add and connect a new broker
  - Body: `AddBrokerRequest` (name, broker_type, host, port, client_id, config)
- `GET /brokers/{broker_name}` - Get information about a specific broker
- `DELETE /brokers/{broker_name}` - Remove and disconnect a broker
- `GET /brokers/{broker_name}/account` - Get account information for a broker

### 3. Data (`/data`)
Handles market data retrieval, subscriptions, and option chains.

- `POST /data/historical` - Get historical bar data
  - Body: `HistoricalDataRequest` (symbol, exchange, duration, bar_size, security_type, currency, broker_name)
  - Returns: `HistoricalDataResponse` with bar data array
- `POST /data/option-chain` - Get option chain for an underlying symbol
  - Body: `OptionChainRequest` (symbol, exchange, security_type, currency, broker_name)
  - Returns: `OptionChainInfo` with expiration dates and strikes
- `POST /data/subscribe` - Subscribe to real-time market data
  - Body: `MarketDataSubscriptionRequest` (symbol, exchange, security_type, currency, broker_name, market_data_type, snapshot)
  - Returns: `MarketDataSubscriptionResponse` with subscription_id

### 4. Orders (`/orders`)
Manages order submission, cancellation, status checking, and positions.

#### Order Submission
- `POST /orders/market` - Submit a market order
  - Body: `MarketOrderRequest` (symbol, exchange, action, quantity, broker_name, security_type, currency, account, time_in_force)
- `POST /orders/limit` - Submit a limit order
  - Body: `LimitOrderRequest` (includes limit_price)
- `POST /orders/stop` - Submit a stop order
  - Body: `StopOrderRequest` (includes stop_price)
- `POST /orders/stop-limit` - Submit a stop-limit order
  - Body: `StopLimitOrderRequest` (includes stop_price and limit_price)

#### Order Management
- `GET /orders` - Get all orders
- `GET /orders/{order_id}` - Get status of a specific order
- `DELETE /orders/{order_id}` - Cancel an order

#### History
- `GET /orders/history/orders` - Get order history
  - Query params: `symbol`, `start_date`, `end_date` (optional)
- `GET /orders/history/trades` - Get trade history
  - Query params: `symbol`, `start_date`, `end_date` (optional)

#### Positions
- `GET /orders/positions` - Get current positions
  - Query params: `broker_name` (optional)

### 5. Strategies (`/strategies`)
Manages strategy initialization, execution, status, and portfolio tracking.

- `POST /strategies/initialize` - Initialize a strategy for execution
  - Body: `StrategyInitializeRequest` (broker_name, exchange, strategy_name, start_date, end_date, db_path)
  - Returns: `StrategyStatusResponse` with run_id
- `POST /strategies/{run_id}/start` - Start strategy execution
- `POST /strategies/{run_id}/stop` - Stop strategy execution
- `GET /strategies/{run_id}/status` - Get current strategy status
- `GET /strategies/{run_id}/portfolio` - Get portfolio summary for a strategy
  - Returns: `PortfolioSummaryResponse` with PnL, positions, etc.
- `DELETE /strategies/{run_id}` - Stop and remove a strategy

## Request/Response Patterns

### Success Response
```json
{
  "success": true,
  "message": "Operation completed successfully",
  "timestamp": "2024-01-01T12:00:00"
}
```

### Error Response
```json
{
  "error": "Error message",
  "detail": "Detailed error information",
  "timestamp": "2024-01-01T12:00:00"
}
```

## Common Request Fields

- `symbol`: Trading symbol (e.g., "AAPL", "SPY")
- `exchange`: Exchange identifier (e.g., "SMART", "NYSE")
- `security_type`: "STK", "OPT", "FUT", etc.
- `currency`: Currency code (e.g., "USD", "INR")
- `broker_name`: Name of the broker to use
- `action`: "BUY" or "SELL"
- `quantity`: Order quantity (positive integer)
- `time_in_force`: "DAY", "GTC", "IOC", "FOK", etc.

## Notes

1. **Runtime Management**: The API uses a singleton `TradingSystem` instance managed by `runtime.py`.

2. **Strategy Management**: Active strategy managers are stored in memory by `run_id`. Strategies should be initialized before starting.

3. **Error Handling**: All endpoints use proper HTTP status codes and error handling.

4. **Data Types**: 
   - Dates should be in ISO format (YYYY-MM-DD for dates, ISO 8601 for datetimes)
   - Prices and quantities are floats/integers
   - All timestamps are returned as ISO 8601 strings

## Example Usage

### Initialize a Strategy
```bash
curl -X POST "http://localhost:8000/strategies/initialize" \
  -H "Content-Type: application/json" \
  -d '{
    "broker_name": "interactive_brokers",
    "exchange": "NYSE",
    "strategy_name": "atm_short_straddle",
    "start_date": null,
    "end_date": null,
    "db_path": "trading_system.db"
  }'
```

### Submit a Market Order
```bash
curl -X POST "http://localhost:8000/orders/market" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "exchange": "SMART",
    "action": "BUY",
    "quantity": 100,
    "broker_name": "interactive_brokers",
    "security_type": "STK",
    "currency": "USD"
  }'
```

### Get Historical Data
```bash
curl -X POST "http://localhost:8000/data/historical" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "SPY",
    "exchange": "SMART",
    "duration": "1 D",
    "bar_size": "1 hour",
    "security_type": "STK",
    "currency": "USD"
  }'
```

