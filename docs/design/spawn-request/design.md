# Spawn Request

## Functional Responsibilities

Manages the agent spawn request lifecycle from creation through approval, denial, or expiry. Provides pure data functions that are safe to call from both the CLI (no bot token) and the bot process (full handler context).

Core capabilities:

- `SpawnRequest` dataclass: the canonical data model for a pending spawn request written to disk and held in the in-memory cache
- `SpawnResult` dataclass: the success outcome returned after a window is created
- Request creation: `create_spawn_request(requester_window, provider, cwd, prompt, ...)` validates the `cwd`, generates a request ID, writes a JSON file to `mailbox/spawns/`, records a spawn timestamp, and populates the in-memory cache
- Disk persistence: each request is written to `mailbox/spawns/{request_id}.json` via `atomic_write_json` for crash recovery
- In-memory cache: `_pending_requests: dict[str, SpawnRequest]` — private; broker and spawn handler access it only through the public accessor API
- Spawn rate limiting: `check_spawn_rate(window_id, max_rate)` loads a `rate_log.json` from `mailbox/spawns/`, counts timestamps within the last hour, and returns whether the window is within limits; `record_spawn(window_id)` appends the current timestamp and prunes old entries
- Max window check: `check_max_windows(window_states, max_windows)` compares live window count against the configured ceiling
- Broker-side scan: `scan_spawn_requests(spawn_timeout)` reads new `.json` files from `mailbox/spawns/`, loads them into `_pending_requests`, evicts expired cached requests (and deletes their files), and returns newly discovered requests for the broker to route
- Window-scoped cleanup: `clear_spawn_state(window_id)` removes all pending requests from cache and disk whose `requester_window` matches the given ID
- Process reset: `reset_spawn_state()` clears the in-memory cache (used in tests)

## Encapsulated Knowledge

- `_pending_requests: dict[str, SpawnRequest]` — private in-process cache; never exported directly; accessed only through `scan_spawn_requests`, `create_spawn_request`, and the accessor API
- Spawn request file layout: `mailbox/spawns/{request_id}.json`; rate log: `mailbox/spawns/rate_log.json`
- `SpawnRequest` fields: `id`, `requester_window`, `provider`, `cwd`, `prompt`, `context_file`, `auto`, `created_at`
- `SpawnResult` fields: `window_id`, `window_name`
- Request ID format: `{int(time.time())}-{uuid4.hex[:8]}`
- Expiry check: `SpawnRequest.is_expired(timeout)` compares `time.time() - created_at` against the `spawn_timeout` parameter
- Rate window: `_SPAWN_RATE_WINDOW_SECONDS = 3600` (1 hour)
- Rate log file format: `{window_id: [timestamp, ...]}` JSON; pruned of old entries on each `record_spawn` call
- `scan_spawn_requests` dual responsibility: evicts stale cached requests AND discovers new disk requests — both must run on the same call to prevent the cache from growing unbounded
- Files with name `rate_log.json` are skipped during `scan_spawn_requests` iteration
- `clear_spawn_state` scans both the in-memory cache and disk to handle requests created in another process

## Subdomain Classification

**Supporting** — well-defined approval/denial lifecycle; changes when spawn safety rules, rate limiting policy, or the `SpawnRequest` data model evolves. Does not own Telegram or tmux logic, keeping it safe for CLI use.

## Integration Contracts

**Public accessor API** (replaces direct `_pending_requests` dict access):

```python
def get_pending(request_id: str) -> SpawnRequest | None: ...
def pop_pending(request_id: str) -> SpawnRequest | None: ...
def iter_pending() -> Iterator[tuple[str, SpawnRequest]]: ...
def register_pending(request: SpawnRequest) -> None: ...
def scan_spawn_requests(spawn_timeout: int = 300) -> list[SpawnRequest]: ...
def check_max_windows(window_states: dict, max_windows: int) -> bool: ...
def check_spawn_rate(window_id: str, rate_limit: int) -> bool: ...
```

**← Message Broker** (depended on by `handlers/msg_broker.py`):

- Direction: broker depends on Spawn Request
- Contract type: contract
- What is shared: pending request discovery for routing to approval keyboards or auto-approval
- Contract definition: `scan_spawn_requests(spawn_timeout)` returns `list[SpawnRequest]`; `pop_pending(request_id)` for cache eviction on failure (currently `_pending_requests.pop(req.id, None)`)

**← Message Spawn handler** (depended on by `handlers/msg_spawn.py`):

- Direction: spawn handler depends on Spawn Request
- Contract type: contract
- What is shared: request lifecycle — pop on approval/denial, expiry check, window limit check
- Contract definition: `pop_pending(request_id)`, `register_pending(request)`, `check_max_windows(window_states, max_windows)`, `check_spawn_rate(window_id, rate_limit)`, `SpawnRequest.is_expired(timeout)`, `_spawns_dir()` for file cleanup after approval

**← Messaging CLI** (depended on by `msg_cmd.py`):

- Direction: CLI depends on Spawn Request
- Contract type: contract
- What is shared: spawn request creation and rate/window validation from the `ccgram msg spawn` subcommand
- Contract definition: `create_spawn_request(requester_window, provider, cwd, prompt, context_file, auto)`, `check_max_windows(window_states, max_windows)`, `check_spawn_rate(window_id, rate_limit)`

**← Topic State Registry** (depended on by cleanup handlers):

- Direction: cleanup depends on Spawn Request
- Contract type: contract
- What is shared: window-scoped spawn state teardown on topic close
- Contract definition: `clear_spawn_state(qualified_id)` registered as window close callback

**→ Utils** (depends on `utils.py`):

- Direction: Spawn Request depends on Utils
- Contract type: contract
- What is shared: atomic file write and config directory resolution
- Contract definition: `atomic_write_json(path, data)`, `ccgram_dir() -> Path`

## Change Vectors

- Adding `SpawnRequest` fields (priority, resource limits, environment variables) — only the dataclass and `from_dict`/`to_dict` change; `scan_spawn_requests` and file format evolve; callers access new fields optionally via `getattr`/`.get()`
- Changing rate limiting algorithm (per-provider rate, global cap) — only `check_spawn_rate` and `record_spawn` change; callers pass `max_rate` and receive `bool`
- Adding auto-approval policies (trust lists, provider-specific caps) — only validation logic in `check_spawn_rate` / `check_max_windows` changes; callers remain unchanged
- Changing persistence format (SQLite instead of flat JSON files) — only `_spawns_dir`, `create_spawn_request`, `scan_spawn_requests`, and `clear_spawn_state` change; the accessor API is unchanged
- Changing request ID format — only `create_spawn_request` changes; consumers treat the ID as an opaque string
