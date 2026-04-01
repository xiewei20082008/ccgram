# Message Broker

## Functional Responsibilities

Poll-loop delivery engine that injects pending inter-agent messages into idle tmux windows via `send_keys`. Runs as a background task called from the polling coordinator every `BROKER_CYCLE_INTERVAL` (2 seconds).

Core capabilities:

- Per-window delivery cycle: enumerate live windows, check idle state, collect eligible messages, inject via `send_keys`
- Provider-aware routing: hook-enabled providers (Claude) deliver only when explicitly marked idle via `idle_windows`; non-hook providers (Codex, Gemini) use heuristic idle detection; shell windows are inbox-only (no `send_keys` injection)
- Message formatting for injection: `format_injection_text` produces a single-line string capped at 500 chars; long bodies are written to a delivery file and a file reference is injected instead
- Multi-message merging: `merge_injection_texts` concatenates multiple injection strings into a single `send_keys` call (capped at 1500 chars)
- Rate limiting: per-window sliding-window counter (`_RATE_WINDOW_SECONDS=300s`) gated by `MessageDeliveryStrategy.check_rate_limit()`
- Loop detection: frequency tracking of exchanges between window pairs within `_LOOP_WINDOW_SECONDS=600s`; pauses delivery and fires a Telegram alert when `_LOOP_THRESHOLD=5` exchanges are reached
- Delivery file writing: `write_delivery_file` constructs the path using `mailbox_dir / {sanitized_window_id} / tmp / deliver-{msg_id}.txt` — currently calls private Mailbox helpers, targeted for replacement with `Mailbox.create_delivery_path()`
- Crash recovery: `_recover_stale_pending` runs once on first cycle; marks as delivered any messages that were `send_keys`-injected but not recorded before a crash
- Spawn request scanning: `_process_spawn_requests` reads new spawn files from disk and either posts approval keyboards or auto-approves based on config
- Telegram notifications: silent notifications to sender and recipient topics on delivery, and to both topics on loop detection

## Encapsulated Knowledge

- `MessageDeliveryStrategy` is in `msg_delivery.py` (separate module) — broker imports the `delivery_strategy` singleton; it does not own state storage
- Delivery routing rules: shell windows → notify-only; hook-enabled windows → deliver only when in `idle_windows` set; heuristic-idle windows → deliver in every cycle when eligible
- Eligible message filter: exclude broadcasts, skip paused peers, apply rate limit
- Loop detection algorithm: `check_loop(window_a, window_b)` counts timestamps in `state.loop_counts[pair_key]` within the sliding window; `record_exchange` records on both sides for order-independence
- Crash recovery guard: `delivery_strategy._crash_recovery_done` flag ensures `_recover_stale_pending` runs exactly once per process lifetime
- Injection char limit (500) and merged char limit (1500)
- `_pair_key(a, b)` canonical order-independent key for window pairs: `{min(a,b)}|{max(a,b)}`
- Foreign window qualified ID construction: foreign windows already carry a qualified ID; local windows are prefixed with `tmux_session_name()`
- Spawn auto-approval: `req.auto or config.msg_auto_spawn` gate

## Subdomain Classification

**Core** — highest volatility in the messaging subdomain. Delivery strategy, idle detection rules, shell routing, and loop detection all evolve independently. Owns the orchestration between Mailbox, providers, tmux, Telegram UI, and spawn flow.

## Integration Contracts

**→ Mailbox** (depends on `mailbox.py`):

- Direction: broker depends on Mailbox
- Contract type: contract
- What is shared: message enumeration, status transitions during delivery, crash recovery scan
- Contract definition: `Mailbox.inbox(window_id)`, `Mailbox.mark_delivered(msg_id, window_id)`, `Mailbox.pending_undelivered(min_age_seconds)`. Currently also imports `_sanitize_dir_name` and `_validate_no_traversal` for delivery file path construction — these should be replaced by `Mailbox.create_delivery_path(inbox_dir, msg_id) -> Path` and `Mailbox.validate_path(path)`

