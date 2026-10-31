# O3DE Pilot - AI session history tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Conversation history reaches the provider: request building, native
multi-turn ``chat()`` per provider, and the AI panel end to end."""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest
from o3de_pilot_gui.ai_session import AISession, SessionRole

# ── AISession.build_request ─────────────────────────────────────────

class TestBuildRequest:
    def test_system_combines_prompt_included_context_and_instructions(self):
        s = AISession(system_prompt="You are the CLI specialist.")
        s.add_context_item("full build log", source="Build", summary="build failed", included=True)
        s.add_context_item("ignored output", source="CLI", included=False)
        system, _ = s.build_request("Reply in JSON.")
        assert system == (
            "You are the CLI specialist.\n\n"
            "Recent context:\n[Build] build failed\n\n"
            "Reply in JSON."
        )
        assert "ignored output" not in system

    def test_handoff_carries_coordinator_context(self):
        coordinator = AISession(system_prompt="You are the coordinator.")
        coordinator.add_context_item("error: gem RedPanda failed to link", source="Build",
                                     summary="RedPanda link error", included=True)
        coordinator.add_user_message("I'm working on the gem RedPanda.")
        coordinator.add_assistant_message("Got it.")
        coordinator.add_user_message("Why does the build fail for that gem?")
        build = AISession(system_prompt="You are the Build specialist.")
        build.add_user_message("Why does the build fail for that gem?")

        system, messages = build.build_request("Reply in JSON.", handoff_from=coordinator)
        assert system.startswith("You are the Build specialist.")
        assert system.endswith("Reply in JSON.")
        assert "RedPanda link error" in system
        assert "user: I'm working on the gem RedPanda." in system
        assert messages == [{"role": "user", "content": "Why does the build fail for that gem?"}]

        alone, _ = build.build_request("Reply in JSON.")
        assert "RedPanda" not in alone       # no handoff, no coordinator context

    def test_history_in_order(self):
        s = AISession()
        s.add_user_message("My gem is RedPanda.")
        s.add_assistant_message("Noted.")
        s.add_user_message("What is my gem called?")
        _, messages = s.build_request()
        assert messages == [
            {"role": "user", "content": "My gem is RedPanda."},
            {"role": "assistant", "content": "Noted."},
            {"role": "user", "content": "What is my gem called?"},
        ]

    def test_starts_with_user_after_trim(self):
        s = AISession(max_history=2)
        s.add_user_message("one")
        s.add_assistant_message("two")
        s.add_user_message("three")  # trims "one", leaving an assistant turn first
        _, messages = s.build_request()
        assert messages == [{"role": "user", "content": "three"}]

    def test_consecutive_same_role_merged(self):
        s = AISession()
        s.add_user_message("first try")  # its request failed: no reply recorded
        s.add_user_message("second try")
        _, messages = s.build_request()
        assert messages == [{"role": "user", "content": "first try\n\nsecond try"}]

    def test_system_role_messages_skipped(self):
        s = AISession()
        s.messages.append(type(s.add_user_message("x"))(role="system", content="old"))
        _, messages = s.build_request()
        assert all(m["role"] != "system" for m in messages)


class TestResponseInstructions:
    def test_lists_commands_and_json_contract(self):
        from o3de_pilot_gui.ai.command_router import get_ai_response_instructions
        text = get_ai_response_instructions()
        assert "gem info" in text
        assert '"command": "chat"' in text
        assert "earlier conversation" in text

    def test_classification_prompt_unchanged_shape(self):
        from o3de_pilot_gui.ai.command_router import get_ai_classification_prompt
        text = get_ai_classification_prompt("list my gems")
        assert '"list my gems"' in text and "gem info" in text


# ── Native multi-turn chat per provider ─────────────────────────────

CONVERSATION = [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hello"},
    {"role": "user", "content": "again"},
]


def _http_response(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.raise_for_status = MagicMock()
    return r


class TestProviderChat:
    def test_openai_compatible(self):
        from o3de_pilot_gui.ai.provider import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://api.test/v1", "key", "m1")
        with patch("httpx.post", return_value=_http_response(
                {"choices": [{"message": {"content": "ok"}}]})) as post:
            assert p.chat(CONVERSATION, system="SYS") == "ok"
        body = post.call_args.kwargs["json"]
        assert body["messages"][0] == {"role": "system", "content": "SYS"}
        assert body["messages"][1:] == CONVERSATION
        assert post.call_args.args[0] == "https://api.test/v1/chat/completions"

    def test_openai(self):
        from o3de_pilot_gui.ai.provider import OpenAIProvider
        p = OpenAIProvider(api_key="k", model="gpt-4o")
        p._client = MagicMock()
        p._client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="ok"))]
        assert p.chat(CONVERSATION, system="SYS") == "ok"
        sent = p._client.chat.completions.create.call_args.kwargs["messages"]
        assert sent[0] == {"role": "system", "content": "SYS"} and sent[1:] == CONVERSATION

    def test_openai_complete_keeps_default_system_prompt(self):
        from o3de_pilot_gui.ai.provider import OpenAIProvider
        p = OpenAIProvider(api_key="k", model="gpt-4o")
        p._client = MagicMock()
        p._client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="ok"))]
        p.complete("q")
        sent = p._client.chat.completions.create.call_args.kwargs["messages"]
        assert "O3DE" in sent[0]["content"] and sent[1] == {"role": "user", "content": "q"}

    def test_gemini_maps_assistant_to_model(self):
        from o3de_pilot_gui.ai.provider import GeminiProvider
        p = GeminiProvider(api_key="k", model="gemini-2.5-flash")
        with patch("httpx.post", return_value=_http_response(
                {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})) as post:
            assert p.chat(CONVERSATION, system="SYS") == "ok"
        body = post.call_args.kwargs["json"]
        assert body["system_instruction"] == {"parts": [{"text": "SYS"}]}
        assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
        assert body["contents"][1]["parts"] == [{"text": "hello"}]

    def test_ollama_uses_chat_endpoint(self):
        from o3de_pilot_gui.ai.provider import OllamaProvider
        p = OllamaProvider(url="http://localhost:11434", model="llama3.2:3b")
        p._model_checked = True
        with patch("httpx.post", return_value=_http_response(
                {"message": {"role": "assistant", "content": "ok"}})) as post:
            assert p.chat(CONVERSATION, system="SYS") == "ok"
        assert post.call_args.args[0] == "http://localhost:11434/api/chat"
        body = post.call_args.kwargs["json"]
        assert body["messages"][0] == {"role": "system", "content": "SYS"}
        assert body["messages"][1:] == CONVERSATION
        assert body["stream"] is False

    def test_base_fallback_keeps_system(self):
        from o3de_pilot_gui.ai.provider import AIProvider

        class Echo(AIProvider):
            def complete(self, prompt):
                return prompt

            async def complete_async(self, prompt):
                return prompt

            async def stream(self, prompt):
                yield prompt

        out = Echo().chat(CONVERSATION, system="SYS")
        assert out.startswith("Instructions:\nSYS")
        assert "Assistant: hello" in out and out.endswith("User: again")


# ── AI panel end to end ─────────────────────────────────────────────

class FakeProvider:
    """Records each request; replies in the panel's JSON contract."""

    def __init__(self, replies=None, gate=None):
        self.calls = []
        self._replies = list(replies or [])
        self._gate = gate

    def chat(self, messages, system=None):
        self.calls.append({"messages": [dict(m) for m in messages], "system": system})
        if self._gate is not None:
            self._gate.wait(5)
        reply = self._replies.pop(0) if self._replies else "ok"
        if isinstance(reply, dict):
            return json.dumps(reply)
        return json.dumps({"command": "chat", "response": reply})


