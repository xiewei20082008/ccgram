# Messaging Telegram UI — Test Specification

## Unit Tests

Tests for the module's internal logic in isolation.

- **Test name**: `test_resolve_topic_finds_bound_window`
  - **Scenario**: Patch `thread_router.iter_thread_bindings` to yield `(user_id, thread_id, window_id)` where `window_id` matches the `qualified_id` passed to `_resolve_topic`; patch `thread_router.resolve_chat_id` to return a known `chat_id`
  - **Expected behavior**: `_resolve_topic(qualified_id)` returns `(user_id, thread_id, chat_id, window_id)`; the chat ID, thread ID, and user ID match the patched values

- **Test name**: `test_resolve_topic_returns_none_for_unbound`
  - **Scenario**: Patch `thread_router.iter_thread_bindings` to yield no bindings that match the given `qualified_id`
  - **Expected behavior**: `_resolve_topic(qualified_id)` returns `None`; no exception is raised

- **Test name**: `test_notification_grouping_edits_recent`
  - **Scenario**: Call `notify_messages_delivered` with a list of two `Message` objects for the same `to_window`
  - **Expected behavior**: A single `rate_limit_send_message` call is made with a multi-line text block (not two separate calls); the text begins with `← 2 messages delivered:` and lists both senders

- **Test name**: `test_notification_grouping_sends_new_after_threshold`
  - **Scenario**: Call `notify_messages_delivered` with a single-message list
  - **Expected behavior**: The notification text uses the compact single-message format (`← {from_wid} ({from_name}) [{type}]`); a single `rate_limit_send_message` call is made with `disable_notification=True`

- **Test name**: `test_loop_alert_callback_data_within_64_bytes`
  - **Scenario**: Construct the callback data strings for `[Pause Messaging]` and `[Allow 5 more]` buttons using the hash-based format (`CB_MSG_LOOP_PAUSE + pair_hash` and `CB_MSG_LOOP_ALLOW + pair_hash`) for a variety of long qualified IDs (e.g. `emdash-claude-main-abc123:@0`)
  - **Expected behavior**: `len(callback_data.encode())` is at most 64 bytes for all generated pairs; the prefix (`ml:p:` or `ml:a:`) plus 12-char hex hash sums to 17 bytes total, well within the limit

- **Test name**: `test_loop_alert_pairs_bounded_by_lru`
  - **Scenario**: Call `notify_loop_detected` with 101 distinct window pairs (patching `rate_limit_send_message` to be a no-op); inspect `_loop_alert_pairs`
  - **Expected behavior**: `len(_loop_alert_pairs)` is exactly `_MAX_LOOP_ALERT_PAIRS` (100); the oldest inserted pair hash is no longer present; the 101st pair's hash is present

## Integration Contract Tests

Tests that verify the module honors its integration contracts.

- **Test name**: `test_resolve_topic_uses_thread_router`
  - **Scenario**: Call `_resolve_topic` with a qualified window ID; verify that `thread_router.iter_thread_bindings()` and `thread_router.resolve_chat_id(user_id, thread_id)` are called (using `MagicMock`)
  - **Expected behavior**: Both thread router methods are invoked; the return value of `resolve_chat_id` is used as the `chat_id` in the returned tuple; `thread_router.get_display_name` is not called from within `_resolve_topic` itself

- **Test name**: `test_loop_callbacks_use_delivery_strategy`
  - **Scenario**: Invoke the `_handle_loop_alert` callback handler (via a mocked `Update` with `callback_query.data = CB_MSG_LOOP_PAUSE + pair_hash`) after seeding `_loop_alert_pairs` with the matching pair; verify which object's `pause_peer` is called
  - **Expected behavior**: `delivery_strategy.pause_peer` is called twice (once for each direction: `pause_peer(pair[0], pair[1])` and `pause_peer(pair[1], pair[0])`); the `delivery_strategy` imported in `msg_telegram` is the same singleton as in `msg_delivery` (not a copy from `msg_broker`)

- **Test name**: `test_callbacks_registered_with_callback_registry`
  - **Scenario**: Import `msg_telegram` and inspect the callback registry for the `CB_MSG_LOOP_PAUSE` (`ml:p:`) and `CB_MSG_LOOP_ALLOW` (`ml:a:`) prefixes
  - **Expected behavior**: Both prefixes map to `_handle_loop_alert` in the registry; the `@register(CB_MSG_LOOP_PAUSE, CB_MSG_LOOP_ALLOW)` decorator has been applied at import time

## Boundary Tests

Tests that verify the module correctly rejects invalid inputs and maintains encapsulation.

- **Test name**: `test_notify_with_telegram_error`
  - **Scenario**: Patch `rate_limit_send_message` to raise `telegram.error.TelegramError`; call `notify_messages_delivered` with a valid topic binding
  - **Expected behavior**: The `TelegramError` propagates to the caller (broker catches it); no internal state is corrupted; subsequent calls to `notify_messages_delivered` behave normally

- **Test name**: `test_resolve_topic_with_deleted_binding`
  - **Scenario**: Patch `iter_thread_bindings` to return a binding on the first iteration, then patch `resolve_chat_id` to raise `KeyError` (simulating a binding removed between the check and the resolve)
  - **Expected behavior**: `_resolve_topic` propagates the exception or returns `None`; it does not silently return a tuple with invalid values

- **Test name**: `test_silent_notification_flag`
  - **Scenario**: Call `notify_message_sent`, `notify_messages_delivered`, `notify_reply_received`, and `notify_pending_shell` with valid mocked arguments; capture the kwargs passed to `rate_limit_send_message`
  - **Expected behavior**: All four notification functions pass `disable_notification=True` to `rate_limit_send_message`; `notify_loop_detected` also passes `disable_notification=True`

## Behavior Tests

Tests that verify the module's functional responsibilities from an outside-in perspective.

- **Test name**: `test_delivery_notification_flow`
  - **Scenario**: Mock `_resolve_topic` to return a valid `(user_id, thread_id, chat_id, window_id)` tuple; call `notify_messages_delivered(bot, to_window, [message])` with a single pending message
  - **Expected behavior**: `rate_limit_send_message` is called once with `chat_id`, the formatted text (`← @0 (service-name) [request]`), `message_thread_id=thread_id`, and `disable_notification=True`; the bot's `AsyncMock` records the call

- **Test name**: `test_loop_detection_alert_flow`
  - **Scenario**: Call `notify_loop_detected(bot, window_a, window_b)` with mocked topic resolution; then simulate a user tap on `[Pause Messaging]` by dispatching a `CallbackQuery` update with `data=CB_MSG_LOOP_PAUSE + pair_hash`
  - **Expected behavior**: `notify_loop_detected` posts a message with an `InlineKeyboardMarkup` containing two buttons; after the callback is handled, `delivery_strategy.is_paused(window_a, window_b)` and `delivery_strategy.is_paused(window_b, window_a)` both return `True`; the callback query's message text is edited to the pause confirmation string

- **Test name**: `test_reply_notification_flow`
  - **Scenario**: Create an original `Message` with `from_id=window_a` and a reply `Message` with `from_id=window_b`; call `notify_reply_received(bot, original_msg, reply_msg)` with a mocked topic for `window_a`
  - **Expected behavior**: `rate_limit_send_message` is called with the recipient's `chat_id` and `thread_id` (resolved from `original_msg.from_id`); the text contains `✓ Reply received from` and the reply sender's window ID and display name; `disable_notification=True` is set
