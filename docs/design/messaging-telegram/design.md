# Messaging Telegram UI

## Functional Responsibilities

Sends silent Telegram notifications when inter-agent messages move between windows, and renders loop detection alerts as interactive inline keyboards. All notifications are silent (`disable_notification=True`) to avoid alert fatigue.

Core capabilities:

- Sender notification: `notify_message_sent(bot, from_window, to_window, message)` posts a compact outbound line in the sender's topic (`→ @5 (api-gateway) [request] API contract query`)
- Recipient notification: `notify_messages_delivered(bot, to_window, messages)` posts a grouped inbound notification in the recipient's topic; merges multiple messages into a single update to avoid flooding
- Reply notification: `notify_reply_received(bot, original_msg, reply_msg)` posts a confirmation in the original sender's topic when a reply arrives
- Shell pending notification: `notify_pending_shell(bot, window_id, message)` shows pending message preview in a shell topic (shell windows do not receive `send_keys` injection, so Telegram is the delivery channel)
- Loop detection alert: `notify_loop_detected(bot, window_a, window_b)` posts a warning with `[Pause Messaging]` and `[Allow 5 more]` inline keyboard buttons
- Loop alert button callbacks: `_handle_loop_alert` registered for `ml:p:` and `ml:a:` prefixes; dispatches to `delivery_strategy.pause_peer` or `delivery_strategy.allow_more`
- Topic resolution: `_resolve_topic(qualified_id)` finds the Telegram `(user_id, thread_id, chat_id, window_id)` for a qualified window ID; tries exact qualified ID match first (for foreign/emdash windows), then bare window ID fallback (restricted to local session)

## Encapsulated Knowledge

- `_loop_alert_pairs: dict[str, tuple[str, str]]` — bounded LRU dict (max 100 entries) mapping a 12-char MD5 hash to `(window_a, window_b)`; required because Telegram limits `callback_data` to 64 bytes and qualified IDs can exceed that
- Hash construction: `hashlib.md5(f"{window_a}|{window_b}".encode()).hexdigest()[:12]`; oldest entry evicted when capacity is reached
- Notification text formats: `→ {wid} ({name}) [{type}]{subj}` for sent; `← {wid} ({name}) [{type}]{subj}` for delivered; `✓ Reply received from {wid} ({name}){for: subj}` for replies; `✉ Pending from {wid} ({name}) [{type}]{subj}: {preview}` for shell
- Subject truncation: `_SUBJECT_MAX_LEN = 40` chars with `...` suffix
- Body preview in shell notification: `_BODY_PREVIEW_LEN = 100` chars
- Callback prefixes: `CB_MSG_LOOP_PAUSE = "ml:p:"` and `CB_MSG_LOOP_ALLOW = "ml:a:"`
- Local vs. foreign session discrimination in `_resolve_topic` and `_display_name`: foreign IDs (those whose session prefix differs from `tmux_session_name()`) must not fall back to a bare `@N` match that belongs to a local window
- `_is_local_qualified(qualified_id)`: bare IDs (no colon) are always local; qualified IDs are local only when their session prefix matches `tmux_session_name()`

## Subdomain Classification

**Supporting** — notification formatting and Telegram delivery mechanics. Moderate volatility: UX text and grouping rules change with product decisions, but the module's structure and contract surface are stable. Does not own delivery state; only reads it for callback dispatch.

## Integration Contracts

**Public function: `resolve_topic`** (previously `_resolve_topic`):

```python
def resolve_topic(qualified_id: str) -> tuple[int, int, int, str] | None:
    """Find (user_id, thread_id, chat_id, window_id) for a qualified window ID.
    Returns None if no topic is bound to this window."""
```

Currently named `_resolve_topic` and called by `msg_spawn.py` via a private import — the redesign makes it public.

**→ Thread Router** (depends on `thread_router.py`):

- Direction: Messaging Telegram UI depends on Thread Router
- Contract type: contract
- What is shared: topic lookup, display name resolution, chat ID resolution
- Contract definition: `thread_router.iter_thread_bindings() -> Iterator[tuple[int, int, str]]` (yields `user_id, thread_id, window_id`); `thread_router.resolve_chat_id(user_id, thread_id) -> int`; `thread_router.get_display_name(window_id) -> str`

**→ Message Delivery** (depends on `msg_delivery.py` — currently `handlers/msg_broker.py`):

- Direction: Messaging Telegram UI depends on Message Delivery for callback dispatch
- Contract type: contract
- What is shared: loop alert pause/allow state mutations triggered by button presses
- Contract definition:
  ```python
  from .msg_delivery import delivery_strategy  # target import path
  delivery_strategy.pause_peer(pair[0], pair[1])
  delivery_strategy.pause_peer(pair[1], pair[0])
  delivery_strategy.allow_more(pair[0], pair[1])
  ```
  Currently imports from `msg_broker` — the redesign breaks this circular dependency by moving the singleton to `msg_delivery.py`

**→ Callback Registry** (depends on `handlers/callback_registry.py`):

- Direction: Messaging Telegram UI depends on Callback Registry
- Contract type: contract
- What is shared: self-registration of loop alert button callbacks
- Contract definition: `@register(CB_MSG_LOOP_PAUSE, CB_MSG_LOOP_ALLOW)` decorator applied to `_handle_loop_alert`

**→ Message Sender** (depends on `handlers/message_sender.py`):

- Direction: Messaging Telegram UI depends on Message Sender for rate-limited delivery
- Contract type: contract
- What is shared: outbound Telegram message sending with flood control
- Contract definition: `rate_limit_send_message(bot, chat_id, text, message_thread_id, disable_notification, reply_markup)` returns sent message or None

**← Message Broker** (depended on by `handlers/msg_broker.py`):

- Direction: broker depends on Messaging Telegram UI
- Contract type: contract
- What is shared: notification trigger calls after delivery events and loop detection
- Contract definition: `notify_messages_delivered(bot, to_window, messages)`, `notify_message_sent(bot, from_window, to_window, message)`, `notify_reply_received(bot, original_msg, reply_msg)`, `notify_loop_detected(bot, window_a, window_b)`, `notify_pending_shell(bot, window_id, message)`

**← Message Spawn** (depended on by `handlers/msg_spawn.py`):

- Direction: spawn handler depends on Messaging Telegram UI
- Contract type: contract
- What is shared: topic resolution for posting approval keyboards to the requester's topic
- Contract definition: `resolve_topic(qualified_id) -> tuple[int, int, int, str] | None` (public function)

**← Topic State Registry** (depended on by cleanup handlers):

- Direction: cleanup depends on Messaging Telegram UI
- Contract type: contract
- What is shared: loop alert pair cache cleanup on topic close
- Contract definition: cleanup handler removes entries from `_loop_alert_pairs` whose window ID matches the closing topic

## Change Vectors

- Changing notification text format — only the `text =` string construction in the `notify_*` functions changes; no callers are affected
- Adding a new notification type (e.g. `notify_spawn_completed`) — add a new `async def notify_*` function; broker calls it; no existing functions change
- Changing notification grouping algorithm (edit-in-place for rapid sequences) — only the `notify_messages_delivered` logic changes; broker calls remain identical
- Changing loop alert UI (different button labels, adding a third option) — only `notify_loop_detected` keyboard construction and `_handle_loop_alert` dispatch change
- Adding `resolve_topic` caching (for high-frequency broker cycles) — only the internal lookup logic changes; signature and return type unchanged
- Changing the hash algorithm for callback data (SHA-256 truncated) — only `notify_loop_detected` hash construction and the lookup in `_handle_loop_alert` change
