"""Transcript discovery for hookless providers.

Discovers and registers transcripts for providers without hook support
(Codex, Gemini). Also handles provider auto-detection from pane process
and shell ↔ agent transitions.

Key components:
  - discover_and_register_transcript: main discovery function called per topic
  - _detect_and_apply_provider: provider auto-detection from running process
  - _find_and_register_transcript: transcript search for hookless providers
"""

import asyncio
from typing import TYPE_CHECKING

import structlog

from ..config import config
from ..providers import (
    detect_provider_from_pane,
    detect_provider_from_runtime,
    detect_provider_from_transcript_path,
    get_provider_for_window,
    should_probe_pane_title_for_provider_detection,
)
from ..session import session_manager
from ..session_map import session_map_sync
from ..tmux_manager import tmux_manager
from ..window_resolver import is_foreign_window
from .polling_strategies import is_shell_prompt

if TYPE_CHECKING:
    from telegram import Bot

    from ..providers.base import AgentProvider
    from ..session import WindowState
    from ..tmux_manager import TmuxWindow

logger = structlog.get_logger()


async def _detect_and_apply_provider(
    window_id: str,
    state: "WindowState",
    w: "TmuxWindow",
    *,
    bot: "Bot | None" = None,
    chat_id: int = 0,
    thread_id: int = 0,
) -> None:
    """Detect provider from pane process and apply transitions."""
    detected = await detect_provider_from_pane(
        w.pane_current_command, pane_tty=w.pane_tty, window_id=window_id
    )
    try:
        with open("/tmp/1.log", "a") as _f:
            _f.write(
                f"[detect_provider] window_id={window_id} "
                f"pane_cmd={w.pane_current_command!r} "
                f"detected={detected!r} current={state.provider_name!r}\n"
            )
    except Exception:
        pass

    if not detected and should_probe_pane_title_for_provider_detection(
        w.pane_current_command
    ):
        pane_title = await tmux_manager.get_pane_title(window_id)
        detected = detect_provider_from_runtime(
            w.pane_current_command,
            pane_title=pane_title,
        )
        try:
            with open("/tmp/1.log", "a") as _f:
                _f.write(
                    f"[detect_provider] pane_title probe: "
                    f"pane_title={pane_title!r} detected={detected!r}\n"
                )
        except Exception:
            pass

    if detected and detected != state.provider_name:
        old_provider = state.provider_name
        session_manager.set_window_provider(window_id, detected, cwd=w.cwd or None)
        try:
            with open("/tmp/1.log", "a") as _f:
                _f.write(
                    f"[detect_provider] SWITCHING provider: "
                    f"{old_provider!r} → {detected!r} for window_id={window_id}\n"
                )
        except Exception:
            pass
        from ..providers import get_provider_for_window

        new_caps = get_provider_for_window(window_id, detected)
        old_caps = (
            get_provider_for_window(window_id, old_provider) if old_provider else None
        )
        if new_caps and new_caps.capabilities.chat_first_command_path:
            state.transcript_path = ""
            from .shell_prompt_orchestrator import ensure_setup

            await ensure_setup(
                window_id,
                "provider_switch",
                bot=bot,
                chat_id=chat_id,
                thread_id=thread_id,
            )
        elif old_caps and old_caps.capabilities.chat_first_command_path:
            from .shell_capture import clear_shell_monitor_state
            from .shell_prompt_orchestrator import clear_state as clear_orchestrator

            clear_shell_monitor_state(window_id)
            clear_orchestrator(window_id)
    elif not detected and state.transcript_path:
        inferred = detect_provider_from_transcript_path(state.transcript_path)
        if inferred and inferred != state.provider_name:
            session_manager.set_window_provider(window_id, inferred, cwd=w.cwd or None)
            try:
                with open("/tmp/1.log", "a") as _f:
                    _f.write(
                        f"[detect_provider] inferred from transcript_path: "
                        f"{inferred!r} for window_id={window_id}\n"
                    )
            except Exception:
                pass


