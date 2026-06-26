# O3DE Pilot — AI Coordinator
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Coordinator that routes user requests to specialist AI sessions.

Framework-agnostic — no GUI imports.  The coordinator:

1. Classifies the user's intent (command, build, edit, or general chat).
2. Dispatches to the appropriate specialist session.
3. Receives specialist results as context items (summaries, not raw output).
4. Answers the user from the coordinator session, incorporating results.

The coordinator does NOT execute commands itself — it generates prompts
for specialists and collects their responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .ai_session import AISession, SessionManager, SessionRole, ContextItem


@dataclass
class DispatchResult:
    """Result of routing a user message."""
    session: AISession          # which session handles this
    prompt: str                 # the prompt to send to the specialist
    direct: bool = False        # True if coordinator handles it directly


class Coordinator:
    """Routes user requests to the appropriate specialist session.

    Parameters
    ----------
    manager : SessionManager
        The session manager owning all sessions.
    classify_fn : callable, optional
        Custom classification function.  Receives the user text and returns
        a SessionRole.  If not provided, uses keyword-based heuristics.
    """

    # Keywords that indicate CLI specialist
    _CLI_KEYWORDS = {
        "gem", "project", "engine", "workspace", "register", "manifest",
        "resolve", "refresh", "install", "uninstall", "create", "delete",
        "list", "info", "search", "add", "remove", "audit", "deps",
        "template", "repo", "registry", "update", "config",
    }

    # Keywords that indicate Build specialist
    _BUILD_KEYWORDS = {
        "build", "compile", "cmake", "link", "error", "warning",
        "configure", "target", "makefile", "ninja", "msbuild",
    }

    # Keywords that indicate Editor specialist
    _EDITOR_KEYWORDS = {
        "editor", "entity", "component", "prefab", "level", "scene",
        "viewport", "transform", "spawn", "script canvas", "lua",
        "material", "mesh", "terrain", "sky", "light", "camera",
    }

    def __init__(
        self,
        manager: SessionManager,
        *,
        classify_fn: Callable[[str], SessionRole] | None = None,
    ):
        self._manager = manager
        self._classify_fn = classify_fn or self._classify_heuristic

    @property
    def session(self) -> AISession:
        """The coordinator's own session."""
        return self._manager.coordinator

    def route(self, user_text: str) -> DispatchResult:
        """Classify and route a user message.

        Returns a DispatchResult indicating which session should handle
        the request and what prompt to send.
        """
        role = self._classify_fn(user_text)

        if role == SessionRole.COORDINATOR or role == SessionRole.GENERAL:
            # Coordinator handles it directly
            return DispatchResult(
                session=self.session,
                prompt=user_text,
                direct=True,
            )

        # Find the specialist
        specialist = self._manager.get_sessions_by_role(role)
        if not specialist:
            # No specialist available — coordinator handles it
            return DispatchResult(
                session=self.session,
                prompt=user_text,
                direct=True,
            )

        target = specialist[0]
        return DispatchResult(
            session=target,
            prompt=user_text,
            direct=False,
        )

    def report_specialist_result(
        self,
        specialist: AISession,
        result: str,
        *,
        summary: str = "",
        auto_include: bool = False,
    ) -> ContextItem:
        """Report a specialist's result to the coordinator's context.

        By default, results are excluded from context (the user or
        coordinator can include them if needed).  If *auto_include* is
        True (e.g. for errors or questions), the item is included
        automatically.
        """
        return self.session.add_context_item(
            content=result,
            source=specialist.name,
            summary=summary or _summarize(result),
            included=auto_include,
        )

    def _classify_heuristic(self, text: str) -> SessionRole:
        """Simple keyword-based classification."""
        words = set(text.lower().split())

        cli_score = len(words & self._CLI_KEYWORDS)
        build_score = len(words & self._BUILD_KEYWORDS)
        editor_score = len(words & self._EDITOR_KEYWORDS)

        best = max(cli_score, build_score, editor_score)
        if best == 0:
            return SessionRole.GENERAL

        if cli_score == best:
            return SessionRole.CLI
        if build_score == best:
            return SessionRole.BUILD
        return SessionRole.EDITOR


def _summarize(text: str, max_len: int = 200) -> str:
    """Create a short summary of text for context display."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
