# O3DE Pilot CLI - AI Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""AI assistant commands."""

import json
import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()


def _apply_thinking(provider, thinking: str | None):
    """Apply a --thinking override to the provider."""
    if thinking:
        from o3de_pilot.ai.provider import THINKING_LEVELS
        if thinking in THINKING_LEVELS:
            provider.thinking_effort = thinking
    return provider


@click.group()
def ai() -> None:
    """AI-powered assistance."""
    pass


@ai.command("setup")
def setup() -> None:
    """Interactive AI provider setup wizard.

    Walks through provider selection, API key entry, and connection test.
    """
    from o3de_pilot.core.config import get_config
    from o3de_pilot.ai.provider import OPENAI_COMPATIBLE_URLS

    cfg = get_config()

    providers = [
        ("ollama", "Ollama (local, free — requires Ollama running)"),
        ("anthropic", "Anthropic Claude (BYOK)"),
        ("openai", "OpenAI GPT (BYOK)"),
        ("gemini", "Google Gemini (free tier available)"),
        ("groq", "Groq (fast, free tier available)"),
        ("deepseek", "DeepSeek (BYOK)"),
        ("mistral", "Mistral AI (BYOK)"),
        ("xai", "xAI Grok (BYOK)"),
        ("openrouter", "OpenRouter (multi-model, BYOK)"),
        ("together", "Together AI (BYOK)"),
        ("perplexity", "Perplexity (BYOK)"),
    ]

    console.print("[bold]AI Provider Setup[/bold]\n")
    for i, (key, desc) in enumerate(providers, 1):
        console.print(f"  {i}. {desc}")
    console.print()

    choice = click.prompt("Select provider", type=int, default=1)
    if choice < 1 or choice > len(providers):
        console.print("[red]Invalid choice.[/red]")
        raise SystemExit(1)

    provider_key, provider_desc = providers[choice - 1]
    cfg.set("ai.provider", provider_key)

    # Provider-specific config
    if provider_key == "ollama":
        url = click.prompt("Ollama URL", default="http://localhost:11434")
        model = click.prompt("Model name", default="llama3")
        cfg.set("ai.ollama_url", url)
        cfg.set("ai.model", model)
    elif provider_key in ("anthropic", "openai", "gemini") or provider_key in OPENAI_COMPATIBLE_URLS:
        signup_urls = {
            "anthropic": "https://console.anthropic.com/",
            "openai": "https://platform.openai.com/api-keys",
            "gemini": "https://aistudio.google.com/apikey",
            "groq": "https://console.groq.com/keys",
            "deepseek": "https://platform.deepseek.com/api_keys",
            "mistral": "https://console.mistral.ai/api-keys/",
            "xai": "https://console.x.ai/",
            "openrouter": "https://openrouter.ai/keys",
            "together": "https://api.together.xyz/settings/api-keys",
            "perplexity": "https://www.perplexity.ai/settings/api",
        }
        if provider_key in signup_urls:
            console.print(f"\n[dim]Get your API key at: {signup_urls[provider_key]}[/dim]")

        api_key = click.prompt("API key", hide_input=True)
        cfg.set("ai.api_key", api_key)

        # Try dynamic model discovery
        from o3de_pilot.ai.provider import discover_models
        console.print("[dim]Discovering available models...[/dim]")
        available = discover_models(provider_key, api_key)

        default_models = {
            "anthropic": "claude-sonnet-4-20250514",
            "openai": "gpt-4o",
            "gemini": "gemini-2.5-flash",
            "groq": "llama-3.3-70b-versatile",
            "deepseek": "deepseek-chat",
            "mistral": "mistral-large-latest",
        }

        if available:
            model_ids = [m["id"] for m in available]
            console.print(f"[green]Found {len(model_ids)} model(s):[/green]")
            for i, mid in enumerate(model_ids[:15], 1):
                console.print(f"  {i}. {mid}")
            if len(model_ids) > 15:
                console.print(f"  [dim]... and {len(model_ids) - 15} more[/dim]")
            default = default_models.get(provider_key, model_ids[0])
            if default not in model_ids:
                default = model_ids[0]
            model = click.prompt("Model", default=default)
        else:
            console.print("[dim]Could not discover models — using defaults[/dim]")
            model = click.prompt("Model", default=default_models.get(provider_key, ""))
        cfg.set("ai.model", model)

    cfg.set("ai.enabled", "true")
    cfg.save()

    # Test connection
    console.print("\n[dim]Testing connection...[/dim]")
    try:
        from o3de_pilot.ai.provider import get_ai_provider
        provider = get_ai_provider()
        response = provider.complete("Say 'hello' in one word.")
        console.print(f"[green]Connected![/green] Response: {response[:100]}")
    except Exception as e:
        console.print(f"[yellow]Connection test failed:[/yellow] {e}")
        console.print("[dim]Your config was saved — you can fix it with 'o3de-pilot config set'[/dim]")


