# Message Delivery — Test Specification

## Unit Tests

Tests for the module's internal logic in isolation.

- **Test name**: `test_delivery_state_created_on_first_access`
  - **Scenario**: Call `delivery_strategy.get_state(window_id)` for a `window_id` that has not been seen before
  - **Expected behavior**: A new `DeliveryState` is returned with empty `delivery_timestamps`, `loop_counts`, `paused_peers`, and `notified_shell_ids`; a second call with the same `window_id` returns the same object (not a fresh one)

- **Test name**: `test_delivery_state_updated_on_success`
  - **Scenario**: Call `delivery_strategy.record_delivery(window_id)` then `delivery_strategy.get_state(window_id)`
  - **Expected behavior**: `delivery_timestamps` contains exactly one monotonic timestamp; `check_rate_limit(window_id, max_rate=10)` returns `True` (one delivery is within the limit)

- **Test name**: `test_loop_pause_sets_pause_state`
  - **Scenario**: Call `delivery_strategy.pause_peer(window_id, peer_id)`
  - **Expected behavior**: `delivery_strategy.is_paused(window_id, peer_id)` returns `True`; `is_paused(peer_id, window_id)` returns `False` (pause is directional — only the recipient side is checked)

- **Test name**: `test_loop_allow_clears_pause`
  - **Scenario**: Pause delivery between `window_a` and `window_b` by calling `pause_peer` on both sides; then call `delivery_strategy.allow_more(window_a, window_b)`
  - **Expected behavior**: `is_paused(window_a, window_b)` returns `False`; `is_paused(window_b, window_a)` returns `False`; the pair's `loop_counts` entry is cleared from both states

- **Test name**: `test_clear_delivery_state_removes_entry`
  - **Scenario**: Call `delivery_strategy.get_state(window_id)` to create an entry; then call `delivery_strategy.clear_state(window_id)`
  - **Expected behavior**: The state dict no longer contains an entry for `window_id`; a subsequent `get_state(window_id)` returns a fresh default `DeliveryState`

## Integration Contract Tests

Tests that verify the module honors its integration contracts.

- **Test name**: `test_broker_and_telegram_share_strategy`
  - **Scenario**: Import `delivery_strategy` from `msg_delivery` in both the broker and the Telegram UI module paths; mutate state via one import and read via the other
  - **Expected behavior**: `delivery_strategy` is the same object in both import paths (identity check); setting `delivery_strategy.pause_peer(window_a, window_b)` via the broker's import path causes `delivery_strategy.is_paused(window_a, window_b)` to return `True` when read via the Telegram UI's import path

- **Test name**: `test_cleanup_via_topic_state_registry`
  - **Scenario**: Call the module-level `clear_delivery_state(window_id)` function (as used by the topic state registry on topic close) with a qualified window ID
  - **Expected behavior**: The state for that `window_id` is removed from the singleton; no exception is raised when calling `clear_delivery_state` for a `window_id` that has no state

## Boundary Tests

Tests that verify the module correctly rejects invalid inputs and maintains encapsulation.

- **Test name**: `test_clear_nonexistent_state`
  - **Scenario**: Call `delivery_strategy.clear_state(window_id)` for a `window_id` that was never accessed
  - **Expected behavior**: No `KeyError` or other exception is raised; the internal `_states` dict remains empty

- **Test name**: `test_concurrent_state_updates`
  - **Scenario**: Call `delivery_strategy.record_delivery(window_id)` and `delivery_strategy.record_exchange(window_id, peer_id)` from two `asyncio` tasks running concurrently via `asyncio.gather`
  - **Expected behavior**: After both tasks complete, `delivery_timestamps` contains exactly 2 entries and `loop_counts` contains the expected exchange entries; no data is lost or duplicated due to interleaving

## Behavior Tests

Tests that verify the module's functional responsibilities from an outside-in perspective.

- **Test name**: `test_delivery_lifecycle`
  - **Scenario**: Simulate a full delivery lifecycle for a window pair: create state (via `get_state`) → record delivery → record multiple exchanges → trigger loop check → pause → allow → clear on topic close
  - **Expected behavior**:
    1. After `record_delivery`, `check_rate_limit` returns `True` (within limit)
    2. After `_LOOP_THRESHOLD` calls to `record_exchange`, `check_loop` returns `True`
    3. After `pause_peer`, `is_paused` returns `True`
    4. After `allow_more`, `is_paused` returns `False` and `check_loop` returns `False`
    5. After `clear_state`, `get_state` returns a fresh `DeliveryState` with no history
