# Mailbox — Test Specification

## Unit Tests

Tests for the module's internal logic in isolation.

- **Test name**: `test_create_message_writes_json_atomically`
  - **Scenario**: Call `Mailbox.send()` with a valid `from_id`, `to_id`, and body; inspect the resulting file in the inbox directory
  - **Expected behavior**: A `{msg_id}.json` file exists under `base_dir/{sanitized_to_id}/`; the JSON is valid and contains `id`, `from_id`, `to_id`, `type`, `body`, `status="pending"`, and `created_at`; no partial `.json` files exist in `tmp/`

- **Test name**: `test_read_marks_message_as_read`
  - **Scenario**: Send a message, then call `Mailbox.read(msg_id, window_id)` on the recipient's inbox
  - **Expected behavior**: The returned `Message` has `status="read"` and `read_at` is a non-empty ISO timestamp; the on-disk JSON file reflects the same change

- **Test name**: `test_list_inbox_returns_fifo_order`
  - **Scenario**: Send three messages to the same window with small time delays between them so their timestamp-prefixed filenames sort differently
  - **Expected behavior**: `Mailbox.inbox(window_id)` returns the messages in oldest-first order (ascending by filename prefix)

- **Test name**: `test_sweep_removes_expired_messages`
  - **Scenario**: Write a message whose `created_at` is far in the past (beyond its `ttl_minutes`) and a second message that is still valid; call `Mailbox.sweep(window_id)`
  - **Expected behavior**: The expired message file is deleted from disk; the valid message file remains; `sweep()` returns `1`

- **Test name**: `test_prune_dead_removes_orphaned_inboxes`
  - **Scenario**: Create inbox directories for two window IDs; pass only one of them as a `live_id` to `Mailbox.prune_dead()`
  - **Expected behavior**: The inbox directory for the non-live window ID is removed from disk; the live window's directory is preserved; `prune_dead()` returns `1`

- **Test name**: `test_sanitize_dir_name_handles_special_chars`
  - **Scenario**: Call `_sanitize_dir_name` with qualified IDs containing colons and `@` signs (e.g. `ccgram:@0`, `ccgram:@12`)
  - **Expected behavior**: The colon is replaced with `=` (`ccgram=@0`, `ccgram=@12`); `@` is preserved as-is; the result contains no colon and is a valid directory name on all platforms

- **Test name**: `test_create_delivery_path_returns_valid_path`
  - **Scenario**: Call `Mailbox.create_delivery_path(inbox_dir, msg_id)` (or equivalent public helper) with a valid `window_id` and `msg_id`
  - **Expected behavior**: The returned path is under `base_dir/{sanitized_window_id}/tmp/deliver-{msg_id}.txt`; the `tmp/` directory is created if it does not exist

- **Test name**: `test_validate_path_rejects_traversal`
  - **Scenario**: Call `_validate_no_traversal` (or the public `validate_path` wrapper) with a string containing `../`, `//`, or `\`
  - **Expected behavior**: `ValueError` is raised for each traversal attempt; plain IDs like `ccgram:@0` pass without error

## Integration Contract Tests

Tests that verify the module honors its integration contracts.

- **Test name**: `test_broker_uses_create_delivery_path`
  - **Scenario**: The broker calls `write_delivery_file` for a long-body message; verify the path it constructs matches what the `Mailbox` public API (`create_delivery_path`) would return
  - **Expected behavior**: The delivery file appears at the path returned by the public Mailbox API, not at a path constructed by calling private `_sanitize_dir_name` directly; the file is readable and contains the full message body

- **Test name**: `test_cli_reads_inbox_via_public_api`
  - **Scenario**: Use `Mailbox.send()` to write a message, then use `Mailbox.inbox()` and `Mailbox.read()` to retrieve and mark it — simulating the `ccgram msg inbox` / `ccgram msg read` CLI flow
  - **Expected behavior**: `inbox()` returns the message with `status="pending"`; `read()` transitions it to `status="read"` and returns the updated message; a second call to `inbox()` no longer returns the read message

- **Test name**: `test_sweep_called_from_topic_state_registry`
  - **Scenario**: Populate an inbox for a qualified `window_id`, then call `Mailbox.sweep(qualified_id)` and `Mailbox.clear_inbox(qualified_id)` using the same qualified ID format used by cleanup handlers (`ccgram:@0`)
  - **Expected behavior**: `sweep()` removes expired/terminal messages; `clear_inbox()` removes all remaining messages regardless of status; neither call raises an error for an unknown `window_id`

## Boundary Tests

Tests that verify the module correctly rejects invalid inputs and maintains encapsulation.

- **Test name**: `test_create_message_with_empty_body`
  - **Scenario**: Call `Mailbox.send()` with `body=""`
  - **Expected behavior**: The message is written successfully; `inbox()` returns it with `body=""`; no `ValueError` is raised

- **Test name**: `test_create_message_with_oversized_body`
  - **Scenario**: Call `Mailbox.send()` with a `body` that exceeds 10 KB (10,241 bytes of UTF-8 text)
  - **Expected behavior**: `ValueError` is raised with a message mentioning the size limit and suggesting `--file`; no file is written to the inbox

- **Test name**: `test_read_nonexistent_message`
  - **Scenario**: Call `Mailbox.read()` with a `msg_id` that does not exist in the inbox
  - **Expected behavior**: Returns `None`; no exception is raised; the inbox directory is unchanged

- **Test name**: `test_concurrent_writes_to_same_inbox`
  - **Scenario**: Call `Mailbox.send()` twice concurrently (using `asyncio.gather`) targeting the same `to_id`
  - **Expected behavior**: Both calls succeed; `inbox()` returns two messages; no corrupted or partial JSON files are present in the inbox directory

- **Test name**: `test_prune_dead_preserves_emdash_sessions`
  - **Scenario**: Create an inbox directory for a foreign window ID containing `emdash-` (e.g. `emdash-claude-main-abc123:@0`); call `Mailbox.prune_dead({})` with an empty live set
  - **Expected behavior**: The emdash inbox directory is not removed; `prune_dead()` returns `0`

## Behavior Tests

Tests that verify the module's functional responsibilities from an outside-in perspective.

- **Test name**: `test_full_message_lifecycle`
  - **Scenario**: Send a `request` message → list inbox → deliver (mark delivered) → read → run `sweep()`
  - **Expected behavior**: After send, `inbox()` returns the message with `status="pending"`; after `mark_delivered()`, `inbox()` returns it with `status="delivered"`; after `read()`, the message has `status="read"` and `read_at` set; after `sweep()`, the file is removed from disk

- **Test name**: `test_broadcast_delivers_to_all_peers`
  - **Scenario**: Call `Mailbox.broadcast(from_id, [peer_1, peer_2, peer_3], body)` with three recipient IDs
  - **Expected behavior**: Each recipient's `inbox()` contains exactly one `broadcast` message from `from_id` with the same `body`; the broadcast call returns a list of three `Message` objects; no cross-inbox contamination (peer_1's inbox only contains peer_1's message)

- **Test name**: `test_message_ordering_preserved_across_operations`
  - **Scenario**: Send messages A, B, C; read message B; send message D; call `all_messages()` on the inbox
  - **Expected behavior**: `all_messages()` returns A, C, D in timestamp order (B is omitted since it is `read` status and `all_messages` still returns it, but FIFO order by timestamp is preserved); `inbox()` returns only A, C, D (the unread/pending/delivered subset) in the same order
