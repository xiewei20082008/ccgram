# Messaging CLI

## Functional Responsibilities

- Provide `ccgram msg` CLI subcommand group (Click-based)
- Subcommands: list-peers, find, send, inbox, read, reply, broadcast, register, spawn, sweep
- Discover peers via msg_discovery module (SessionManager-independent path)
- Read window states via `export_window_info()` from Session State (explicit contract, not raw state.json parsing)
- Build message context from window state for LLM-powered agents

## Encapsulated Knowledge

- Click command definitions and argument parsing
- CLI output formatting (JSON mode, table mode, human-readable)
- `_CONTEXT_CACHE: dict[str, str] | None` — per-process cache for message context building
- Wait-file convention (`mailbox/.waiting-{id}`) for synchronous `--wait` flag
- Rate limit env var resolution for CLI context (outside bot process)

## Subdomain Classification

Generic — thin CLI wrapper; stable once commands are defined.

## Integration Contracts

- → Mailbox (depends on): Contract — `Mailbox.create()`, `Mailbox.list_inbox()`, `Mailbox.read()`, `Mailbox.sweep()`
- → Session State (depends on): Contract — `export_window_info() -> dict[str, WindowInfo]` (new public function, replaces raw state.json parsing)
- → Msg Discovery (depends on): Contract — `list_peers()`, `register_declared()`, `_detect_branch()`, `WindowInfo`, `PeerInfo`
- → Spawn Request (depends on): Contract — `create_spawn_request()`, `check_max_windows()`, `check_spawn_rate()`
- → Utils (depends on): Contract — `ccgram_dir()`, `tmux_session_name()`

## Change Vectors

- Adding a new CLI subcommand — add Click command function; no other module changes
- Changing output format — only formatting logic changes
- Adding CLI authentication — only command middleware changes
- Changing context cache strategy — only `_CONTEXT_CACHE` logic changes
