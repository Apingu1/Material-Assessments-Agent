from __future__ import annotations

import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import Settings
from .models import MaterialInput
from .pipeline import AssessmentPipeline
from .queue import MaterialQueue

app = typer.Typer(help="Autonomous research and draft-generation agent for ES.SOP.272.F01.V02.")
console = Console()


def _settings(require_runtime: bool = False) -> Settings:
    settings = Settings.load()
    if require_runtime:
        settings.require_runtime()
    return settings


def _final_status(bundle) -> str:
    pde = bundle.scoring.pde_requirement
    if pde == "MANDATORY":
        return "PDE_REQUIRED"
    if pde == "RECOMMENDED":
        return "PDE_RECOMMENDED"
    if pde == "UNDETERMINED":
        return "EVIDENCE_GAP"
    return "READY_FOR_REVIEW"


@app.command()
def check() -> None:
    """Check configuration and confirm the agent-ready DOCX tags are present."""
    from .docx_template import validate_template

    settings = _settings(require_runtime=False)
    validate_template(settings.template_path)
    console.print(f"[green]Template OK:[/green] {settings.template_path}")
    console.print(f"Model: {settings.openai_model}")
    console.print("OpenAI key: " + ("configured" if settings.openai_api_key else "NOT configured"))
    console.print(f"Evidence capture: {settings.capture_evidence}")


@app.command("add")
def add_material(
    material_name: str,
    dosage_forms: str = typer.Option("", "--dosage-form", "-d"),
    routes: str = typer.Option("", "--route", "-r"),
    product_context: str = typer.Option("", "--context", "-c"),
) -> None:
    """Add one material to the autonomous queue."""
    settings = _settings()
    queue = MaterialQueue(settings.database_path)
    material_id = queue.add(MaterialInput(material_name=material_name, dosage_forms=dosage_forms, routes=routes, product_context=product_context))
    console.print(f"Added queue item #{material_id}: {material_name}")


@app.command("import-csv")
def import_csv(path: Path) -> None:
    """Import materials from CSV. Required column: material_name."""
    settings = _settings()
    queue = MaterialQueue(settings.database_path)
    count = queue.import_csv(path)
    console.print(f"Imported {count} material(s).")


@app.command("list")
def list_queue() -> None:
    """Show the current material queue."""
    settings = _settings()
    queue = MaterialQueue(settings.database_path)
    table = Table("ID", "Material", "Status", "Output", "Error")
    for row in queue.list_rows():
        table.add_row(str(row["id"]), row["material_name"], row["status"], row["output_dir"] or "", (row["error"] or "")[:80])
    console.print(table)


@app.command()
def assess(
    material_name: str,
    dosage_forms: str = typer.Option("", "--dosage-form", "-d"),
    routes: str = typer.Option("", "--route", "-r"),
    product_context: str = typer.Option("", "--context", "-c"),
) -> None:
    """Run one material immediately without adding it to the queue."""
    settings = _settings(require_runtime=True)
    pipeline = AssessmentPipeline(settings)
    item = MaterialInput(material_name=material_name, dosage_forms=dosage_forms, routes=routes, product_context=product_context)
    with console.status(f"Researching {material_name}..."):
        bundle, output_dir = pipeline.run(item)
    console.print(f"[green]Complete:[/green] {output_dir}")
    console.print(f"PDE Requirement: [bold]{bundle.scoring.pde_requirement}[/bold]")
    if bundle.scoring.review_flags:
        console.print(f"Operator review flags: {len(bundle.scoring.review_flags)}")


@app.command("run")
def run_queue(
    continuous: bool = typer.Option(False, "--continuous", help="Keep waiting for new queue items."),
    poll_seconds: int = typer.Option(60, "--poll-seconds", min=5),
) -> None:
    """Process queued materials sequentially."""
    settings = _settings(require_runtime=True)
    queue = MaterialQueue(settings.database_path)
    pipeline = AssessmentPipeline(settings)
    console.print("Material Assessment Agent started.")
    while True:
        claimed = queue.claim_next()
        if not claimed:
            if not continuous:
                console.print("Queue is empty.")
                return
            time.sleep(poll_seconds)
            continue
        material_id, item = claimed
        console.print(f"Processing #{material_id}: [bold]{item.material_name}[/bold]")
        try:
            bundle, output_dir = pipeline.run(item)
            status = _final_status(bundle)
            queue.update(material_id, status, str(output_dir), None)
            console.print(f"[green]{item.material_name} -> {status}[/green] ({output_dir})")
        except Exception as exc:
            queue.update(material_id, "FAILED", None, str(exc))
            console.print(f"[red]{item.material_name} failed:[/red] {exc}")


if __name__ == "__main__":
    app()
