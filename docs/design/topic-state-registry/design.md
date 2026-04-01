# Topic State Registry

## Functional Responsibilities

- Provide a centralized registry where modules register their per-topic and per-window cleanup functions
- Replace cleanup.py's 14 lazy imports with a self-registration pattern (like callback_registry's @register)
- Two primary scopes: "topic" (keyed by user_id + thread_id) and "window" (keyed by window_id)
- Additional scope: "qualified" (keyed by qualified_id like "session:@0") for mailbox/delivery/spawn state
- `clear_topic(user_id, thread_id)` — calls all topic-scoped cleanups
- `clear_window(window_id)` — calls all window-scoped cleanups
- `clear_qualified(qualified_id)` — calls all qualified-scoped cleanups
- `clear_all(user_id, thread_id, window_id, qualified_id)` — full cleanup orchestration
- Resolve chat_id from thread_router when needed for backward-compat modules using (chat_id, thread_id)

## Encapsulated Knowledge

- Registry data structure: `dict[str, list[Callable]]` mapping scope names to cleanup function lists
- Scope resolution: which key type each scope uses and how to derive it
- The translation from (user_id, thread_id) to (chat_id, thread_id) via thread_router.resolve_chat_id()
- The translation from window_id to qualified_id via tmux_session_name()
- Registration deduplication (prevent double-registration on re-import)
- Cleanup ordering (topic-scoped first, then window-scoped, then qualified-scoped)

## Subdomain Classification

Core — most volatile integration point; every new stateful feature must register here, but the registration is a one-liner, not a cross-module edit.

## Integration Contracts

- ← All stateful handler modules (depended on by): Contract — modules import `@topic_state.register(scope)` decorator and annotate their cleanup functions at module level

  ```python
  # Example usage in any handler module:
  from ..topic_state_registry import topic_state

  @topic_state.register("window")
  def clear_shell_monitor_state(window_id: str) -> None:
      _shell_monitor_state.pop(window_id, None)

  @topic_state.register("topic")
  def clear_history(user_id: int, thread_id: int) -> None:
      _history.pop((user_id, thread_id), None)
  ```

- ← cleanup.py (depended on by): Contract — cleanup.py calls `topic_state.clear_all(user_id, thread_id, window_id, qualified_id)`; becomes ~20 lines instead of 14 lazy imports
- → Thread Router (depends on): Contract — `thread_router.resolve_chat_id(user_id, thread_id)` for legacy (chat_id, thread_id) modules
- → Utils (depends on): Contract — `tmux_session_name()` for qualified_id construction

## Change Vectors

- Adding a new scope (e.g., "pane" for per-pane state) — add scope handler; existing registrations unaffected
- Adding cleanup verification (e.g., assert all state cleared) — add post-clear validation
- Adding cleanup ordering constraints — add priority parameter to register()
- Changing key derivation (e.g., drop chat_id translation when modules standardize) — only derivation logic changes