def _resolve_providers_to_try(
    window_id: str, state: "WindowState", w: "TmuxWindow | None"
) -> list[tuple[str, "AgentProvider"]] | None:
    """Determine which providers to probe for transcripts.

    Returns a list of (name, provider) pairs, or ``None`` to signal the
    caller should set up a shell provider.
    """
    from ..providers import registry

    if state.provider_name:
        provider = get_provider_for_window(window_id, state.provider_name)
        if not provider.capabilities.supports_mailbox_delivery:
            return []
        return [(provider.capabilities.name, provider)]

    if w and is_shell_prompt(w.pane_current_command):
        return None  # signals caller to set up shell

    return [
        (name, registry.get(name))
        for name in registry.provider_names()
        if not registry.get(name).capabilities.supports_hook and name != "shell"
    ]


async def _find_and_register_transcript(
    window_id: str,
    state: "WindowState",
    providers_to_try: list[tuple[str, "AgentProvider"]],
    pane_alive: bool,
) -> None:
    """Search for transcripts among candidate providers and register if found."""
    window_key = (
        window_id
        if is_foreign_window(window_id)
        else f"{config.tmux_session_name}:{window_id}"
    )

    try:
        with open("/tmp/1.log", "a") as _f:
            _f.write(
                f"[find_transcript] window_id={window_id} window_key={window_key} "
                f"pane_alive={pane_alive} "
                f"providers={[n for n, _ in providers_to_try]} "
                f"state.cwd={state.cwd!r} state.transcript_path={state.transcript_path!r}\n"
            )
    except Exception:
        pass

    for provider_name, provider in providers_to_try:
        max_age = 0 if pane_alive else None
        try:
            with open("/tmp/1.log", "a") as _f:
                _f.write(
                    f"[find_transcript] calling discover_transcript: "
                    f"provider={provider_name!r} cwd={state.cwd!r} max_age={max_age!r}\n"
                )
        except Exception:
            pass
        event = await asyncio.to_thread(
            provider.discover_transcript,
            state.cwd,
            window_key,
            max_age=max_age,
        )
        try:
            with open("/tmp/1.log", "a") as _f:
                _f.write(
                    f"[find_transcript] discover_transcript result: {event!r}\n"
                )
        except Exception:
            pass
        if not event:
            continue

        if (
            state.session_id == event.session_id
            and state.transcript_path == event.transcript_path
            and state.provider_name == provider_name
        ):
            try:
                with open("/tmp/1.log", "a") as _f:
                    _f.write(
                        f"[find_transcript] already registered (no change): "
                        f"session_id={event.session_id!r}\n"
                    )
            except Exception:
                pass
            return

        try:
            with open("/tmp/1.log", "a") as _f:
                _f.write(
                    f"[find_transcript] REGISTERING new session: "
                    f"session_id={event.session_id!r} "
                    f"transcript={event.transcript_path!r} "
                    f"provider={provider_name!r}\n"
                )
        except Exception:
            pass
        session_map_sync.register_hookless_session(
            window_id=window_id,
            session_id=event.session_id,
            cwd=event.cwd,
            transcript_path=event.transcript_path,
            provider_name=provider_name,
        )
        await asyncio.to_thread(
            session_map_sync.write_hookless_session_map,
            window_id=window_id,
            session_id=event.session_id,
            cwd=event.cwd,
            transcript_path=event.transcript_path,
            provider_name=provider_name,
        )
        return


