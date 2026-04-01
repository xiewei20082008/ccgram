# Messaging CLI — Test Specification

## Unit Tests

Tests for the module's internal logic in isolation.

| Test name                                | Scenario                                                                                                                                        | Expected behavior                                                                   |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `test_list_peers_outputs_json_format`    | Mock `list_peers()` to return two `PeerInfo` objects; invoke `msg list-peers --json` via Click test runner                                      | Output is valid JSON; each entry contains `window_id`, `provider`, and `cwd` fields |
| `test_send_creates_message_in_inbox`     | Mock `Mailbox.create` and `export_window_info` returning `{"@0": ...}`; invoke `msg send @0 "hello"`                                            | `Mailbox.create()` called once with recipient `window_id="@0"` and body `"hello"`   |
| `test_inbox_lists_messages`              | Mock `Mailbox.list_inbox` returning two message dicts; invoke `msg inbox`                                                                       | Both messages appear in stdout output                                               |
| `test_read_marks_message`                | Mock `Mailbox.read`; invoke `msg read msg-001`                                                                                                  | `Mailbox.read(msg_id="msg-001")` called exactly once                                |
| `test_broadcast_sends_to_matching_peers` | Mock `list_peers` returning 3 peers, two with `team="backend"`; mock `Mailbox.create`; invoke `msg broadcast "hello" --team backend`            | `Mailbox.create()` called exactly twice (only matching peers)                       |
| `test_spawn_creates_request`             | Mock `create_spawn_request`, `check_max_windows` returning ok, `check_spawn_rate` returning ok; invoke `msg spawn --provider claude --cwd /tmp` | `create_spawn_request()` called once with `provider="claude"` and `cwd="/tmp"`      |
| `test_sweep_cleans_expired`              | Mock `Mailbox.sweep`; invoke `msg sweep`                                                                                                        | `Mailbox.sweep()` called exactly once                                               |

## Integration Contract Tests

Tests that verify the module honors its integration contracts.

| Test name                                | Scenario                                                                                                                      | Expected behavior                                                                                                      |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `test_cli_uses_export_window_info`       | Patch `export_window_info` on the session state module; invoke any `msg` subcommand that needs window data (e.g., `msg send`) | `export_window_info()` called; `state.json` file never opened directly by the CLI                                      |
| `test_cli_uses_mailbox_public_api`       | Patch `Mailbox` class methods; invoke `msg send`, `msg inbox`, `msg read`, `msg sweep`                                        | Each command routes through the corresponding `Mailbox` public method; no direct file I/O to mailbox dir from CLI code |
| `test_cli_uses_spawn_request_public_api` | Patch `create_spawn_request`, `check_max_windows`, `check_spawn_rate`; invoke `msg spawn --provider claude --cwd /tmp`        | All three spawn-request public functions called in correct order                                                       |

## Boundary Tests

Tests that verify the module correctly rejects invalid inputs and maintains encapsulation.

| Test name                              | Scenario                                                                                           | Expected behavior                                                                                               |
| -------------------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `test_send_to_nonexistent_peer`        | Mock `export_window_info` returning no windows; invoke `msg send @99 "hello"`                      | Command exits with non-zero status; stderr contains a helpful error message referencing the unknown `window_id` |
| `test_send_with_empty_body`            | Invoke `msg send @0 ""` with an empty body string                                                  | Command exits with non-zero status or `Mailbox.create` never called; no silent empty message created            |
| `test_spawn_when_max_windows_exceeded` | Mock `check_max_windows` raising an error or returning a limit-exceeded signal; invoke `msg spawn` | Command exits with non-zero status; error message mentions window limit                                         |
| `test_list_peers_with_no_sessions`     | Mock `list_peers` returning an empty list; invoke `msg list-peers`                                 | Exits with zero status; output indicates no peers (empty list or "no peers" message); no crash                  |

## Behavior Tests

Tests that verify the module's functional responsibilities from an outside-in perspective.

| Test name                                    | Scenario                                                                                                                                      | Expected behavior                                                                                                                                           |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_send_and_receive_roundtrip`            | Use a real temporary mailbox directory; invoke `msg send @0 "ping"` targeting `window_id="@0"`; invoke `msg inbox` for `window_id="@0"`       | Inbox lists the message; `msg read <id>` returns body `"ping"`                                                                                              |
| `test_spawn_approval_lifecycle`              | Mock `check_max_windows` and `check_spawn_rate` returning ok; invoke `msg spawn --provider claude --cwd /tmp`; inspect the spawn request file | A JSON file exists in `mailbox/` containing `provider="claude"`, `cwd="/tmp"`, and a `status` field scannable by the broker                                 |
| `test_context_cache_populated_on_first_send` | Clear `_CONTEXT_CACHE`; mock `export_window_info` returning one window; invoke `msg send @0 "hello"`                                          | `export_window_info` called exactly once during the send; a subsequent call with the same process uses the cache without calling `export_window_info` again |