@ai.command("status")
def status() -> None:
    """Show current AI configuration status."""
    from o3de_pilot.core.config import get_config

    cfg = get_config()
    enabled = cfg.get("ai.enabled", "false")
    provider = cfg.get("ai.provider", "none")
    model = cfg.get("ai.model", "default")
    has_key = bool(cfg.get("ai.api_key", ""))
    thinking = cfg.get("ai.thinking_effort", "off")

    console.print("[bold]AI Configuration[/bold]")
    console.print(f"  Enabled:   {'[green]yes[/green]' if enabled == 'true' else '[dim]no[/dim]'}")
    console.print(f"  Provider:  [cyan]{provider}[/cyan]")
    console.print(f"  Model:     {model}")
    console.print(f"  API Key:   {'[green]configured[/green]' if has_key else '[dim]not set[/dim]'}")
    console.print(f"  Thinking:  {thinking}")


@ai.command("models")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.option("--provider", "-p", "provider_name", help="Override provider (default: configured)")
def models_command(as_json: bool, provider_name: str | None) -> None:
    """Discover available models from the configured provider."""
    from o3de_pilot.core.config import get_config
    from o3de_pilot.ai.provider import discover_models, OPENAI_COMPATIBLE_URLS

    cfg = get_config()
    prov = provider_name or cfg.get("ai.provider", "ollama")
    api_key = cfg.get("ai.api_key", "")
    _per_keys = cfg.get("ai.api_keys", {})
    if isinstance(_per_keys, dict) and prov in _per_keys:
        api_key = _per_keys[prov]
    ollama_url = cfg.get("ai.ollama_url", "http://localhost:11434")

    with console.status(f"Querying {prov} for available models..."):
        result = discover_models(prov, api_key, ollama_url)

    if as_json:
        console.print_json(json.dumps(result))
        return

    if not result:
        console.print(f"[yellow]No models found for [bold]{prov}[/bold].[/yellow]")
        console.print("[dim]Check your API key or provider status.[/dim]")
        return

    from rich.table import Table
    table = Table(title=f"Available Models — {prov}")
    table.add_column("Model ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Details", style="dim")

    for m in sorted(result, key=lambda x: x.get("id", "")):
        details = ""
        if m.get("context_window"):
            details = f"{m['context_window']:,} tokens"
        elif m.get("owned_by"):
            details = m["owned_by"]
        elif m.get("size"):
            details = f"{m['size'] / 1e9:.1f} GB"
        table.add_row(m.get("id", ""), m.get("name", ""), details)

    console.print(table)
    console.print(f"\n[dim]{len(result)} model(s) available[/dim]")


@ai.command("local")
@click.option("--model", "-m", default=None, help="Model to pull (default: llama3.2:3b)")
def local_setup(model: str | None) -> None:
    """Set up local AI with Ollama — free, no API key needed.

    Checks if Ollama is running and pulls the default model if needed.
    """
    from o3de_pilot.ai.provider import (
        DEFAULT_LOCAL_MODEL, _ollama_is_running, _ollama_has_model, _ollama_pull,
    )

    target = model or DEFAULT_LOCAL_MODEL
    ollama_url = "http://localhost:11434"

    try:
        from o3de_pilot.core.config import get_config
        cfg = get_config()
        ollama_url = cfg.get("ai.ollama_url", ollama_url)
    except Exception:
        pass

    # Step 1: check Ollama daemon
    console.print("[bold]Checking Ollama...[/bold]")
    if not _ollama_is_running(ollama_url):
        console.print("[red]Ollama is not running.[/red]")
        console.print("  Install: [cyan]https://ollama.com[/cyan]")
        console.print("  Start:   [cyan]ollama serve[/cyan]")
        raise SystemExit(1)
    console.print("  [green]✓[/green] Ollama running")

    # Step 2: check model
    console.print(f"[bold]Checking model [cyan]{target}[/cyan]...[/bold]")
    if _ollama_has_model(ollama_url, target):
        console.print(f"  [green]✓[/green] {target} already available")
    else:
        console.print(f"  Pulling {target} (this may take a few minutes)...")
        from rich.progress import Progress

        with Progress(console=console) as progress:
            task = progress.add_task(f"Pulling {target}", total=None)

            def _on_progress(status, completed, total):
                if total > 0:
                    progress.update(task, total=total, completed=completed, description=status)
                else:
                    progress.update(task, description=status)

            ok = _ollama_pull(ollama_url, target, on_progress=_on_progress)

        if ok:
            console.print(f"  [green]✓[/green] {target} pulled successfully")
        else:
            console.print(f"  [red]✗[/red] Failed to pull {target}")
            console.print(f"  Try manually: [cyan]ollama pull {target}[/cyan]")
            raise SystemExit(1)

    # Step 3: configure
    try:
        from o3de_pilot.core.config import get_config
        cfg = get_config()
        cfg.set("ai.provider", "ollama")
        cfg.set("ai.model", target)
        cfg.set("ai.enabled", "true")
        cfg.save()
        console.print(f"\n[green bold]Local AI ready![/green bold] Using {target}")
        console.print("[dim]Try: o3de-pilot ai ask 'What is a gem?'[/dim]")
    except Exception as e:
        console.print(f"[yellow]Model pulled but could not save config:[/yellow] {e}")