**→ Message Delivery** (depends on `msg_delivery.py`):

- Direction: broker depends on Message Delivery singleton
- Contract type: contract
- What is shared: per-window delivery state (rate limiting, loop tracking, pause state)
- Contract definition: `delivery_strategy.check_rate_limit(window_id, max_rate)`, `delivery_strategy.record_delivery(window_id)`, `delivery_strategy.check_loop(window_a, window_b)`, `delivery_strategy.record_exchange(window_a, window_b)`, `delivery_strategy.is_paused(window_id, peer_id)`, `delivery_strategy.pause_peer(window_id, peer_id)`

**→ Spawn Request** (depends on `spawn_request.py`):

- Direction: broker depends on Spawn Request
- Contract type: contract
- What is shared: pending spawn request discovery for approval routing
- Contract definition: `scan_spawn_requests(spawn_timeout)` returns new `SpawnRequest` objects; `_pending_requests.pop(req.id, None)` used for cache eviction on failure — should be replaced by `pop_pending(request_id)` accessor

**→ Provider Protocol** (depends on `providers/__init__.py`):

- Direction: broker depends on provider resolution
- Contract type: contract
- What is shared: provider capability check to gate delivery routing
- Contract definition: `get_provider_for_window(window_id)` returns a provider instance; `provider.capabilities.name == "shell"` and `provider.capabilities.supports_hook` consulted per window

**→ Window Resolver** (depends on `window_resolver.py`):

- Direction: broker depends on window resolver
- Contract type: contract
- What is shared: foreign window ID detection for qualified ID construction
- Contract definition: `is_foreign_window(window_id) -> bool`

**→ Message Spawn** (depends on `handlers/msg_spawn.py`):

- Direction: broker depends on spawn handler for approval flow
- Contract type: functional
- What is shared: spawn request post and approval execution after broker discovers new requests
- Contract definition: `handle_spawn_approval(request_id, bot, spawn_timeout)`, `post_spawn_approval_keyboard(bot, requester_window, request)`

**→ Messaging Telegram UI** (depends on `handlers/msg_telegram.py`):

- Direction: broker depends on Telegram UI for notifications
- Contract type: contract
- What is shared: delivery and loop alert notifications triggered by broker events
- Contract definition: `notify_messages_delivered(bot, to_window, messages)`, `notify_message_sent(bot, from_window, to_window, message)`, `notify_reply_received(bot, original_msg, reply_msg)`, `notify_loop_detected(bot, window_a, window_b)`, `notify_pending_shell(bot, window_id, message)`

**→ Config** (depends on `config.py`):

- Direction: broker depends on config
- Contract type: contract
- What is shared: runtime tunables for spawn and rate limiting
- Contract definition: `config.msg_spawn_timeout`, `config.msg_auto_spawn`, `config.msg_rate_limit`

**← Polling Coordinator** (depended on by `handlers/polling_coordinator.py`):

- Direction: polling coordinator depends on broker
- Contract type: contract
- What is shared: async delivery cycle invocation from poll loop
- Contract definition: `broker_delivery_cycle(mailbox, tmux_mgr, window_states, tmux_session, msg_rate_limit, mailbox_dir, bot, idle_windows)` — called every `BROKER_CYCLE_INTERVAL` seconds; returns delivered message count

## Change Vectors

- Changing delivery strategy (webhook-based delivery instead of `send_keys`) — only injection logic in `broker_delivery_cycle` changes; eligibility filtering, rate limiting, and notification calls remain
- Adding a new idle detection method for a new provider — only the per-window provider capability check changes
- Changing rate limiting algorithm (token bucket instead of sliding window) — only `MessageDeliveryStrategy.check_rate_limit` changes; broker calls remain identical
- Changing loop detection threshold or window — only `_LOOP_THRESHOLD` / `_LOOP_WINDOW_SECONDS` constants change
- Adding delivery confirmation (agent sends ack back to broker) — only the post-injection state update logic changes
- Changing spawn auto-approval policy — only the `if req.auto or config.msg_auto_spawn` gate in `_process_spawn_requests` changes
