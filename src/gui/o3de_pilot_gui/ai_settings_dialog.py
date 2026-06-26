# O3DE Pilot GUI - AI Settings Dialog
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Dialog for configuring the AI provider, API key, and model.

Supported providers (11 total):
    - **Ollama** (local, free) — default if installed
    - **Google Gemini** (free tier available via API key)
    - **Groq** (free tier — ultra-fast inference)
    - **OpenRouter** (multi-provider, free models available)
    - **Mistral AI** (European AI lab)
    - **DeepSeek** (powerful & affordable)
    - **OpenAI** (requires API key)
    - **Anthropic Claude** (requires API key)
    - **xAI Grok** (free credits on signup)
    - **Together AI** (open-source model hosting)
    - **Perplexity** (search-augmented AI)
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QAction
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLineEdit, QPushButton, QLabel,
    QDialogButtonBox, QGroupBox, QWidget, QMessageBox,
)


# ── Provider metadata ──────────────────────────────────────────────

PROVIDERS = [
    {
        "id": "ollama",
        "name": "Ollama (Local)",
        "needs_key": False,
        "default_model": "llama3",
        "models": ["llama3", "llama3.1", "llama3.2", "codellama", "mistral", "gemma2", "phi3", "deepseek-coder"],
        "free_models": ["llama3", "llama3.1", "llama3.2", "codellama", "mistral", "gemma2", "phi3", "deepseek-coder"],  # all local = free
        "help": "Runs locally — install from https://ollama.com",
        "free_key_url": "",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "needs_key": True,
        "default_model": "gemini-2.5-flash",
        "models": [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-3-flash-preview",
            "gemini-2.5-pro",
            "gemini-3-pro-preview",
        ],
        "free_models": ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-3-pro-preview"],
        "help": "All models have a free tier. Get a key at https://aistudio.google.com/apikey",
        "free_key_url": "https://aistudio.google.com/apikey",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "needs_key": True,
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-mini"],
        "free_models": [],  # no free API tier
        "help": "Get an API key at https://platform.openai.com/api-keys",
        "free_key_url": "",
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "needs_key": True,
        "default_model": "claude-sonnet-4-20250514",
        "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-3-5-haiku-20241022"],
        "free_models": [],  # no free API tier
        "help": "Get an API key at https://console.anthropic.com/settings/keys",
        "free_key_url": "",
    },
    {
        "id": "groq",
        "name": "Groq",
        "needs_key": True,
        "default_model": "llama-3.3-70b-versatile",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
        "free_models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],  # all free with rate limits
        "help": "Ultra-fast free inference \u2014 https://console.groq.com",
        "free_key_url": "https://console.groq.com/keys",
    },
    {
        "id": "mistral",
        "name": "Mistral AI",
        "needs_key": True,
        "default_model": "mistral-large-latest",
        "models": ["mistral-large-latest", "mistral-small-latest", "codestral-latest", "open-mistral-nemo"],
        "free_models": [],  # trial credits only, no permanent free tier
        "help": "European AI lab \u2014 https://mistral.ai",
        "free_key_url": "https://console.mistral.ai/api-keys",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "needs_key": True,
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
        "free_models": [],  # very cheap but pay-per-token
        "help": "Powerful & affordable \u2014 https://platform.deepseek.com",
        "free_key_url": "https://platform.deepseek.com/api_keys",
    },
    {
        "id": "xai",
        "name": "xAI (Grok)",
        "needs_key": True,
        "default_model": "grok-2",
        "models": ["grok-2", "grok-2-mini"],
        "free_models": ["grok-2", "grok-2-mini"],  # $25/mo free API credits
        "help": "xAI\u2019s Grok models \u2014 free $25/mo credits \u2014 https://x.ai",
        "free_key_url": "https://console.x.ai",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "needs_key": True,
        "default_model": "auto",
        "models": ["auto", "meta-llama/llama-3.3-70b-instruct", "google/gemini-2.0-flash-exp:free", "mistralai/mistral-small-24b-instruct-2501:free"],
        "free_models": ["google/gemini-2.0-flash-exp:free", "mistralai/mistral-small-24b-instruct-2501:free"],  # :free suffix models
        "help": "Routes to 200+ models, some free \u2014 https://openrouter.ai",
        "free_key_url": "https://openrouter.ai/keys",
    },
    {
        "id": "together",
        "name": "Together AI",
        "needs_key": True,
        "default_model": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "models": ["meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo", "mistralai/Mixtral-8x7B-Instruct-v0.1"],
        "free_models": [],  # trial credits only
        "help": "Open-source model hosting \u2014 https://together.ai",
        "free_key_url": "",
    },
    {
        "id": "perplexity",
        "name": "Perplexity",
        "needs_key": True,
        "default_model": "sonar-pro",
        "models": ["sonar-pro", "sonar", "sonar-reasoning"],
        "free_models": [],  # no free API tier
        "help": "Search-augmented AI \u2014 https://perplexity.ai",
        "free_key_url": "",
    },
]


