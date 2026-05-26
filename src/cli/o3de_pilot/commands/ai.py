# O3DE Pilot CLI - AI Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""AI assistant commands."""

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()


@click.group()
def ai() -> None:
    """AI-powered assistance."""
    pass


@ai.command("ask")
@click.argument("prompt", nargs=-1, required=True)
def ask(prompt: tuple[str, ...]) -> None:
    """Ask the AI a question about O3DE."""
    question = " ".join(prompt)
    
    console.print(Panel(question, title="Your Question", border_style="blue"))
    
    # TODO: Implement AI query
    from o3de_pilot.ai.provider import get_ai_provider
    
    try:
        provider = get_ai_provider()
        response = provider.complete(question)
        console.print(Panel(Markdown(response), title="AI Response", border_style="green"))
    except Exception as e:
        console.print(f"[red]AI Error:[/red] {e}")
        console.print("[dim]Make sure you have configured an AI provider with 'o3de-pilot config set ai.provider <name>'[/dim]")


@ai.command("diagnose")
@click.option("--path", "-p", type=click.Path(exists=True), help="Project path")
def diagnose(path: str | None) -> None:
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
        provider = get_ai_provider()
        response = provider.complete(prompt)
        console.print(Panel(Markdown(response), title="Diagnosis", border_style="green"))
    except Exception as e:
        console.print(f"[red]AI Error:[/red] {e}")


@ai.command("generate")
@click.argument("obj_type", type=click.Choice(["gem", "component", "script"]))
@click.argument("description", nargs=-1, required=True)
def generate(obj_type: str, description: tuple[str, ...]) -> None:
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
        provider = get_ai_provider()
        response = provider.complete(prompt)
        console.print(Panel(Markdown(response), title=f"Generated {obj_type}", border_style="green"))
    except Exception as e:
        console.print(f"[red]AI Error:[/red] {e}")


@ai.command("migrate")
@click.option("--path", "-p", type=click.Path(exists=True), help="Project path")
@click.option("--target", "-t", help="Target engine version")
def migrate(path: str | None, target: str | None) -> None:
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
        provider = get_ai_provider()
        response = provider.complete(prompt)
        console.print(Panel(Markdown(response), title="Migration Plan", border_style="green"))
    except Exception as e:
        console.print(f"[red]AI Error:[/red] {e}")


@ai.command("explain")
@click.argument("topic", nargs=-1, required=True)
def explain(topic: tuple[str, ...]) -> None:
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
        provider = get_ai_provider()
        response = provider.complete(prompt)
        console.print(Panel(Markdown(response), title="Explanation", border_style="green"))
    except Exception as e:
        console.print(f"[red]AI Error:[/red] {e}")
