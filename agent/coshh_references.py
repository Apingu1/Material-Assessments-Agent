"""Persistent, concurrency-safe ES.COSHH.NNN reference assignment.

References are allocated once per assessment output run. A failed generation
retains its allocated number so no other assessment can reuse its audit trail.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path


def reserve_coshh_reference(db_path: Path, output_dir: Path) -> tuple[str, date]:
    """Reserve/retrieve the reference and original completion date for a run."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    run_key = str(output_dir.resolve())
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS coshh_reference_registry (
                sequence INTEGER PRIMARY KEY,
                run_key TEXT NOT NULL UNIQUE,
                completed_on TEXT NOT NULL
            )
        """)
        row = conn.execute(
            "SELECT sequence, completed_on FROM coshh_reference_registry WHERE run_key=?",
            (run_key,),
        ).fetchone()
        if row is None:
            number = conn.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM coshh_reference_registry"
            ).fetchone()[0]
            completed = date.today()
            conn.execute(
                "INSERT INTO coshh_reference_registry(sequence,run_key,completed_on) "
                "VALUES (?,?,?)", (number, run_key, completed.isoformat()),
            )
        else:
            number, raw_completed = row
            completed = date.fromisoformat(raw_completed)
        conn.commit()
    return f"ES.COSHH.{number:03d}", completed