async def discover_and_register_transcript(
    window_id: str,
    *,
    _window: "TmuxWindow | None" = None,
    bot: "Bot | None" = None,
    user_id: int = 0,
    thread_id: int = 0,
) -> None:
    """Discover and register transcript for hookless providers (Codex, Gemini).

    Also handles provider auto-detection from pane process name
    and shell ↔ agent transitions with prompt marker setup.
    """
    from ..thread_router import thread_router

    # Fetch the window first so we can bootstrap state if needed.
    w = _window or await tmux_manager.find_window_by_id(window_id)

    state = session_manager.window_states.get(window_id)
    if not state:
        # No state yet — seed an empty record from the live window's cwd so
        # that hookless discovery (Gemini, Codex) can run for the first time.
        # Without this, discover_transcript is never reached and the session
        # stays undiscovered forever (chicken-and-egg deadlock).
        if not w or not w.cwd:
            try:
                with open("/tmp/1.log", "a") as _f:
                    _f.write(
                        f"[discover] SKIP window_id={window_id}: "
                        f"no state and no live window/cwd (w={w!r})\n"
                    )
            except Exception:
                pass
            return
        try:
            with open("/tmp/1.log", "a") as _f:
                _f.write(
                    f"[discover] BOOTSTRAP state for window_id={window_id} "
                    f"cwd={w.cwd!r}\n"
                )
        except Exception:
            pass
        session_manager.set_window_provider(window_id, "", cwd=w.cwd)
        state = session_manager.window_states.get(window_id)
        if not state:
            return

    try:
        _pane_cmd = w.pane_current_command if w else None
        with open("/tmp/1.log", "a") as _f:
            _f.write(
                f"[discover] window_id={window_id} "
                f"provider={state.provider_name!r} "
                f"cwd={state.cwd!r} "
                f"transcript_path={state.transcript_path!r} "
                f"session_id={state.session_id!r} "
                f"pane_cmd={_pane_cmd!r}\n"
            )
    except Exception:
        pass

    chat_id = thread_router.resolve_chat_id(user_id, thread_id) if user_id else 0

    if w and w.pane_current_command:
        await _detect_and_apply_provider(
            window_id, state, w, bot=bot, chat_id=chat_id, thread_id=thread_id
        )

    if state.provider_name:
        provider = get_provider_for_window(window_id, state.provider_name)
        if provider.capabilities.supports_hook:
            try:
                with open("/tmp/1.log", "a") as _f:
                    _f.write(
                        f"[discover] SKIP window_id={window_id}: "
                        f"provider={state.provider_name!r} uses hooks\n"
                    )
            except Exception:
                pass
            return

    if not state.cwd:
        if not w or not w.cwd:
            try:
                with open("/tmp/1.log", "a") as _f:
                    _f.write(
                        f"[discover] SKIP window_id={window_id}: no cwd in state or window\n"
                    )
            except Exception:
                pass
            return
        session_manager.set_window_provider(
            window_id, state.provider_name or "", cwd=w.cwd
        )

    providers_to_try = _resolve_providers_to_try(window_id, state, w)
    try:
        with open("/tmp/1.log", "a") as _f:
            _f.write(
                f"[discover] providers_to_try={[n for n, _ in providers_to_try] if providers_to_try is not None else 'None (→shell)'}\n"
            )
    except Exception:
        pass
    if providers_to_try is None:
        session_manager.set_window_provider(window_id, "shell")
        state.transcript_path = ""
        from .shell_prompt_orchestrator import ensure_setup

        await ensure_setup(
            window_id, "provider_switch", bot=bot, chat_id=chat_id, thread_id=thread_id
        )
        return
    if not providers_to_try:
        try:
            with open("/tmp/1.log", "a") as _f:
                _f.write(
                    f"[discover] SKIP window_id={window_id}: "
                    f"providers_to_try is empty (provider={state.provider_name!r} "
                    f"supports_mailbox_delivery=False?)\n"
                )
        except Exception:
            pass
        return

    pane_alive = w is not None and not is_shell_prompt(w.pane_current_command)
    try:
        with open("/tmp/1.log", "a") as _f:
            _f.write(
                f"[discover] calling _find_and_register_transcript: "
                f"window_id={window_id} pane_alive={pane_alive}\n"
            )
    except Exception:
        pass
    await _find_and_register_transcript(window_id, state, providers_to_try, pane_alive)
