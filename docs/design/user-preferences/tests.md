# User Preferences — Test Specification

## Unit Tests

Tests for the module's internal logic in isolation.

| Test name                                      | Scenario                                                                                                                       | Expected behavior                                                             |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| `test_get_user_starred_empty_by_default`       | Construct a fresh `UserPreferences`; call `get_user_starred(user_id=1)`                                                        | Returns an empty `set`                                                        |
| `test_toggle_user_star_adds_path`              | Call `toggle_user_star(user_id=1, path="/home/user/proj")` on a fresh instance                                                 | Path present in `get_user_starred(user_id=1)`                                 |
| `test_toggle_user_star_removes_existing`       | Star a path; call `toggle_user_star` again with the same path                                                                  | Path absent from `get_user_starred(user_id=1)`                                |
| `test_toggle_user_star_returns_new_state`      | Toggle a fresh path (not yet starred); capture return value; then toggle the same path again                                   | First call returns `True`; second call returns `False`                        |
| `test_get_user_mru_empty_by_default`           | Construct a fresh `UserPreferences`; call `get_user_mru(user_id=1)`                                                            | Returns an empty `list`                                                       |
| `test_update_user_mru_adds_to_front`           | Call `update_user_mru` with paths `"/a"`, `"/b"`, `"/c"` in order                                                              | `get_user_mru` returns `["/c", "/b", "/a"]`                                   |
| `test_update_user_mru_moves_existing_to_front` | Pre-populate MRU with `["/a", "/b", "/c"]`; call `update_user_mru(user_id=1, path="/b")`                                       | MRU is `["/b", "/a", "/c"]` with no duplicates                                |
| `test_update_user_mru_evicts_oldest_at_max`    | Add 11 distinct paths; inspect MRU list                                                                                        | List length is 10; the first path added is absent                             |
| `test_get_user_window_offset_default_zero`     | Call `get_user_window_offset(user_id=1, window_id="@0")` on a fresh instance                                                   | Returns `0`                                                                   |
| `test_update_user_window_offset_persists`      | Call `update_user_window_offset(user_id=1, window_id="@0", offset=1024)`; then call `get_user_window_offset` with the same key | Returns `1024`                                                                |
| `test_to_dict_serializes_all_state`            | Set starred path, two MRU paths, and one window offset; call `to_dict()`                                                       | Returned dict contains keys for starred, MRU, and offsets with correct values |
| `test_from_dict_restores_all_state`            | Build a dict with starred, MRU, and offset entries; call `from_dict(data)`; inspect all three getters                          | All values match the input dict                                               |

## Integration Contract Tests

Tests that verify the module honors its integration contracts.

| Test name                                    | Scenario                                                                                                             | Expected behavior                                                    |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `test_session_state_calls_to_dict_on_save`   | Create a `UserPreferences` instance; inject it into a `SessionManager` mock; trigger a save via the `SessionManager` | `user_preferences.to_dict()` is called exactly once during the save  |
| `test_session_state_calls_from_dict_on_load` | Provide a state dict containing a `user_preferences` key; load it via `SessionManager`                               | `user_preferences.from_dict(data)` called with the matching sub-dict |
| `test_schedule_save_called_on_mutation`      | Provide a `schedule_save` mock to `UserPreferences`; call `toggle_user_star`                                         | `schedule_save()` called at least once after the mutation            |

## Boundary Tests

Tests that verify the module correctly rejects invalid inputs and maintains encapsulation.

| Test name                                    | Scenario                                                    | Expected behavior                                                              |
| -------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `test_toggle_star_with_empty_path`           | Call `toggle_user_star(user_id=1, path="")`                 | No exception; empty string treated as a valid (unusual) path                   |
| `test_update_mru_with_duplicate_consecutive` | Call `update_user_mru(user_id=1, path="/a")` twice in a row | `get_user_mru` contains `"/a"` exactly once                                    |
| `test_from_dict_with_missing_keys`           | Call `from_dict({})` (empty dict)                           | All getters return their defaults (empty set, empty list, zero); no `KeyError` |
| `test_from_dict_with_extra_keys`             | Call `from_dict({"starred": {}, "unknown_future_key": 42})` | No exception; known keys loaded; unknown key silently ignored                  |

## Behavior Tests

Tests that verify the module's functional responsibilities from an outside-in perspective.

| Test name                                     | Scenario                                                                                                                                                                    | Expected behavior                                                                                                     |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `test_directory_browser_uses_starred_and_mru` | Star two paths and add three to MRU for the same user; retrieve both via public API                                                                                         | `get_user_starred` returns exactly the two starred paths; `get_user_mru` returns the three MRU paths in recency order |
| `test_preferences_survive_restart`            | Set starred, MRU, and offset state; call `to_dict()` to capture; construct a new `UserPreferences` instance; call `from_dict()` with the captured dict; inspect all getters | New instance has identical starred set, MRU list, and offset values to the original                                   |
| `test_offset_tracking_for_transcript_reading` | Set offset to `512`; then set it to `1024`; then to `2048`                                                                                                                  | Each `get_user_window_offset` call after an update returns the latest value; values monotonically increase            |