@ai.command("ask")
@click.argument("prompt", nargs=-1, required=True)
@click.option("--thinking", type=click.Choice(["off", "low", "medium", "high", "max"]), help="Thinking effort level")
def ask(prompt: tuple[str, ...], thinking: str | None) -> None:
    """Ask the AI a question about O3DE."""
    question = " ".join(prompt)
    
    console.print(Panel(question, title="Your Question", border_style="blue"))
    
    from o3de_pilot.ai.provider import get_ai_provider
    
    try:
        provider = _apply_thinking(get_ai_provider(), thinking)
        response = provider.complete(question)
        console.print(Panel(Markdown(response), title="AI Response", border_style="green"))
    except Exception as e:
        console.print(f"[red]AI Error:[/red] {e}")
        console.print("[dim]Make sure you have configured an AI provider with 'o3de-pilot config set ai.provider <name>'[/dim]")


@ai.command("diagnose")
@click.option("--path", "-p", type=click.Path(exists=True), help="Project path")
@click.option("--thinking", type=click.Choice(["off", "low", "medium", "high", "max"]), help="Thinking effort level")
def diagnose(path: str | None, thinking: str | None) -> None:
    """AI-powered build error diagnosis."""
    from pathlib import Path as P
    from o3de_pilot.ai.provider import get_ai_provider

    project_dir = P(path) if path else P.cwd()
    console.print(f"[bold]Running AI diagnostics on [cyan]{project_dir}[/cyan]...[/bold]")

    # Collect CMake / build log snippets if available
    context_parts: list[str] = []
    for log_name in ("CMakeOutput.log", "CMakeError.log", "build.log"):
        candidate = project_dir / "build" / log_name
        if candidate.exists():
            tail = candidate.read_text(errors="replace")[-4000:]
            context_parts.append(f"--- {log_name} (last 4 KB) ---\n{tail}")

    if not context_parts:
        context_parts.append("No build logs found in the project directory.")

    prompt = (
        "You are an O3DE build-error diagnostician.\n"
        "Analyse the following build output and suggest fixes.\n\n"
        + "\n\n".join(context_parts)
    )

    try:
        provider = _apply_thinking(get_ai_provider(), thinking)
        response = provider.complete(prompt)
        console.print(Panel(Markdown(response), title="Diagnosis", border_style="green"))
    except Exception as e:
        console.print(f"[red]AI Error:[/red] {e}")


@ai.command("generate")
@click.argument("obj_type", type=click.Choice(["gem", "component", "script"]))
@click.argument("description", nargs=-1, required=True)
@click.option("--thinking", type=click.Choice(["off", "low", "medium", "high", "max"]), help="Thinking effort level")
def generate(obj_type: str, description: tuple[str, ...], thinking: str | None) -> None:
    """AI-powered code generation."""
    from o3de_pilot.ai.provider import get_ai_provider

    desc = " ".join(description)
    console.print(f"[bold]Generating {obj_type}:[/bold] {desc}")

    prompt = (
        f"Generate an O3DE {obj_type} based on this description: {desc}\n\n"
        "Provide the complete file contents with proper O3DE conventions, "
        "including CMakeLists.txt entries where applicable. "
        "Use markdown code blocks with file paths as titles."
    )

    try:
        provider = _apply_thinking(get_ai_provider(), thinking)
        response = provider.complete(prompt)
        console.print(Panel(Markdown(response), title=f"Generated {obj_type}", border_style="green"))
    except Exception as e:
        console.print(f"[red]AI Error:[/red] {e}")


