# Message Broker — Test Specification

## Unit Tests

Tests for the module's internal logic in isolation.

- **Test name**: `test_idle_detection_for_claude_provider`
  - **Scenario**: Mock a Claude provider with `capabilities.supports_hook=True` and `capabilities.name="claude"`; call `broker_delivery_cycle` with the window ID included in `idle_windows`
  - **Expected behavior**: The broker attempts delivery to the Claude window (calls `tmux_mgr.send_keys`); when the same window is absent from `idle_windows`, the broker skips it without calling `send_keys`

- **Test name**: `test_idle_detection_for_shell_provider`
  - **Scenario**: Mock a shell provider with `capabilities.name="shell"`; call `broker_delivery_cycle` with a pending message in the shell window's inbox
  - **Expected behavior**: `tmux_mgr.send_keys` is never called for the shell window; instead, `notify_pending_shell` is called (verified via patched `msg_telegram` module)

- **Test name**: `test_rate_limiting_blocks_excess_messages`
  - **Scenario**: Call `broker_delivery_cycle` repeatedly for the same window until `msg_rate_limit` is exhausted within `_RATE_WINDOW_SECONDS`
  - **Expected behavior**: Once the rate limit is reached, further calls to `broker_delivery_cycle` skip the window; `tmux_mgr.send_keys` is not called again until the sliding window expires

- **Test name**: `test_loop_detection_triggers_on_rapid_exchange`
  - **Scenario**: Simulate `_LOOP_THRESHOLD` or more exchanges between `window_a` and `window_b` within `_LOOP_WINDOW_SECONDS` by calling `delivery_strategy.record_exchange` the required number of times, then call `_collect_eligible` for `window_a` with a pending message from `window_b`
  - **Expected behavior**: `check_loop` returns `True`; `window_b` is added to `window_a`'s `paused_peers`; the loop pair is included in the returned `loops` list; the message is excluded from `eligible`

- **Test name**: `test_crash_recovery_cleans_orphaned_delivery_files`
  - **Scenario**: Write `tmp/deliver-{msg_id}.txt` files to a mailbox inbox directory; create corresponding message files with `status="pending"` and `delivered_at=None` with `created_at` older than 5 seconds; call `broker_delivery_cycle` for the first time
  - **Expected behavior**: `_recover_stale_pending` runs once; each stale pending message is marked `delivered`; `delivery_strategy._crash_recovery_done` is set to `True`; on subsequent calls, `_recover_stale_pending` does not run again

## Integration Contract Tests

Tests that verify the module honors its integration contracts.

- **Test name**: `test_broker_calls_mailbox_create_delivery_path`
  - **Scenario**: Patch `write_delivery_file` and verify it constructs delivery paths using the public Mailbox path contract (path under `inbox_dir/tmp/deliver-{msg_id}.txt`) rather than calling `_sanitize_dir_name` directly
  - **Expected behavior**: The delivery file path uses the same sanitized inbox directory that `Mailbox._inbox_dir(window_id)` produces; the `_sanitize_dir_name` function is not imported at module level in `msg_broker.py` for path construction purposes

- **Test name**: `test_broker_calls_spawn_request_accessors`
  - **Scenario**: In `_process_spawn_requests`, verify the code path for cache eviction on failure uses `pop_pending(req.id)` or equivalent rather than `_pending_requests.pop(req.id, None)` directly
  - **Expected behavior**: `scan_spawn_requests` is called to discover new requests; failed spawn requests are evicted using the public accessor; `_pending_requests` dict is not accessed directly from `msg_broker`

- **Test name**: `test_broker_imports_delivery_strategy_from_msg_delivery`
  - **Scenario**: Inspect the import chain: `msg_broker.py` must import `delivery_strategy` from `msg_delivery` (not own it directly); `msg_telegram.py` must import `delivery_strategy` from `msg_delivery` (not `msg_broker`)
  - **Expected behavior**: Both modules reference the same singleton; mutating it from the broker (e.g. `delivery_strategy.pause_peer`) is immediately reflected when the Telegram UI reads it via `delivery_strategy.is_paused`

- **Test name**: `test_broker_notifies_telegram_on_delivery`
  - **Scenario**: Mock `notify_messages_delivered` and `notify_message_sent` from `msg_telegram`; run `broker_delivery_cycle` with a pending message in an idle window
  - **Expected behavior**: `notify_messages_delivered` is called once with `to_window` and the list of delivered messages; `notify_message_sent` is called once per message with `from_window`, `to_window`, and the `Message` object

## Boundary Tests

Tests that verify the module correctly rejects invalid inputs and maintains encapsulation.

- **Test name**: `test_delivery_to_nonexistent_window`
  - **Scenario**: Call `broker_delivery_cycle` with a `window_id` in `window_states` that has a pending inbox message but whose tmux window no longer exists (`tmux_mgr.send_keys` returns `False`)
  - **Expected behavior**: The broker does not raise an exception; the message is not marked delivered; the broker continues processing other windows

- **Test name**: `test_delivery_to_foreign_window`
  - **Scenario**: Add an emdash foreign window (`emdash-claude-main-abc123:@0`) to `window_states`; add a pending message to its inbox; call `broker_delivery_cycle`
  - **Expected behavior**: `is_foreign_window` returns `True`; the qualified ID used for inbox lookup is the full foreign ID (`emdash-claude-main-abc123:@0`), not prefixed with `tmux_session`; `tmux_mgr.send_keys` is called with the foreign window ID

- **Test name**: `test_empty_inbox_returns_quickly`
  - **Scenario**: Call `broker_delivery_cycle` with all windows having empty inboxes
  - **Expected behavior**: `tmux_mgr.send_keys` is never called; `notify_messages_delivered` is never called; the function returns `0` without errors

## Behavior Tests

Tests that verify the module's functional responsibilities from an outside-in perspective.

- **Test name**: `test_full_delivery_cycle`
  - **Scenario**: Send a message to an idle Claude window's inbox; run `broker_delivery_cycle` with that window in `idle_windows`
  - **Expected behavior**: `_collect_eligible` finds the message; `tmux_mgr.send_keys` is called with the formatted injection text; `Mailbox.mark_delivered` is called; `delivery_strategy.record_exchange` is called; `notify_messages_delivered` is called with the bot and the message list; the function returns `1`

- **Test name**: `test_spawn_request_routed_to_approval`
  - **Scenario**: Write a spawn request JSON file to `mailbox/spawns/`; run `broker_delivery_cycle` with a non-None `bot`
  - **Expected behavior**: `scan_spawn_requests` discovers the new file; `post_spawn_approval_keyboard` is called with the bot and the `SpawnRequest`; the approval keyboard is posted to the requester's Telegram topic

- **Test name**: `test_loop_pause_stops_delivery`
  - **Scenario**: Trigger loop detection between `window_a` and `window_b` by recording `_LOOP_THRESHOLD` exchanges; then run `broker_delivery_cycle` with a pending message from `window_b` to `window_a`
  - **Expected behavior**: The message is not delivered (excluded by `is_paused` check); `tmux_mgr.send_keys` is not called for the loop pair; `notify_loop_detected` is called once for the loop alert