class AISettingsDialog(QDialog):
    """Dialog for configuring the AI provider and credentials."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("AI Settings")
        self.setMinimumWidth(480)
        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E;
                color: #EEEEEE;
            }
            QLabel { color: #CCCCCC; }
            QGroupBox {
                color: #EEEEEE;
                border: 1px solid #444444;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QComboBox, QLineEdit {
                background-color: #2D2D2D;
                color: #EEEEEE;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 6px 10px;
                min-height: 28px;
            }
            QComboBox:focus, QLineEdit:focus { border-color: #0078D4; }
            QComboBox QAbstractItemView {
                background-color: #2D2D2D;
                color: #EEEEEE;
                selection-background-color: #0078D4;
            }
            QPushButton {
                background-color: #333333;
                color: #EEEEEE;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #444444; }
        """)

        self._connection_verified = False
        self._api_keys: dict[str, str] = {}   # provider_id -> api_key
        self._current_provider_id: str = ""     # tracks which provider is active
        self._setup_ui()
        self._load_current()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # ── Provider group ──────────────────────────────────────────
        provider_group = QGroupBox("AI Provider")
        form = QFormLayout(provider_group)

        self._provider_combo = QComboBox()
        for p in PROVIDERS:
            self._provider_combo.addItem(p["name"], p["id"])
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider:", self._provider_combo)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)  # Allow custom model names
        model_row = QHBoxLayout()
        model_row.addWidget(self._model_combo, stretch=1)

        self._discover_btn = QPushButton("Discover")
        self._discover_btn.setToolTip("Query provider API for available models")
        self._discover_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333; color: #EEEEEE;
                border: 1px solid #555555; border-radius: 4px;
                padding: 6px 12px; font-size: 9pt;
            }
            QPushButton:hover { background-color: #444444; }
        """)
        self._discover_btn.clicked.connect(self._discover_models)
        model_row.addWidget(self._discover_btn)
        form.addRow("Model:", model_row)

        # Thinking effort selector
        self._thinking_combo = QComboBox()
        _thinking_items = [
            ("off", "Off — no reasoning"),
            ("low", "Low — quick reasoning"),
            ("medium", "Medium — balanced"),
            ("high", "High — deep analysis"),
            ("max", "Max — maximum reasoning"),
        ]
        for val, label in _thinking_items:
            self._thinking_combo.addItem(label, val)
        self._thinking_combo.setToolTip(
            "Controls how much the AI 'thinks' before answering.\n"
            "Higher = better answers for complex questions, but slower and costs more."
        )
        form.addRow("Thinking:", self._thinking_combo)

        self._help_label = QLabel("")
        self._help_label.setStyleSheet("color: #888888; font-size: 8pt;")
        self._help_label.setWordWrap(True)
        self._help_label.setOpenExternalLinks(True)
        form.addRow("", self._help_label)

        layout.addWidget(provider_group)

        # ── Credentials group ───────────────────────────────────────
        self._cred_group = QGroupBox("Credentials")
        cred_form = QFormLayout(self._cred_group)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("Paste your API key here")

        # Inline show/hide toggle inside the text field
        self._eye_action = QAction("Show", self._api_key_edit)
        self._eye_action.setToolTip("Show / Hide API key")
        self._api_key_edit.addAction(
            self._eye_action, QLineEdit.ActionPosition.TrailingPosition
        )
        self._eye_action.triggered.connect(self._toggle_key_visibility)

        cred_form.addRow("API Key:", self._api_key_edit)

        # "Get Free API Key" button — opens browser, only visible for free-tier providers
        self._free_key_btn = QPushButton("Get Free API Key")
        self._free_key_btn.setStyleSheet("""
            QPushButton {
                background-color: #1A6B3A;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #22884A; }
        """)
        self._free_key_btn.clicked.connect(self._open_free_key_url)
        self._free_key_btn.hide()
        cred_form.addRow("", self._free_key_btn)

        layout.addWidget(self._cred_group)

        # ── Ollama URL (only for Ollama) ────────────────────────────
        self._ollama_group = QGroupBox("Ollama Settings")
        ollama_form = QFormLayout(self._ollama_group)
        self._ollama_url_edit = QLineEdit("http://localhost:11434")
        ollama_form.addRow("URL:", self._ollama_url_edit)

        # Status indicator
        self._ollama_status = QLabel("")
        self._ollama_status.setWordWrap(True)
        self._ollama_status.setStyleSheet("font-size: 9pt; background: transparent;")
        ollama_form.addRow("Status:", self._ollama_status)

        # Action buttons row
        ollama_btn_row = QHBoxLayout()

        self._ollama_install_btn = QPushButton("Install Ollama")
        self._ollama_install_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4; color: white;
                border: none; border-radius: 4px;
                padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1A8AE8; }
        """)
        self._ollama_install_btn.clicked.connect(self._install_ollama)
        self._ollama_install_btn.hide()
        ollama_btn_row.addWidget(self._ollama_install_btn)

        self._ollama_start_btn = QPushButton("Start Ollama")
        self._ollama_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #1A6B3A; color: white;
                border: none; border-radius: 4px;
                padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #22884A; }
        """)
        self._ollama_start_btn.clicked.connect(self._start_ollama)
        self._ollama_start_btn.hide()
        ollama_btn_row.addWidget(self._ollama_start_btn)

        self._ollama_pull_btn = QPushButton("Pull llama3")
        self._ollama_pull_btn.setStyleSheet("""
            QPushButton {
                background-color: #6B4C1A; color: white;
                border: none; border-radius: 4px;
                padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #88631F; }
        """)
        self._ollama_pull_btn.clicked.connect(self._pull_ollama_model)
        self._ollama_pull_btn.hide()
        ollama_btn_row.addWidget(self._ollama_pull_btn)

        self._ollama_refresh_btn = QPushButton("Refresh")
        self._ollama_refresh_btn.setToolTip("Re-check Ollama status")
        self._ollama_refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333; color: #EEEEEE;
                border: 1px solid #555555; border-radius: 4px;
                padding: 8px 14px; font-size: 9pt;
            }
            QPushButton:hover { background-color: #444444; }
        """)
        self._ollama_refresh_btn.clicked.connect(self._detect_ollama)
        ollama_btn_row.addWidget(self._ollama_refresh_btn)

        ollama_btn_row.addStretch()
        ollama_form.addRow("", ollama_btn_row)

        layout.addWidget(self._ollama_group)

        # ── Test button ─────────────────────────────────────────────
        test_row = QHBoxLayout()
        test_row.addStretch()
        self._test_btn = QPushButton("Test Connection")
        self._test_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1A8AE8; }
        """)
        self._test_btn.clicked.connect(self._test_connection)
        test_row.addWidget(self._test_btn)
        layout.addLayout(test_row)

        # ── Dialog buttons ──────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        # Style the OK button
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1A8AE8; }
        """)
        layout.addWidget(buttons)

        # Trigger initial visibility
        self._on_provider_changed(0)

    # ── Provider switch ─────────────────────────────────────────────

    def _on_provider_changed(self, index: int):
        if index < 0 or index >= len(PROVIDERS):
            return
        p = PROVIDERS[index]
        self._connection_verified = False   # reset until re-tested

        # ── Per-provider API key swap ───────────────────────────────
        # Stash the current key before switching
        if self._current_provider_id:
            cur_key = self._api_key_edit.text().strip()
            if cur_key:
                self._api_keys[self._current_provider_id] = cur_key
            elif self._current_provider_id in self._api_keys:
                # User cleared the field — remove stashed key
                del self._api_keys[self._current_provider_id]
        self._current_provider_id = p["id"]
        # Load the new provider's key (or blank)
        self._api_key_edit.setText(self._api_keys.get(p["id"], ""))

        self._model_combo.clear()
        free_set = set(p.get("free_models", []))
        for m in p["models"]:
            self._model_combo.addItem(m)
            idx = self._model_combo.count() - 1
            if m in free_set:
                self._model_combo.setItemData(
                    idx, QColor("#4EC94E"), Qt.ItemDataRole.ForegroundRole
                )
        self._model_combo.setCurrentText(p["default_model"])
        self._help_label.setText(p["help"])
        self._cred_group.setVisible(p["needs_key"])
        self._ollama_group.setVisible(p["id"] == "ollama")

        # Auto-detect Ollama when selected
        if p["id"] == "ollama":
            self._detect_ollama()

        # Show/hide the free-key button
        free_url = p.get("free_key_url", "")
        self._free_key_btn.setVisible(bool(free_url))

    def _toggle_key_visibility(self):
        if self._api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._eye_action.setText("Hide")
        else:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._eye_action.setText("Show")

    # ── Ollama detection & setup ─────────────────────────────────────

    def _discover_models(self):
        """Query the current cloud provider for available models."""
        idx = self._provider_combo.currentIndex()
        if idx < 0 or idx >= len(PROVIDERS):
            return
        p = PROVIDERS[idx]
        if p["id"] == "ollama":
            self._detect_ollama()
            return

        api_key = self._api_key_edit.text().strip()
        if not api_key and p["needs_key"]:
            QMessageBox.warning(self, "No API Key",
                                "Enter your API key first, then click Discover.")
            return

        from o3de_cli.ai.provider import discover_models
        self._discover_btn.setEnabled(False)
        self._discover_btn.setText("...")

        try:
            models = discover_models(p["id"], api_key)
        except Exception:
            models = []

        self._discover_btn.setEnabled(True)
        self._discover_btn.setText("Discover")

        if not models:
            QMessageBox.information(
                self, "No Models",
                f"Could not discover models from {p['name']}.\n"
                "Check your API key and try again.")
            return

        current_model = self._model_combo.currentText()
        self._model_combo.clear()
        for m in models:
            self._model_combo.addItem(m["id"])
        # Restore selection if still valid
        idx = self._model_combo.findText(current_model)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        elif self._model_combo.count() > 0:
            # Try to select the provider's default
            def_idx = self._model_combo.findText(p["default_model"])
            self._model_combo.setCurrentIndex(def_idx if def_idx >= 0 else 0)

    def _detect_ollama(self):
        """Check Ollama installation, service, and available models."""
        self._ollama_install_btn.hide()
        self._ollama_start_btn.hide()
        self._ollama_pull_btn.hide()

        # 1) Is the binary on PATH?
        ollama_path = shutil.which("ollama")
        if not ollama_path:
            self._ollama_status.setText(
                '<span style="color: #FF6666;">✖ Ollama is not installed</span>'
            )
            self._ollama_install_btn.show()
            return

        # 2) Is the server reachable?
        url = self._ollama_url_edit.text().strip() or "http://localhost:11434"
        import httpx
        try:
            r = httpx.get(f"{url}/api/tags", timeout=3.0)
            r.raise_for_status()
        except Exception:
            self._ollama_status.setText(
                '<span style="color: #FFAA44;">● Installed but not running</span>'
            )
            self._ollama_start_btn.show()
            return

        # 3) Any models pulled?
        models = [m["name"] for m in r.json().get("models", [])]
        if not models:
            self._ollama_status.setText(
                '<span style="color: #FFAA44;">● Running but no models found</span>'
            )
            self._ollama_pull_btn.show()
            return

        # All good!
        short = ", ".join(m.split(":")[0] for m in models[:6])
        self._ollama_status.setText(
            f'<span style="color: #66DD88;">✔ Running — {len(models)} model(s): {short}</span>'
        )
        # Populate the model combo with actually-available models
        self._model_combo.clear()
        for m in models:
            self._model_combo.addItem(m)
        if models:
            self._model_combo.setCurrentIndex(0)

    def _install_ollama(self):
        """Open the Ollama download page."""
        QDesktopServices.openUrl(QUrl("https://ollama.com/download"))
        QMessageBox.information(
            self, "Install Ollama",
            "The Ollama download page has been opened in your browser.\n\n"
            "After installing, click the \u21bb refresh button to re-detect."
        )

    def _start_ollama(self):
        """Try to launch the Ollama service."""
        try:
            if platform.system() == "Windows":
                # Launch ollama serve detached
                subprocess.Popen(
                    ["ollama", "serve"],
                    creationflags=subprocess.CREATE_NO_WINDOW
                    | subprocess.DETACHED_PROCESS,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            self._ollama_status.setText(
                '<span style="color: #FFAA44;">Starting Ollama\u2026</span>'
            )
            # Re-detect after a short delay
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2500, self._detect_ollama)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not start Ollama:\n{e}")

    def _pull_ollama_model(self):
        """Pull the default model (llama3) in a background process."""
        model = self._model_combo.currentText() or "llama3"
        self._ollama_pull_btn.setEnabled(False)
        self._ollama_pull_btn.setText(f"Pulling {model}\u2026")
        QApplication.processEvents()
        try:
            result = subprocess.run(
                ["ollama", "pull", model],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                QMessageBox.information(
                    self, "Model Pulled",
                    f"Successfully pulled {model}!"
                )
            else:
                QMessageBox.warning(
                    self, "Pull Failed",
                    f"ollama pull {model} failed:\n{result.stderr}"
                )
        except subprocess.TimeoutExpired:
            QMessageBox.warning(
                self, "Timeout",
                f"Pulling {model} is taking a while.\n"
                "It may still be downloading in the background.\n"
                f"You can also run: ollama pull {model}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not pull model:\n{e}")
        finally:
            self._ollama_pull_btn.setEnabled(True)
            self._ollama_pull_btn.setText("Pull llama3")
            self._detect_ollama()
    def _open_free_key_url(self):
        """Open the free API key URL in the default browser."""
        idx = self._provider_combo.currentIndex()
        p = PROVIDERS[idx]
        url = p.get("free_key_url", "")
        if url:
            QDesktopServices.openUrl(QUrl(url))
    # ── Load / Save config ──────────────────────────────────────────

    def _load_current(self):
        """Load current settings from o3de-pilot config."""
        try:
            from o3de_cli.core.config import get_config
            config = get_config()

            # Load per-provider API keys dict
            saved_keys = config.get("ai.api_keys", {})
            if isinstance(saved_keys, dict):
                self._api_keys = dict(saved_keys)

            # Migrate legacy single key if per-provider dict is empty
            provider = config.get("ai.provider", "ollama")
            legacy_key = config.get("ai.api_key", "")
            if legacy_key and provider not in self._api_keys:
                self._api_keys[provider] = legacy_key

            # Select matching provider (triggers _on_provider_changed
            # which loads the per-provider key into the field)
            for i, p in enumerate(PROVIDERS):
                if p["id"] == provider or (provider in ("claude", "anthropic") and p["id"] == "anthropic"):
                    self._provider_combo.setCurrentIndex(i)
                    break
            model = config.get("ai.model", "")
            if model:
                self._model_combo.setCurrentText(model)
            ollama_url = config.get("ai.ollama_url", "http://localhost:11434")
            self._ollama_url_edit.setText(ollama_url)
            thinking = config.get("ai.thinking_effort", "off")
            idx = self._thinking_combo.findData(thinking)
            if idx >= 0:
                self._thinking_combo.setCurrentIndex(idx)
            self._connection_verified = config.get("ai.connected", False)
        except Exception:
            pass  # Use defaults

    def _save_and_accept(self):
        """Save settings to o3de-pilot config and close."""
        try:
            from o3de_cli.core.config import get_config
            config = get_config()

            idx = self._provider_combo.currentIndex()
            p = PROVIDERS[idx]
            config.set("ai.provider", p["id"])
            config.set("ai.model", self._model_combo.currentText())
            config.set("ai.thinking_effort", self._thinking_combo.currentData() or "off")

            # Stash the current field value into the per-provider dict
            api_key = self._api_key_edit.text().strip()
            if api_key:
                self._api_keys[p["id"]] = api_key
            elif p["id"] in self._api_keys:
                del self._api_keys[p["id"]]

            # Persist the whole per-provider keys dict
            config.set("ai.api_keys", dict(self._api_keys))
            # Also write the active key as ai.api_key for CLI compat
            config.set("ai.api_key", api_key)

            if p["id"] == "ollama":
                config.set("ai.ollama_url", self._ollama_url_edit.text().strip())

            config.set("ai.connected", self._connection_verified)
            config.save()
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Could not save settings:\n{e}")
            return

        self.accept()

    # ── Test connection ─────────────────────────────────────────────

    def _test_connection(self):
        """Quick test of the selected AI provider."""
        idx = self._provider_combo.currentIndex()
        p = PROVIDERS[idx]
        provider_id = p["id"]
        model = self._model_combo.currentText()
        api_key = self._api_key_edit.text().strip()
        ollama_url = self._ollama_url_edit.text().strip()

        self._test_btn.setText("Testing…")
        self._test_btn.setEnabled(False)
        QApplication.processEvents()

        try:
            if provider_id == "ollama":
                self._test_ollama(ollama_url, model)
            elif provider_id == "gemini":
                self._test_gemini(api_key, model)
            elif provider_id == "openai":
                self._test_openai(api_key, model)
            elif provider_id == "anthropic":
                self._test_anthropic(api_key, model)
            elif provider_id in ("groq", "mistral", "deepseek", "xai",
                                 "openrouter", "together", "perplexity"):
                self._test_openai_compatible(provider_id, api_key, model)
            else:
                QMessageBox.information(self, "Test", "Unknown provider.")
        finally:
            self._test_btn.setText("Test Connection")
            self._test_btn.setEnabled(True)

    def _test_ollama(self, url: str, model: str):
        import httpx
        try:
            r = httpx.get(f"{url}/api/tags", timeout=5.0)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            if models:
                self._connection_verified = True
                QMessageBox.information(
                    self, "Ollama Connected",
                    f"Connected to Ollama at {url}\n\nAvailable models:\n" + "\n".join(models[:10])
                )
            else:
                QMessageBox.warning(self, "Ollama", "Connected but no models found.\nRun: ollama pull llama3")
        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", f"Could not connect to Ollama:\n{e}")

    def _test_gemini(self, api_key: str, model: str):
        if not api_key:
            QMessageBox.warning(self, "Missing Key", "Please enter a Gemini API key.")
            return
        import httpx
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            r = httpx.post(url, json={
                "contents": [{"parts": [{"text": "Say hello in 3 words."}]}]
            }, timeout=15.0)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            self._connection_verified = True
            QMessageBox.information(self, "Gemini Connected", f"Response: {text}")
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.json().get("error", {}).get("message", "")
            except Exception:
                body = e.response.text[:300]
            if e.response.status_code == 429:
                # 429 with valid key still counts as verified
                self._connection_verified = True
                QMessageBox.warning(
                    self, "Rate Limited",
                    "Your API key is valid but Google is rate-limiting requests.\n\n"
                    "This is normal for newly created keys — wait a minute\n"
                    "and try again. Your key has been saved."
                )
            elif e.response.status_code in (401, 403):
                QMessageBox.critical(
                    self, "Authentication Failed",
                    f"Invalid API key. Please check and re-enter it.\n\n{body}"
                )
            elif e.response.status_code == 404:
                QMessageBox.critical(
                    self, "Model Not Found",
                    f"Model '{model}' was not found.\n\n{body}\n\n"
                    "Try a different model from the dropdown."
                )
            else:
                QMessageBox.critical(
                    self, "Connection Failed",
                    f"HTTP {e.response.status_code}\n\n{body}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", f"Gemini test failed:\n{e}")

    def _test_openai(self, api_key: str, model: str):
        if not api_key:
            QMessageBox.warning(self, "Missing Key", "Please enter an OpenAI API key.")
            return
        import httpx
        try:
            r = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Say hello in 3 words."}],
                    "max_tokens": 20,
                },
                timeout=15.0,
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            self._connection_verified = True
            QMessageBox.information(self, "OpenAI Connected", f"Response: {text}")
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.json().get("error", {}).get("message", "")
            except Exception:
                body = e.response.text[:300]
            QMessageBox.critical(
                self, "Connection Failed",
                f"HTTP {e.response.status_code}\n\n{body}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", f"OpenAI test failed:\n{e}")

    def _test_anthropic(self, api_key: str, model: str):
        if not api_key:
            QMessageBox.warning(self, "Missing Key", "Please enter an Anthropic API key.")
            return
        import httpx
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 20,
                    "messages": [{"role": "user", "content": "Say hello in 3 words."}],
                },
                timeout=15.0,
            )
            r.raise_for_status()
            text = r.json()["content"][0]["text"]
            self._connection_verified = True
            QMessageBox.information(self, "Claude Connected", f"Response: {text}")
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.json().get("error", {}).get("message", "")
            except Exception:
                body = e.response.text[:300]
            QMessageBox.critical(
                self, "Connection Failed",
                f"HTTP {e.response.status_code}\n\n{body}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", f"Claude test failed:\n{e}")

    def _test_openai_compatible(self, provider_id: str, api_key: str, model: str):
        """Generic connection test for any OpenAI-compatible provider."""
        if not api_key:
            QMessageBox.warning(self, "Missing Key", f"Please enter an API key.")
            return
        from o3de_cli.ai.provider import OPENAI_COMPATIBLE_URLS
        base_url = OPENAI_COMPATIBLE_URLS.get(provider_id, "")
        if not base_url:
            QMessageBox.warning(self, "Error", f"Unknown provider: {provider_id}")
            return
        import httpx
        try:
            r = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Say hello in 3 words."}],
                    "max_tokens": 20,
                },
                timeout=15.0,
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            # Find display name for the provider
            name = next((p["name"] for p in PROVIDERS if p["id"] == provider_id), provider_id)
            self._connection_verified = True
            QMessageBox.information(self, f"{name}", f"Connected!\nResponse: {text}")
        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", f"Test failed:\n{e}")


# Needed for QApplication.processEvents() call in _test_connection
from PySide6.QtWidgets import QApplication