@pytest.fixture
def panel(qtbot, tmp_path):
    from o3de_pilot_gui.ai_panel import AIPanel
    # Plain function, not a MagicMock: PySide6 crashes on MagicMock attributes of QObject classes.
    with patch.object(AIPanel, "_get_persist_dir", lambda self: tmp_path):
        p = AIPanel()
    qtbot.addWidget(p)
    yield p
    p.save_sessions()


def _submit(qtbot, panel, provider, text, session_id=None):
    sid = session_id or panel._coordinator.session.id
    with patch("o3de_pilot_gui.ai.provider.get_ai_provider", return_value=provider):
        panel._on_prompt_submitted(sid, text)
        qtbot.waitUntil(lambda: not panel._busy, timeout=5000)


class TestAIPanelHistory:
    def test_follow_up_sees_earlier_turns(self, qtbot, panel):
        from o3de_pilot_gui.ai.command_router import match_command
        first, second = "Remember the number 42.", "Which number did I ask you to remember?"
        assert match_command(first) is None and match_command(second) is None

        provider = FakeProvider(replies=["Noted: 42.", "You asked me to remember 42."])
        _submit(qtbot, panel, provider, first)
        _submit(qtbot, panel, provider, second)

        assert provider.calls[1]["messages"] == [
            {"role": "user", "content": first},
            {"role": "assistant", "content": "Noted: 42."},
            {"role": "user", "content": second},
        ]
        system = provider.calls[1]["system"]
        assert "coordinator" in system.lower()          # the session's own system prompt
        assert '"command": "chat"' in system            # the response-format instructions
        coordinator = panel._coordinator.session
        assert [m.content for m in coordinator.messages][-1] == "You asked me to remember 42."

    def test_history_survives_restart(self, qtbot, tmp_path):
        from o3de_pilot_gui.ai_panel import AIPanel
        with patch.object(AIPanel, "_get_persist_dir", lambda self: tmp_path):
            p1 = AIPanel()
        qtbot.addWidget(p1)
        _submit(qtbot, p1, FakeProvider(replies=["Noted."]), "Remember the number 7.")

        with patch.object(AIPanel, "_get_persist_dir", lambda self: tmp_path):
            p2 = AIPanel()
        qtbot.addWidget(p2)
        provider = FakeProvider()
        _submit(qtbot, p2, provider, "Which number?")
        assert [m["content"] for m in provider.calls[0]["messages"]] == [
            "Remember the number 7.", "Noted.", "Which number?"]

    def test_specialist_gets_the_message_and_coordinator_shows_the_answer(self, qtbot, panel):
        from o3de_pilot_gui.ai.command_router import match_command
        text = "cmake configure fails on this target"
        assert match_command(text) is None
        dispatch = panel._coordinator.route(text)
        assert dispatch.session.role == SessionRole.BUILD

        provider = FakeProvider(replies=["Delete the CMake cache and reconfigure."])
        _submit(qtbot, panel, provider, text)

        build = dispatch.session
        coordinator = panel._coordinator.session
        assert provider.calls[0]["messages"] == [{"role": "user", "content": text}]
        assert "Build specialist" in provider.calls[0]["system"]
        assert [(m.role, m.content) for m in build.messages] == [
            ("user", text), ("assistant", "Delete the CMake cache and reconfigure.")]
        assert coordinator.messages[-1].content == "Delete the CMake cache and reconfigure."
        # No greyed-out duplicate of the answer in the coordinator's context items.
        assert coordinator.get_visible_context_items() == []

    def test_second_message_while_busy_is_refused(self, qtbot, panel):
        gate = threading.Event()
        provider = FakeProvider(replies=["first answer"], gate=gate)
        sid = panel._coordinator.session.id
        with patch("o3de_pilot_gui.ai.provider.get_ai_provider", return_value=provider):
            panel._on_prompt_submitted(sid, "Remember the number 1.")
            qtbot.waitUntil(lambda: len(provider.calls) == 1, timeout=5000)
            panel._on_prompt_submitted(sid, "And the number 2.")
            gate.set()
            qtbot.waitUntil(lambda: not panel._busy, timeout=5000)

        assert len(provider.calls) == 1
        contents = [m.content for m in panel._coordinator.session.messages]
        assert "And the number 2." not in contents
        assert contents[-1] == "first answer"

    def test_ai_proposed_command_is_recorded(self, qtbot, panel):
        provider = FakeProvider(replies=[{"command": "gem info", "args": {"name": "Atom"},
                                          "description": "Show the Atom gem"}])
        emitted = []
        panel.execute_command.connect(lambda cmd, args: emitted.append((cmd, args)))
        _submit(qtbot, panel, provider, "Tell me about the Atom gem, as a command please.")

        assert emitted == [("gem info", {"name": "Atom"})]
        last = panel._coordinator.session.messages[-1]
        assert last.role == "assistant" and "o3de gem info Atom" in last.content
        assert panel._status.text().startswith("Coordinator")  # not stuck on "Thinking..."

    def test_provider_error_is_shown_and_clears_busy(self, qtbot, panel):
        class Failing:
            def chat(self, messages, system=None):
                raise RuntimeError("Claude Code is not signed in.")

        _submit(qtbot, panel, Failing(), "Remember the number 3.")
        assert panel._busy is False
        # The unanswered user turn stays; the next request merges it rather than failing.
        _, messages = panel._coordinator.session.build_request()
        assert messages == [{"role": "user", "content": "Remember the number 3."}]

    def test_context_toggle_is_saved_and_sent(self, qtbot, panel, tmp_path):
        coordinator = panel._coordinator.session
        item = coordinator.add_context_item("Build failed: missing Atom", source="Build",
                                            summary="build failed: missing Atom")
        chat = panel._chat_widgets[coordinator.id]
        chat.add_context_item(item)
        from o3de_pilot_gui.session_chat_widget import ContextItemWidget
        widget = chat.findChildren(ContextItemWidget)[-1]
        widget._toggle_state()  # include it

        saved = json.loads((tmp_path / f"{coordinator.id}.json").read_text())
        assert saved["context_items"][0]["state"] == "included"

        provider = FakeProvider()
        _submit(qtbot, panel, provider, "Why did it fail?")
        assert "build failed: missing Atom" in provider.calls[0]["system"]
