"""
Event System for Asynchronous Processing
Decouples data producing threads (Brokers) from data consuming threads (Strategies, DB)
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Any, Callable, Dict, List
import queue
import threading
from unified_trading_platform.trading_core.utils import get_logger

logger = get_logger(__name__)

class EventType(Enum):
    TICK = auto()
    BAR = auto()
    ORDER_STATUS = auto()
    TRADE = auto()
    ERROR = auto()
    LOG = auto()

@dataclass
class Event:
    type: EventType
    data: Any

#: Sentinel pushed onto the queue to wake the worker for shutdown.
_STOP = object()


class EventEngine:
    """
    Processes events from a queue in a dedicated background thread.
    """
    def __init__(self):
        self._queue = queue.Queue()
        self._active = False
        self._thread = None
        self._handlers: Dict[EventType, List[Callable]] = {
            evt_type: [] for evt_type in EventType
        }

    def start(self):
        """Start the event processing thread"""
        self._active = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="EventEngine")
        self._thread.start()
        logger.info("Event Engine started")

    def stop(self, timeout: float = 5.0):
        """Stop the event processing thread.

        A sentinel wakes the worker immediately instead of waiting out its poll
        interval, so shutdown does not stall for a second per engine.
        """
        if not self._active:
            return
        self._active = False
        self._queue.put(_STOP)
        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("Event Engine did not stop within %.1fs", timeout)
        logger.info("Event Engine stopped")

    def put(self, event: Event):
        """Push an event to the queue"""
        self._queue.put(event)

    def register(self, event_type: EventType, handler: Callable):
        """Register a handler for an event type"""
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unregister(self, event_type: EventType, handler: Callable):
        """Unregister a handler"""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def _run(self):
        """Drain the queue until stopped."""
        while self._active:
            try:
                # Bounded wait so a missed sentinel can never wedge the thread
                event = self._queue.get(timeout=1.0)
                if event is _STOP:
                    break
                self._process(event)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in Event Engine loop: {e}", exc_info=True)

    def _process(self, event: Event):
        """Process a single event"""
        if event.type in self._handlers:
            for handler in self._handlers[event.type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler {handler.__name__}: {e}", exc_info=True)
