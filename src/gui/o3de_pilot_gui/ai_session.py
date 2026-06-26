# O3DE Pilot — AI Session Model
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Framework-agnostic AI session model.

This module defines the core session, context buffer, and coordinator
abstractions used by the multi-session AI architecture.  It has **no**
GUI imports — only stdlib + o3de_cli dependencies — so the same model
can be reused from CLI, GUI, or a future service layer.

Key concepts
------------
- **ContextItem** — a piece of output (command result, AI response, etc.)
  that *may* be included in the next prompt's context.  Items default to
  *excluded* and the user (or coordinator) explicitly includes them.
- **AISession** — a single conversation thread with its own message
  history, context buffer, and optional specialist role.
- **SessionManager** — owns all sessions, handles persistence, and
  provides the coordinator session.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


# ── Enums ──────────────────────────────────────────────────────────────────

class SessionRole(str, Enum):
    """Role of an AI session."""
    COORDINATOR = "coordinator"
    CLI = "cli"
    BUILD = "build"
    EDITOR = "editor"
    GENERAL = "general"


class ContextItemState(str, Enum):
    """Visibility / inclusion state for a context item."""
    EXCLUDED = "excluded"      # visible in UI, not sent in next prompt
    INCLUDED = "included"      # visible in UI AND sent in next prompt
    DELETED = "deleted"        # removed from UI and context


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class Message:
    """A single message in a session's conversation history."""
    role: str                       # "user", "assistant", "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_provider_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ContextItem:
    """A piece of output that may be included in the coordinator's context."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    source: str = ""                # e.g. "cli", "build", session id
    content: str = ""
    summary: str = ""               # specialist-generated summary
    state: ContextItemState = ContextItemState.EXCLUDED
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_included(self) -> bool:
        return self.state == ContextItemState.INCLUDED

    @property
    def is_visible(self) -> bool:
        return self.state != ContextItemState.DELETED

    def include(self) -> None:
        if self.state != ContextItemState.DELETED:
            self.state = ContextItemState.INCLUDED

    def exclude(self) -> None:
        if self.state != ContextItemState.DELETED:
            self.state = ContextItemState.EXCLUDED

    def delete(self) -> None:
        self.state = ContextItemState.DELETED


# ── AISession ──────────────────────────────────────────────────────────────

class AISession:
    """A single AI conversation session with its own history and context.

    Parameters
    ----------
    session_id : str, optional
        Unique identifier. Auto-generated if not provided.
    name : str
        Display name (e.g. "Coordinator", "CLI", "Build").
    role : SessionRole
        The session's specialist role.
    system_prompt : str
        Injected as the first context message for every provider call.
    max_history : int
        Maximum messages to retain before trimming oldest.
    """

    def __init__(
        self,
        *,
        session_id: str | None = None,
        name: str = "Session",
        role: SessionRole = SessionRole.GENERAL,
        system_prompt: str = "",
        max_history: int = 40,
    ):
        self.id = session_id or uuid.uuid4().hex[:12]
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.messages: list[Message] = []
        self.context_items: list[ContextItem] = []
        self.created_at: float = time.time()
        self.updated_at: float = self.created_at

    # ── Message management ─────────────────────────────────────────

    def add_user_message(self, content: str) -> Message:
        msg = Message(role="user", content=content)
        self.messages.append(msg)
        self._trim()
        self._touch()
        return msg

    def add_assistant_message(self, content: str) -> Message:
        msg = Message(role="assistant", content=content)
        self.messages.append(msg)
        self._trim()
        self._touch()
        return msg

    def get_context_messages(self) -> list[dict[str, str]]:
        """Build the message list for a provider call.

        Returns system prompt + included context items + conversation history.
        """
        out: list[dict[str, str]] = []
        if self.system_prompt:
            out.append({"role": "system", "content": self.system_prompt})

        # Inject included context items as a system-context block
        included = [ci for ci in self.context_items if ci.is_included]
        if included:
            ctx_text = "\n---\n".join(
                f"[{ci.source}] {ci.summary or ci.content}"
                for ci in included
            )
            out.append({
                "role": "system",
                "content": f"Recent context:\n{ctx_text}",
            })

        for msg in self.messages:
            out.append(msg.to_provider_dict())
        return out

    # ── Context buffer ─────────────────────────────────────────────

    def add_context_item(
        self,
        content: str,
        *,
        source: str = "",
        summary: str = "",
        included: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ContextItem:
        """Add a context item (excluded by default)."""
        item = ContextItem(
            source=source,
            content=content,
            summary=summary,
            state=(ContextItemState.INCLUDED if included
                   else ContextItemState.EXCLUDED),
            metadata=metadata or {},
        )
        self.context_items.append(item)
        self._touch()
        return item

    def get_visible_context_items(self) -> list[ContextItem]:
        return [ci for ci in self.context_items if ci.is_visible]

    def clear_context_items(self) -> None:
        self.context_items.clear()
        self._touch()

    # ── Reset / lifecycle ──────────────────────────────────────────

    def reset(self) -> None:
        """Clear all messages and context items."""
        self.messages.clear()
        self.context_items.clear()
        self._touch()

    def _trim(self) -> None:
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]

    def _touch(self) -> None:
        self.updated_at = time.time()

    # ── Serialization ──────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role.value,
            "system_prompt": self.system_prompt,
            "max_history": self.max_history,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "metadata": m.metadata,
                }
                for m in self.messages
            ],
            "context_items": [
                {
                    "id": ci.id,
                    "source": ci.source,
                    "content": ci.content,
                    "summary": ci.summary,
                    "state": ci.state.value,
                    "timestamp": ci.timestamp,
                    "metadata": ci.metadata,
                }
                for ci in self.context_items
                if ci.is_visible
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AISession:
        session = cls(
            session_id=data["id"],
            name=data["name"],
            role=SessionRole(data.get("role", "general")),
            system_prompt=data.get("system_prompt", ""),
            max_history=data.get("max_history", 40),
        )
        session.created_at = data.get("created_at", time.time())
        session.updated_at = data.get("updated_at", session.created_at)
        for m in data.get("messages", []):
            session.messages.append(Message(
                role=m["role"],
                content=m["content"],
                timestamp=m.get("timestamp", 0),
                metadata=m.get("metadata", {}),
            ))
        for ci in data.get("context_items", []):
            session.context_items.append(ContextItem(
                id=ci["id"],
                source=ci.get("source", ""),
                content=ci.get("content", ""),
                summary=ci.get("summary", ""),
                state=ContextItemState(ci.get("state", "excluded")),
                timestamp=ci.get("timestamp", 0),
                metadata=ci.get("metadata", {}),
            ))
        return session


# ── SessionManager ─────────────────────────────────────────────────────────

class SessionManager:
    """Owns all AI sessions and handles persistence.

    Parameters
    ----------
    persist_dir : Path, optional
        Directory for session JSON files.  ``None`` disables persistence.
    """

    def __init__(self, *, persist_dir: Path | None = None):
        self._sessions: dict[str, AISession] = {}
        self._persist_dir = persist_dir
        self._coordinator_id: str | None = None

        if persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)

    # ── Coordinator ────────────────────────────────────────────────

    @property
    def coordinator(self) -> AISession:
        """Get or create the coordinator session."""
        if self._coordinator_id and self._coordinator_id in self._sessions:
            return self._sessions[self._coordinator_id]
        return self._create_coordinator()

    def _create_coordinator(self) -> AISession:
        session = AISession(
            name="Coordinator",
            role=SessionRole.COORDINATOR,
            system_prompt=(
                "You are the O3DE Pilot coordinator AI.  You help the user "
                "manage O3DE projects, gems, engines, and workspaces.  When a "
                "request maps to a specific domain (CLI commands, building, "
                "editing), delegate to the appropriate specialist session and "
                "report the result.  For general questions, answer directly."
            ),
        )
        self._sessions[session.id] = session
        self._coordinator_id = session.id
        return session

    # ── Session CRUD ───────────────────────────────────────────────

    def create_session(
        self,
        name: str,
        role: SessionRole = SessionRole.GENERAL,
        system_prompt: str = "",
    ) -> AISession:
        session = AISession(
            name=name, role=role, system_prompt=system_prompt,
        )
        self._sessions[session.id] = session
        self._save_session(session)
        return session

    def get_session(self, session_id: str) -> AISession | None:
        return self._sessions.get(session_id)

    def get_sessions_by_role(self, role: SessionRole) -> list[AISession]:
        return [s for s in self._sessions.values() if s.role == role]

    def list_sessions(self) -> list[AISession]:
        return list(self._sessions.values())

    def remove_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        if self._persist_dir:
            path = self._persist_dir / f"{session_id}.json"
            path.unlink(missing_ok=True)

    # ── Reset ──────────────────────────────────────────────────────

    def reset_coordinator(self) -> AISession:
        """Reset only the coordinator (specialists keep context)."""
        if self._coordinator_id:
            self.remove_session(self._coordinator_id)
        return self._create_coordinator()

    def reset_all(self) -> AISession:
        """Reset coordinator and all specialist sessions."""
        ids = list(self._sessions.keys())
        for sid in ids:
            self.remove_session(sid)
        return self._create_coordinator()

    def reset_session(self, session_id: str) -> None:
        """Reset a single session's history and context."""
        session = self._sessions.get(session_id)
        if session:
            session.reset()
            self._save_session(session)

    # ── Persistence ────────────────────────────────────────────────

    def _save_session(self, session: AISession) -> None:
        if not self._persist_dir:
            return
        path = self._persist_dir / f"{session.id}.json"
        path.write_text(json.dumps(session.to_dict(), indent=2))

    def save_all(self) -> None:
        for session in self._sessions.values():
            self._save_session(session)

    def load_all(self) -> None:
        """Load all sessions from the persist directory."""
        if not self._persist_dir or not self._persist_dir.is_dir():
            return
        for path in self._persist_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                session = AISession.from_dict(data)
                self._sessions[session.id] = session
                if session.role == SessionRole.COORDINATOR:
                    self._coordinator_id = session.id
            except Exception:
                continue

    # ── Specialist creation helpers ────────────────────────────────

    def ensure_specialist(
        self,
        role: SessionRole,
        name: str,
        system_prompt: str = "",
    ) -> AISession:
        """Get existing specialist for *role*, or create one."""
        existing = self.get_sessions_by_role(role)
        if existing:
            return existing[0]
        return self.create_session(name, role=role, system_prompt=system_prompt)

    def setup_default_specialists(self) -> None:
        """Create the standard set of specialist sessions."""
        self.ensure_specialist(
            SessionRole.CLI,
            "CLI",
            system_prompt=(
                "You are the O3DE CLI specialist.  You handle o3de-pilot "
                "CLI commands: gem/project/engine/workspace management, "
                "registry operations, and manifest resolution.  Execute "
                "commands and report concise results."
            ),
        )
        self.ensure_specialist(
            SessionRole.BUILD,
            "Build",
            system_prompt=(
                "You are the O3DE Build specialist.  You handle CMake "
                "configuration, project compilation, build errors, and "
                "dependency resolution for O3DE projects."
            ),
        )
        self.ensure_specialist(
            SessionRole.EDITOR,
            "Editor",
            system_prompt=(
                "You are the O3DE Editor specialist.  You help with "
                "scene editing, entity/component manipulation, prefab "
                "management, and game world construction in the O3DE Editor."
            ),
        )
