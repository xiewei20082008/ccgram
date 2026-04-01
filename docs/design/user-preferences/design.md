# User Preferences

## Functional Responsibilities

- Manage per-user UI preferences extracted from SessionManager:
  - Starred directories (favorites for directory browser)
  - Most Recently Used (MRU) directories
  - Per-user per-window read offsets (byte positions for transcript reading)
- Serialize/deserialize to state.json alongside SessionManager (shared persistence)
- Provide clean public API that only 2 consumers need (directory_browser, directory_callbacks)

## Encapsulated Knowledge

- `_user_starred: dict[int, set[str]]` — per-user set of starred directory paths
- `_user_mru: dict[int, list[str]]` — per-user ordered MRU list with max length
- `_user_offsets: dict[int, dict[str, int]]` — per-user per-window byte offset
- MRU eviction algorithm (max 10 entries, push to front on use)
- Star toggle behavior (add/remove idempotent)
- Offset pruning logic (remove offsets for windows no longer in window_states)

## Subdomain Classification

Generic — stable getter/setter pattern; rarely changes independently. The MRU/star/offset logic is well-defined and unlikely to evolve.

## Integration Contracts

- Public API:
  ```python
  class UserPreferences:
      def get_user_starred(self, user_id: int) -> set[str]: ...
      def toggle_user_star(self, user_id: int, path: str) -> bool: ...
      def get_user_mru(self, user_id: int) -> list[str]: ...
      def update_user_mru(self, user_id: int, path: str) -> None: ...
      def get_user_window_offset(self, user_id: int, window_id: str) -> int: ...
      def update_user_window_offset(self, user_id: int, window_id: str, offset: int) -> None: ...
      def to_dict(self) -> dict: ...
      def from_dict(self, data: dict) -> None: ...
  ```
- ↔ Session State (bidirectional coordination): Functional — shared state.json persistence
  - Session State calls `user_preferences.to_dict()` on save, `user_preferences.from_dict(data)` on load
  - UserPreferences calls `session_state.schedule_save()` after mutations (same pattern as ThreadRouter)
- ← Directory Browser (depended on by): Contract — `get_user_starred()`, `toggle_user_star()`, `get_user_mru()`, `update_user_mru()`
- ← Directory Callbacks (depended on by): Contract — same methods as directory_browser
- ← History handler (depended on by): Contract — `get_user_window_offset()`, `update_user_window_offset()`

## Change Vectors

- Adding a new preference type (e.g., theme, language) — add getter/setter; update serialization
- Changing MRU max length — only MRU logic changes
- Changing persistence format — only to_dict/from_dict change
- Adding per-user settings sync across instances — only persistence layer changes
