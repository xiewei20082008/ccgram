# Topic State Registry — Test Specification

## Unit Tests

Tests for the module's internal logic in isolation.

| Test name                                               | Scenario                                                                                                                                                                          | Expected behavior                                                            |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `test_register_topic_scope_adds_cleanup_function`       | Register a function with `"topic"` scope via `@topic_state.register("topic")`                                                                                                     | Function stored in registry's topic-scope list; retrievable for dispatch     |
| `test_register_window_scope_adds_cleanup_function`      | Register a function with `"window"` scope via `@topic_state.register("window")`                                                                                                   | Function stored in registry's window-scope list; retrievable for dispatch    |
| `test_register_qualified_scope_adds_cleanup_function`   | Register a function with `"qualified"` scope via `@topic_state.register("qualified")`                                                                                             | Function stored in registry's qualified-scope list; retrievable for dispatch |
| `test_clear_topic_calls_topic_scoped_functions`         | Register 3 topic-scoped `MagicMock` cleanups; call `clear_topic(user_id=1, thread_id=42)`                                                                                         | All 3 mocks called exactly once, each with `(user_id=1, thread_id=42)`       |
| `test_clear_window_calls_window_scoped_functions`       | Register 3 window-scoped `MagicMock` cleanups; call `clear_window(window_id="@0")`                                                                                                | All 3 mocks called exactly once, each with `(window_id="@0")`                |
| `test_clear_qualified_calls_qualified_scoped_functions` | Register 2 qualified-scoped `MagicMock` cleanups; call `clear_qualified(qualified_id="ccgram:@0")`                                                                                | Both mocks called exactly once, each with `(qualified_id="ccgram:@0")`       |
| `test_clear_all_calls_all_scopes`                       | Register one cleanup per scope (topic, window, qualified); call `clear_all(user_id=1, thread_id=42, window_id="@0", qualified_id="ccgram:@0")`                                    | All three cleanups called with their respective keys                         |
| `test_deduplication_prevents_double_registration`       | Register the same function object twice under `"topic"` scope; call `clear_topic`                                                                                                 | Function called exactly once (not twice)                                     |
| `test_clear_all_resolves_chat_id`                       | Register a legacy cleanup expecting `(chat_id, thread_id)`; inject a `thread_router` mock where `resolve_chat_id(user_id=1, thread_id=42)` returns `chat_id=99`; call `clear_all` | Cleanup invoked with `(chat_id=99, thread_id=42)`                            |

## Integration Contract Tests

Tests that verify the module honors its integration contracts.

| Test name                                    | Scenario                                                                                                                                                 | Expected behavior                                                                                                               |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `test_cleanup_py_uses_registry`              | Inspect `cleanup.py` source; verify it calls `topic_state.clear_all(...)` and does not directly import more than one handler module for cleanup purposes | `cleanup.py` delegates entirely to `topic_state.clear_all`; the 14-lazy-import pattern is absent                                |
| `test_handler_modules_self_register`         | Import a representative stateful handler module (e.g., `shell_commands`, `command_history`); inspect `topic_state` registry after import                 | Registry contains at least one cleanup function contributed by that module without any explicit registration call from the test |
| `test_chat_id_resolution_uses_thread_router` | Provide a mock `thread_router` with `resolve_chat_id`; register a legacy-style cleanup; call `clear_all` with `user_id` and `thread_id`                  | `thread_router.resolve_chat_id` called with `(user_id, thread_id)`; result forwarded to the cleanup function                    |

## Boundary Tests

Tests that verify the module correctly rejects invalid inputs and maintains encapsulation.

| Test name                                       | Scenario                                                                                                                | Expected behavior                                                                                     |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `test_clear_topic_with_no_registered_functions` | No functions registered; call `clear_topic(user_id=1, thread_id=42)`                                                    | Returns without error; no exception raised                                                            |
| `test_clear_with_failing_cleanup_function`      | Register three topic-scoped cleanups where the second raises `RuntimeError`; call `clear_topic`                         | First and third cleanups still called; exception from second is caught and does not propagate         |
| `test_register_invalid_scope_raises`            | Call `@topic_state.register("nonexistent_scope")`                                                                       | Raises `ValueError`                                                                                   |
| `test_clear_all_with_missing_window_id`         | Call `clear_all(user_id=1, thread_id=42, window_id=None, qualified_id=None)` with only topic-scoped cleanups registered | Topic-scoped cleanups called normally; window-scoped and qualified-scoped dispatch skipped gracefully |

## Behavior Tests

Tests that verify the module's functional responsibilities from an outside-in perspective.

| Test name                                   | Scenario                                                                                                                          | Expected behavior                                                                          |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `test_full_topic_cleanup_lifecycle`         | Register cleanup mocks from 5 simulated "handler modules" across topic and window scopes; call `clear_all`                        | All 5 mocks called with correct arguments; no leftover calls or missed cleanups            |
| `test_new_feature_registration_pattern`     | Define a new stateful dict; register a cleanup for it via `@topic_state.register("topic")`; populate the dict; call `clear_topic` | Dict entry for the given `(user_id, thread_id)` removed after cleanup                      |
| `test_cleanup_ordering_topic_before_window` | Register one topic-scoped and one window-scoped cleanup, both recording call order via a shared list; call `clear_all`            | Topic-scoped cleanup appears earlier in the call-order list than the window-scoped cleanup |
