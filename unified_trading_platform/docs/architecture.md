# System Architecture

## Overview
The Modular Trading System is designed with a layered architecture to ensure separation of concerns. It employs an **Event-Driven Architecture** for market data processing to ensure that high-frequency broker callbacks do not block the main application logic.

```mermaid
graph TD
    subgraph "Core Layer"
        TS[TradingSystem] --> BF[BrokerFactory]
        TS --> DM[DataManager]
        TS --> OM[OrderManager]
        TS --> EE[EventEngine]
    end

    subgraph "Broker Layer"
        BF --> IB[IBBroker]
        BF --> Paper[PaperBroker]
        
        IB -->|Async| IBC[IBClient]
        IBC -->|Map| RM[IBRequestManager]
    end

    subgraph "Data Layer"
        DM --> DB[(SQLite DB)]
        DM --> Cache[Memory Cache]
    end

    EE -->|Async Event| DM

    subgraph "Configuration"
        Config[config.yaml] --> Settings[Settings Model]
        Settings --> TS
    end
```

## Interactive Brokers Implementation

The IB integration uses a **Request Manager** pattern to bridge the asynchronous, callback-based `ibapi` with the synchronous/async-await style of the trading core.

### The Request Flow

1.  **Request Initiation**: `IBBroker` calls an async method on `IBClient` (e.g., `get_contract_details_async`).
2.  **Future Creation**: `IBClient` asks `IBRequestManager` for a new `reqId`. The manager creates a Python `Future` and maps it to the ID.
3.  **API Call**: `IBClient` sends the request to TWS using the `reqId`.
4.  **Accumulation**: As callbacks arrive (e.g., `contractDetails`), `IBClient` accumulates data in a temporary buffer.
5.  **Completion**: When the "End" callback arrives (e.g., `contractDetailsEnd`), `IBClient` retrieves the `Future` from `IBRequestManager` and sets the result.
6.  **Response**: The `Future` resolves, and `IBBroker` receives the data.

```mermaid
sequenceDiagram
    participant Broker as IBBroker
    participant Client as IBClient
    participant Manager as RequestManager
    participant TWS as IB TWS

    Broker->>Client: get_contract_details_async(contract)
    Client->>Manager: create_request()
    Manager-->>Client: reqId, Future
    Client->>TWS: reqContractDetails(reqId, contract)
    Client-->>Broker: return Future
    
    TWS->>Client: contractDetails(reqId, data)
    Client->>Client: Accumulate data
    
    TWS->>Client: contractDetailsEnd(reqId)
    Client->>Manager: set_result(reqId, accumulated_data)
    Manager-->>Broker: Future Resolves
```

## Configuration

Configuration is managed via `config.yaml`, creating a single source of truth for:
-   **Broker Settings**: Host, port, client IDs.
-   **System Paths**: Data directories, log paths.
-   **Trading defaults**: Risk limits, default quantities.

The system uses `pydantic-settings` to load this configuration and allow environment variable overrides (e.g., `TRADING_SYSTEM_BROKERS__INTERACTIVE_BROKERS__HOST=192.168.1.5`).

## System Class Diagram

```mermaid
classDiagram
    class TradingSystem {
        +add_broker(name, type)
        +submit_order(order)
        +get_historical_data(contract)
        +subscribe_market_data(contract)
    }

    class BrokerFactory {
        +register_broker(type, class)
        +create_broker(type, config) BrokerInterface
    }

    class BrokerInterface {
        <<interface>>
        +connect()
        +disconnect()
        +submit_order(order)
        +get_historical_data(contract)
        +subscribe_market_data(contract)
    }

    class IBBroker {
        -client: IBClient
        -request_manager: IBRequestManager
        +connect()
        +submit_order(order)
    }

    class IBClient {
        +reqContractDetails()
        +reqHistoricalData()
        +reqMktData()
        +get_contract_details_async()
    }
    
    class IBRequestManager {
        +create_request() (reqId, Future)
        +set_result(reqId, result)
        +set_error(reqId, error)
    }

    class PaperBroker {
        +connect()
        +submit_order(order)
    }

    class DataManager {
        -cache: MemoryCache
        -db: SQLiteDB
        +get_historical_data()
        +save_tick_data()
    }

    class OrderManager {
        -orders: Dict
        +submit_order(order)
        +on_order_status(status)
    }

    class StrategyManager {
        +register_strategy(strategy)
        +start()
        +stop()
    }
    
    class StrategyEngine {
        +run_backtest()
        +simulate_market()
    }

    TradingSystem --> BrokerFactory
    TradingSystem --> DataManager
    TradingSystem --> OrderManager
    
    BrokerFactory ..> BrokerInterface : Creates
    IBBroker --|> BrokerInterface
    PaperBroker --|> BrokerInterface
    
    IBBroker --> IBClient
    IBClient --> IBRequestManager
    
    StrategyManager --> TradingSystem : Uses
    StrategyManager --> StrategyEngine : Uses (Backtest)
```