@ai.command("migrate")
@click.option("--path", "-p", type=click.Path(exists=True), help="Project path")
@click.option("--target", "-t", help="Target engine version")
@click.option("--thinking", type=click.Choice(["off", "low", "medium", "high", "max"]), help="Thinking effort level")
def migrate(path: str | None, target: str | None, thinking: str | None) -> None:
    """AI-assisted project migration."""
    from pathlib import Path as P
    from o3de_pilot.ai.provider import get_ai_provider

    project_dir = P(path) if path else P.cwd()
    target_label = target or "latest"
    console.print(
        f"[bold]Analysing migration to [cyan]{target_label}[/cyan] "
        f"for [cyan]{project_dir}[/cyan]...[/bold]"
    )

    # Gather project metadata for context
    context_parts: list[str] = []
    for name in ("project.json", "gem.json", "engine.json"):
        candidate = project_dir / name
        if candidate.exists():
            context_parts.append(f"--- {name} ---\n{candidate.read_text(errors='replace')[:4000]}")

    cmake = project_dir / "CMakeLists.txt"
    if cmake.exists():
        context_parts.append(f"--- CMakeLists.txt ---\n{cmake.read_text(errors='replace')[:4000]}")

    if not context_parts:
        context_parts.append("No project metadata files found.")

    prompt = (
        f"You are an O3DE migration assistant. The user wants to migrate to {target_label}.\n"
        "Analyse the project files below and provide a step-by-step migration plan, "
        "highlighting breaking changes and deprecated APIs.\n\n"
        + "\n\n".join(context_parts)
    )

    try:
        provider = _apply_thinking(get_ai_provider(), thinking)
        response = provider.complete(prompt)
        console.print(Panel(Markdown(response), title="Migration Plan", border_style="green"))
    except Exception as e:
        console.print(f"[red]AI Error:[/red] {e}")


@ai.command("explain")
@click.argument("topic", nargs=-1, required=True)
@click.option("--thinking", type=click.Choice(["off", "low", "medium", "high", "max"]), help="Thinking effort level")
def explain(topic: tuple[str, ...], thinking: str | None) -> None:
    """Get AI explanation of an O3DE concept."""
    from o3de_pilot.ai.provider import get_ai_provider

    topic_str = " ".join(topic)
    console.print(f"[bold]Explaining:[/bold] {topic_str}")

    prompt = (
        "Explain the following O3DE concept clearly and concisely, "
        "with practical examples where helpful:\n\n"
        f"{topic_str}"
    )

    try:
        provider = _apply_thinking(get_ai_provider(), thinking)
        response = provider.complete(prompt)
        console.print(Panel(Markdown(response), title="Explanation", border_style="green"))
    except Exception as e:
        console.print(f"[red]AI Error:[/red] {e}")


@ai.command("chat")
def chat() -> None:
    """Interactive multi-turn conversation with tool calling.
    
    The AI can call o3de-pilot CLI commands to answer questions about
    your workspaces, gems, engines, and builds.  Type 'exit' or 'quit'
    to end the session.
    """
    from o3de_pilot.ai.provider import get_ai_provider
    from o3de_pilot.ai.conversation import ConversationSession
    from o3de_pilot.ai.command_router import match_command

    console.print("[bold]o3de-pilot AI Chat[/bold]")
    console.print("[dim]Type 'exit' to quit. AI can call CLI tools to help you.[/dim]\n")

    def confirm_fn(tool_name: str, args: dict) -> bool:
        return click.confirm(f"Execute {tool_name}({args})?")

    session = ConversationSession(confirm_fn=confirm_fn)

    try:
        provider = get_ai_provider()
    except Exception as e:
        console.print(f"[red]AI Error:[/red] {e}")
        console.print("[dim]Run 'o3de-pilot ai setup' to configure a provider.[/dim]")
        return

    while True:
        try:
            user_input = click.prompt("You", prompt_suffix="> ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if user_input.strip().lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye![/dim]")
            break

        # Try local pattern match first
        action = match_command(user_input)
        if action:
            console.print(f"[cyan]→ {action.description}[/cyan]")
            tool_name = action.command.replace(" ", "_")
            try:
                result = session.execute_tool_call(tool_name, action.args)
                console.print(Panel(
                    json.dumps(result, indent=2)[:2000],
                    title="Result",
                    border_style="green" if result.get("status") == "ok" else "red",
                ))
            except Exception as e:
                console.print(f"[red]Tool error:[/red] {e}")
            continue

        # AI conversation turn
        session.add_user_message(user_input)
        try:
            messages = session.get_context_messages()
            full_prompt = session.system_prompt + "\n\n"
            for msg in messages:
                full_prompt += f"{msg['role'].upper()}: {msg['content']}\n\n"
            
            response = provider.complete(full_prompt)
            session.add_assistant_message(response)
            console.print(Panel(Markdown(response), border_style="green"))
        except Exception as e:
            console.print(f"[red]AI Error:[/red] {e}")
