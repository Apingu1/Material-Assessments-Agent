from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import MaterialInput


STATUSES = {
    "PENDING", "RESEARCHING", "READY_FOR_REVIEW", "PDE_RECOMMENDED",
    "PDE_REQUIRED", "EVIDENCE_GAP", "FAILED",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MaterialQueue:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_name TEXT NOT NULL,
                    dosage_forms TEXT NOT NULL DEFAULT '',
                    routes TEXT NOT NULL DEFAULT '',
                    product_context TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    output_dir TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def add(self, item: MaterialInput) -> int:
        now = _now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO materials
                    (material_name, dosage_forms, routes, product_context, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'PENDING', ?, ?)
                """,
                (item.material_name, item.dosage_forms, item.routes, item.product_context, now, now),
            )
            conn.commit()
            return int(cur.lastrowid)

    def import_csv(self, path: Path) -> int:
        count = 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "material_name" not in reader.fieldnames:
                raise ValueError("CSV must contain a material_name column")
            for row in reader:
                name = (row.get("material_name") or "").strip()
                if not name:
                    continue
                self.add(MaterialInput(
                    material_name=name,
                    dosage_forms=(row.get("dosage_forms") or "").strip(),
                    routes=(row.get("routes") or "").strip(),
                    product_context=(row.get("product_context") or "").strip(),
                ))
                count += 1
        return count

    def claim_next(self) -> tuple[int, MaterialInput] | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM materials WHERE status='PENDING' ORDER BY id LIMIT 1").fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute("UPDATE materials SET status='RESEARCHING', updated_at=? WHERE id=?", (_now(), row["id"]))
            conn.commit()
            return int(row["id"]), MaterialInput(
                material_name=row["material_name"], dosage_forms=row["dosage_forms"],
                routes=row["routes"], product_context=row["product_context"],
            )

    def update(self, material_id: int, status: str, output_dir: str | None = None, error: str | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"Unknown queue status: {status}")
        with self.connect() as conn:
            conn.execute(
                "UPDATE materials SET status=?, output_dir=?, error=?, updated_at=? WHERE id=?",
                (status, output_dir, error, _now(), material_id),
            )
            conn.commit()

    def list_rows(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM materials ORDER BY id"))
