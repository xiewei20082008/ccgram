# Mailbox

## Functional Responsibilities

File-based inter-agent mailbox system providing per-window inbox directories under `~/.ccgram/mailbox/`. Each window gets its own subdirectory named by sanitizing the qualified window ID (e.g. `ccgram:@0` → `ccgram=@0`). Atomic writes use a `tmp/` staging directory within each inbox for crash-safe message delivery.

Core capabilities:

- Message CRUD: create (`send`), read with status update (`read`), list inbox (`inbox`, `all_messages`), get without side effects (`get`)
- Reply flow: mark original as `replied`, write reply message to sender's inbox
- Broadcast: fan-out a single message to multiple recipient inboxes
- Status transitions: `pending` → `delivered` (`mark_delivered`), `pending` → `read`, `pending` → `replied`
- TTL expiration: per-message TTL fields; `is_expired()` checked on read; sweep removes expired files
- Sweep: remove expired and terminal-status (`read`, `replied`, `expired`) message files; clean orphaned delivery files in `tmp/`
- Full inbox clear: `clear_inbox(window_id)` removes all messages regardless of status (used on topic close)
- Prune dead inboxes: `prune_dead(live_ids)` removes directories for windows no longer live, preserving foreign (emdash) windows
- ID migration: `migrate_ids(old_to_new)` renames inbox directories and updates `from_id`/`to_id` fields when window IDs are remapped after tmux server restart
- Crash recovery: `pending_undelivered(min_age_seconds)` scans all inboxes for messages that were never marked delivered — used by broker on startup

## Encapsulated Knowledge

- Directory layout: `mailbox/{sanitized_window_id}/` with `tmp/` subdirectory for atomic write staging
- Sanitization: `_sanitize_dir_name()` converts `ccgram:@0` → `ccgram=@0` by replacing the first colon; `_unsanitize_dir_name()` reverses it
- Path traversal guard: `_validate_no_traversal()` rejects values containing `..`, `/`, or `\` — enforced on all externally-supplied IDs before they are used in path construction
- `Message` dataclass fields: `id`, `from_id`, `to_id`, `type`, `body`, `subject`, `reply_to`, `file_path`, `context`, `created_at`, `delivered_at`, `read_at`, `status`, `ttl_minutes`
- Timestamp prefix format for FIFO ordering: nanosecond epoch + 8-char UUID hex (`{ts_ns}-{short_uuid}.json`)
- Default TTL by type: request=60min, reply=120min, notify=240min, broadcast=480min
- Body size limit: 10 KB; larger payloads must use `file_path`
- Valid message types: `request`, `reply`, `notify`, `broadcast`
- Sweepable statuses: `read`, `replied`, `expired`
- Atomic write implementation: `tempfile.mkstemp` in `tmp/`, `os.fsync`, then `os.replace` for rename-atomicity
- Emdash foreign window awareness in `prune_dead`: directories whose unsanitized ID contains `emdash-` are never pruned
- `spawns/` subdirectory is excluded from sweep and prune (owned by `spawn_request.py`)

## Subdomain Classification

**Supporting** — clean data model with well-understood file I/O semantics. No domain-specific business logic beyond message lifecycle state transitions. Changes when message format or storage strategy evolves, not when delivery or notification behavior changes.

## Integration Contracts

**← Message Broker** (depended on by `handlers/msg_broker.py`):

- Direction: broker depends on Mailbox
- Contract type: contract
- What is shared: message enumeration and status mutation during delivery cycles
- Contract definition: `Mailbox.inbox(window_id)`, `Mailbox.mark_delivered(msg_id, window_id)`, `Mailbox.pending_undelivered(min_age_seconds)`. The broker also calls private helpers `_sanitize_dir_name` and `_validate_no_traversal` directly — these should be exposed as `create_delivery_path(inbox_dir, msg_id) -> Path` and `validate_path(path)` to eliminate the private import

**← Messaging CLI** (depended on by `msg_cmd.py`):

- Direction: CLI depends on Mailbox
- Contract type: contract
- What is shared: full message lifecycle operations for human-initiated sends, reads, replies, and broadcasts
- Contract definition: `Mailbox.send()`, `Mailbox.inbox()`, `Mailbox.read()`, `Mailbox.reply()`, `Mailbox.broadcast()`, `Mailbox.sweep()`

**← Messaging Telegram UI** (depended on by `handlers/msg_telegram.py`):

- Direction: Telegram UI depends on Mailbox
- Contract type: model
- What is shared: `Message` dataclass fields for notification text formatting
- Contract definition: `Message` dataclass imported via `TYPE_CHECKING`; fields accessed: `id`, `from_id`, `to_id`, `type`, `body`, `subject`, `reply_to`, `status`

**← Cleanup / Topic State Registry** (depended on by cleanup handlers):

- Direction: cleanup depends on Mailbox
- Contract type: contract
- What is shared: topic-scoped inbox teardown
- Contract definition: `Mailbox.sweep(qualified_id)`, `Mailbox.clear_inbox(qualified_id)`

**→ stdlib only** — zero internal ccgram imports; depends only on `structlog` and Python stdlib

## Change Vectors

- Changing directory structure (flat vs. nested, different sanitization scheme) — only internal path construction and `_sanitize_dir_name` / `_unsanitize_dir_name` change; all callers receive the same `Message` objects
- Adding message fields (priority, attachments, metadata) — extend `Message` dataclass; `from_dict` uses `.get()` with defaults so existing files remain readable; consumers access new fields optionally
- Changing storage backend (files → SQLite, Redis) — public `Mailbox` API unchanged; all I/O is private to the class
- Changing atomic write strategy (e.g. WAL-style, fsync policy) — only `_atomic_write_message` changes
- Adding encryption at rest — only `_atomic_write_message` and the `open()` read calls change
- Adding message compression — only serialization helpers change
