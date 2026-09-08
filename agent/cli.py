from __future__ import annotations

import json
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import Settings
from .models import COSHHArea, MaterialInput
from .pipeline import AssessmentPipeline
from .queue import MaterialQueue

app = typer.Typer(help="Autonomous research and draft-generation agent for cleaning validation and COSHH.")
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


def _coshh_status(output_dir: Path) -> str:
    path = output_dir / "COSHH_STATUS.json"
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("status") or "FAILED")
    except Exception:
        return "FAILED"


def _parse_areas(value: str) -> list[COSHHArea]:
    if not value.strip():
        return MaterialInput(material_name="placeholder").coshh_areas
    result: list[COSHHArea] = []
    aliases = {
        "GOODS_IN": "GOODS_IN_WAREHOUSE",
        "WAREHOUSE": "GOODS_IN_WAREHOUSE",
        "R&D": "R_AND_D",
    }
    for raw in value.replace(";", ",").split(","):
        key = raw.strip().upper().replace(" ", "_")
        key = aliases.get(key, key)
        try:
            area = COSHHArea(key)
        except ValueError as exc:
            raise typer.BadParameter(f"Unknown COSHH area: {raw}") from exc
        if area not in result:
            result.append(area)
    return result


def _item(
    material_name: str,
    dosage_forms: str,
    routes: str,
    product_context: str,
    coshh_areas: str,
    people_exposed: str,
    typical_quantity: str,
    existing_controls: str,
    frequency: str,
    duration: str,
) -> MaterialInput:
    return MaterialInput(
        material_name=material_name,
        dosage_forms=dosage_forms,
        routes=routes,
        product_context=product_context,
        coshh_areas=_parse_areas(coshh_areas),
        people_exposed=people_exposed,
        typical_quantity=typical_quantity,
        existing_controls=existing_controls,
        frequency=frequency,
        duration=duration,
    )


@app.command()
def check() -> None:
    """Check configuration and confirm the cleaning-validation DOCX tags are present."""
    from .docx_template import validate_template

    settings = _settings(require_runtime=False)
    validate_template(settings.template_path)
    console.print(f"[green]Cleaning template OK:[/green] {settings.template_path}")
    console.print(f"Model: {settings.openai_model}")
    console.print("OpenAI key: " + ("configured" if settings.openai_api_key else "NOT configured"))
    console.print(f"Evidence capture: {settings.capture_evidence}")
    console.print("COSHH: enabled; generated programmatically from SDS/workplace context")


@app.command("add")
def add_material(
    material_name: str,
    dosage_forms: str = typer.Option("", "--dosage-form", "-d"),
    routes: str = typer.Option("", "--route", "-r"),
    product_context: str = typer.Option("", "--context", "-c"),
    coshh_areas: str = typer.Option("GOODS_IN_WAREHOUSE,SAMPLING,QC,PRODUCTION", "--coshh-areas"),
    people_exposed: str = typer.Option("Production, QC, Sampling and Warehouse personnel as applicable", "--people-exposed"),
    typical_quantity: str = typer.Option("", "--quantity"),
    existing_controls: str = typer.Option("", "--controls"),
    frequency: str = typer.Option("Infrequent", "--frequency"),
    duration: str = typer.Option("<30 mins", "--duration"),
) -> None:
    """Add one material to the autonomous queue."""
    settings = _settings()
    queue = MaterialQueue(settings.database_path)
    item = _item(material_name, dosage_forms, routes, product_context, coshh_areas, people_exposed, typical_quantity, existing_controls, frequency, duration)
    material_id = queue.add(item)
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
    table = Table("ID", "Material", "Cleaning", "COSHH", "Output", "Error")
    for row in queue.list_rows():
        table.add_row(
            str(row["id"]),
            row["material_name"],
            row["cleaning_status"],
            row["coshh_status"],
            row["output_dir"] or "",
            (row["error"] or "")[:80],
        )
    console.print(table)


@app.command()
def assess(
    material_name: str,
    dosage_forms: str = typer.Option("", "--dosage-form", "-d"),
    routes: str = typer.Option("", "--route", "-r"),
    product_context: str = typer.Option("", "--context", "-c"),
    coshh_areas: str = typer.Option("GOODS_IN_WAREHOUSE,SAMPLING,QC,PRODUCTION", "--coshh-areas"),
    people_exposed: str = typer.Option("Production, QC, Sampling and Warehouse personnel as applicable", "--people-exposed"),
    typical_quantity: str = typer.Option("", "--quantity"),
    existing_controls: str = typer.Option("", "--controls"),
    frequency: str = typer.Option("Infrequent", "--frequency"),
    duration: str = typer.Option("<30 mins", "--duration"),
) -> None:
    """Run one material immediately without adding it to the queue."""
    settings = _settings(require_runtime=True)
    pipeline = AssessmentPipeline(settings)
    item = _item(material_name, dosage_forms, routes, product_context, coshh_areas, people_exposed, typical_quantity, existing_controls, frequency, duration)
    with console.status(f"Researching {material_name}..."):
        bundle, output_dir = pipeline.run(item)
    console.print(f"[green]Complete:[/green] {output_dir}")
    console.print(f"Cleaning PDE Requirement: [bold]{bundle.scoring.pde_requirement}[/bold]")
    console.print(f"COSHH status: [bold]{_coshh_status(output_dir)}[/bold]")
    if bundle.scoring.review_flags:
        console.print(f"Cleaning review flags: {len(bundle.scoring.review_flags)}")


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
            coshh = _coshh_status(output_dir)
            queue.update(
                material_id,
                status,
                str(output_dir),
                None,
                cleaning_status=status,
                coshh_status=coshh,
            )
            console.print(f"[green]{item.material_name} -> Cleaning {status}; COSHH {coshh}[/green] ({output_dir})")
        except Exception as exc:
            queue.update(
                material_id,
                "FAILED",
                None,
                str(exc),
                cleaning_status="FAILED",
                coshh_status="FAILED",
            )
            console.print(f"[red]{item.material_name} failed:[/red] {exc}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Start the local web interface."""
    import uvicorn

    _settings(require_runtime=True)
    console.print(f"Starting Material Assessment Agent UI on http://{host}:{port}")
    uvicorn.run("agent.web:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
