# Message Delivery

## Functional Responsibilities

Owns the `MessageDeliveryStrategy` class and its module-level singleton `delivery_strategy` — the per-window delivery state tracker shared between the Message Broker (write path) and the Messaging Telegram UI (read path for loop alert button callbacks).

Core capabilities:

- Per-window `DeliveryState` management: create on first access via `get_state(window_id)`, clear on window close via `clear_state(window_id)`
- Rate limiting state: sliding-window timestamp list per window; `check_rate_limit(window_id, max_rate)` trims stale timestamps and returns whether the window is within limits; `record_delivery(window_id)` appends the current monotonic timestamp
- Loop detection state: per-pair exchange timestamp lists; `check_loop(window_a, window_b)` tests frequency threshold within the sliding window; `record_exchange(window_a, window_b)` records on both sides for order-independence
- Pause/unpause: `is_paused(window_id, peer_id)`, `pause_peer(window_id, peer_id)`, `unpause_peer(window_id, peer_id)` — paused peer set per window
- Allow more: `allow_more(window_a, window_b)` clears pair-specific loop counts and unpauses both sides
- Crash recovery guard: `_crash_recovery_done` flag on the singleton; set by broker after first cycle, never cleared
- Shell notification tracking: `notified_shell_ids` set per window to prevent re-notifying the same message in every broker cycle
- Bulk reset: `reset_all_state()` clears all windows (used in tests)
- Module-level helpers: `clear_delivery_state(window_id)` and `reset_delivery_state()` delegate to the singleton for clean imports

## Encapsulated Knowledge

- `DeliveryState` dataclass fields: `delivery_timestamps: list[float]`, `loop_counts: dict[str, list[float]]`, `paused_peers: set[str]`, `notified_shell_ids: set[str]`
- Rate limit window: `_RATE_WINDOW_SECONDS = 300.0` (5 minutes) — trims timestamps older than this on each `check_rate_limit` call
- Loop detection window: `_LOOP_WINDOW_SECONDS = 600.0` (10 minutes)
- Loop threshold: `_LOOP_THRESHOLD = 5` exchanges within the window
- `_pair_key(a, b)` canonical order-independent key: `{min(a,b)}|{max(a,b)}`
- State dict keyed by qualified window ID — same key space as the Mailbox and session_map
- `_crash_recovery_done` lives on the singleton object, not in `DeliveryState`; it is process-scoped, not per-window
- All timestamps use `time.monotonic()` for rate/loop checks (not wall clock), so they are not persisted across restarts

## Subdomain Classification

**Core** — shared between the broker (write path on every delivery cycle) and the Telegram UI (read path on loop alert button presses). Changes with delivery strategy evolution: new idle detection methods, new rate limiting algorithms, new loop detection policies, new per-window delivery fields all land here.

## Integration Contracts

**← Message Broker** (depended on by `handlers/msg_broker.py`):

- Direction: broker depends on Message Delivery
- Contract type: contract
- What is shared: rate limiting, loop detection, pause state, delivery recording, crash recovery guard, shell notification dedup
- Contract definition:
  ```python
  delivery_strategy.get_state(window_id) -> DeliveryState
  delivery_strategy.check_rate_limit(window_id, max_rate) -> bool
  delivery_strategy.record_delivery(window_id) -> None
  delivery_strategy.check_loop(window_a, window_b) -> bool
  delivery_strategy.record_exchange(window_a, window_b) -> None
  delivery_strategy.is_paused(window_id, peer_id) -> bool
  delivery_strategy.pause_peer(window_id, peer_id) -> None
  delivery_strategy._crash_recovery_done  # bool flag, set once
  ```

**← Messaging Telegram UI** (depended on by `handlers/msg_telegram.py`):

- Direction: Telegram UI depends on Message Delivery
- Contract type: contract
- What is shared: loop alert button callback dispatch — pause/allow actions mutate delivery state
- Contract definition:
  ```python
  from .msg_broker import delivery_strategy  # current import path
  delivery_strategy.pause_peer(window_a, window_b)
  delivery_strategy.pause_peer(window_b, window_a)
  delivery_strategy.allow_more(window_a, window_b)
  ```
  Note: the import `from .msg_broker import delivery_strategy` creates a coupling to the broker module's namespace. The redesign moves the singleton to `msg_delivery.py` so the UI can import directly without pulling in broker logic.

**← Topic State Registry** (depended on by cleanup handlers):

- Direction: cleanup depends on Message Delivery
- Contract type: contract
- What is shared: window-scoped state cleanup on topic close
- Contract definition: `clear_delivery_state(window_id)` module-level function registered as window close callback

## Change Vectors

- Changing `DeliveryState` fields (adding backoff counter, retry count, last-error timestamp) — only the dataclass definition and the methods that read/write those fields change
- Changing rate limiting algorithm (token bucket, leaky bucket) — only `check_rate_limit` and `record_delivery` change; callers pass `max_rate` and receive `bool`
- Changing loop detection algorithm (different threshold, exponential backoff pause) — only `check_loop`, `record_exchange`, and `allow_more` change
- Adding per-window delivery retry backoff — add `backoff_until: float` field to `DeliveryState`; update broker to consult it; UI unchanged
- Persisting delivery state across restarts (for durable rate limiting) — add serialization to `DeliveryState`; public API unchanged
