# Spawn Request — Test Specification

## Unit Tests

Tests for the module's internal logic in isolation.

- **Test name**: `test_register_pending_stores_request`
  - **Scenario**: Call `register_pending(request)` with a `SpawnRequest` instance; then call `get_pending(request.id)`
  - **Expected behavior**: `get_pending` returns the same `SpawnRequest` object; the in-memory cache contains exactly one entry for that ID

- **Test name**: `test_pop_pending_removes_and_returns`
  - **Scenario**: Register a `SpawnRequest` via `register_pending`; call `pop_pending(request.id)`
  - **Expected behavior**: The returned value is the registered `SpawnRequest`; a subsequent `get_pending(request.id)` returns `None`; the cache no longer contains the ID

- **Test name**: `test_pop_pending_nonexistent_returns_none`
  - **Scenario**: Call `pop_pending("unknown-id-999")` without registering any request with that ID
  - **Expected behavior**: Returns `None`; no exception is raised; the cache is unaffected

- **Test name**: `test_iter_pending_yields_all`
  - **Scenario**: Register three `SpawnRequest` objects with distinct IDs; call `iter_pending()`
  - **Expected behavior**: The iterator yields exactly three `(id, SpawnRequest)` pairs; each registered ID appears exactly once

- **Test name**: `test_check_max_windows_enforces_limit`
  - **Scenario**: Call `check_max_windows(window_states, max_windows=5)` where `window_states` contains exactly 5 entries
  - **Expected behavior**: Returns `False` (at capacity); with 4 entries it returns `True` (room to spawn)

- **Test name**: `test_check_spawn_rate_enforces_limit`
  - **Scenario**: Call `record_spawn(window_id)` `max_rate` times within `_SPAWN_RATE_WINDOW_SECONDS`; then call `check_spawn_rate(window_id, max_rate)`
  - **Expected behavior**: Returns `False` (rate limit reached); after the rate window expires (mock `time.time`), `check_spawn_rate` returns `True` again

- **Test name**: `test_create_spawn_request_persists_to_disk`
  - **Scenario**: Call `create_spawn_request(requester_window, provider, cwd, prompt)` with a valid `cwd` (a real existing directory)
  - **Expected behavior**: A JSON file named `{request_id}.json` exists under `mailbox/spawns/`; the file contains all `SpawnRequest` fields; `get_pending(request_id)` returns the request from the in-memory cache

- **Test name**: `test_scan_spawn_requests_reads_from_disk`
  - **Scenario**: Write two `SpawnRequest` JSON files directly to `mailbox/spawns/` without going through `create_spawn_request`; call `scan_spawn_requests()`
  - **Expected behavior**: Both requests are returned in the result list; both are now in the in-memory cache via `get_pending`; the `rate_log.json` file (if present) is not returned as a request

- **Test name**: `test_clear_spawn_state_removes_pending_for_window`
  - **Scenario**: Register two requests for `window_a` and one for `window_b`; call `clear_spawn_state(window_a)`
  - **Expected behavior**: `get_pending` returns `None` for both `window_a` request IDs; `window_b`'s request is unaffected; the corresponding JSON files for `window_a` requests are deleted from disk

## Integration Contract Tests

Tests that verify the module honors its integration contracts.

- **Test name**: `test_broker_uses_accessor_api`
  - **Scenario**: Inspect `msg_broker._process_spawn_requests` for direct access to `_pending_requests`; verify no code path touches `_pending_requests` directly in the broker — only `scan_spawn_requests` (discovery) and `pop_pending` (eviction) are called
  - **Expected behavior**: The broker module does not import or reference `_pending_requests` as a module-level symbol; all interactions go through the public accessor functions

- **Test name**: `test_spawn_handler_uses_accessor_api`
  - **Scenario**: In `handle_spawn_approval`, verify the request is fetched via `pop_pending(request_id)` rather than `_pending_requests.pop(request_id, None)` directly
  - **Expected behavior**: After `handle_spawn_approval` completes, `get_pending(request_id)` returns `None`; the pop happened through the public API

- **Test name**: `test_cleanup_via_topic_state_registry`
  - **Scenario**: Register requests for a qualified window ID (`ccgram:@5`); call `clear_spawn_state("ccgram:@5")` as the topic state registry does on topic close
  - **Expected behavior**: All requests for `ccgram:@5` are removed from cache and disk; no exception raised for an unrecognized qualified ID format

## Boundary Tests

Tests that verify the module correctly rejects invalid inputs and maintains encapsulation.

- **Test name**: `test_register_duplicate_id_overwrites`
  - **Scenario**: Call `register_pending(request_v1)` and then `register_pending(request_v2)` where both have the same `id` but different `prompt` values
  - **Expected behavior**: `get_pending(request_id)` returns `request_v2` (latest registration wins); no duplicate entries exist in the cache

- **Test name**: `test_expired_request_not_returned`
  - **Scenario**: Write a `SpawnRequest` JSON file to disk with `created_at` set to a timestamp older than `spawn_timeout=300` seconds; call `scan_spawn_requests(spawn_timeout=300)`
  - **Expected behavior**: The expired request is not returned in the result list; the JSON file is deleted from disk; the request is not added to the in-memory cache

- **Test name**: `test_empty_spawns_directory`
  - **Scenario**: Call `scan_spawn_requests()` when `mailbox/spawns/` either does not exist or contains no `.json` files (only possibly `rate_log.json`)
  - **Expected behavior**: Returns an empty list; no exception is raised; the spawns directory is not created by `scan_spawn_requests` alone

## Behavior Tests

Tests that verify the module's functional responsibilities from an outside-in perspective.

- **Test name**: `test_full_spawn_lifecycle`
  - **Scenario**: Create a spawn request via `create_spawn_request` → scan it via `scan_spawn_requests` → approve it via `pop_pending` → verify it is cleared from cache and disk
  - **Expected behavior**:
    1. `create_spawn_request` writes a JSON file and caches the request
    2. `scan_spawn_requests` is a no-op (request already cached) — no duplicate in result
    3. `pop_pending(request_id)` returns the request and removes it from cache
    4. The JSON file is removed from disk (by the caller, after `pop_pending`)
    5. `get_pending(request_id)` returns `None`

- **Test name**: `test_rate_limited_spawn_rejected`
  - **Scenario**: Exhaust the spawn rate for `window_id` by recording `max_rate` spawns; attempt to create another spawn request from the same window
  - **Expected behavior**: `check_spawn_rate(window_id, max_rate)` returns `False`; the caller (CLI or broker) does not call `create_spawn_request`; no new JSON file is written to disk
