from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import COSHHArea, MaterialInput


STATUSES = {
    "PENDING", "RESEARCHING", "READY_FOR_REVIEW", "PDE_RECOMMENDED",
    "PDE_REQUIRED", "EVIDENCE_GAP", "FAILED",
}
COSHH_STATUSES = {"PENDING", "RESEARCHING", "READY_FOR_REVIEW", "REVIEW_REQUIRED", "FAILED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _area_text(areas: list[COSHHArea]) -> str:
    return ",".join(area.value for area in areas)


def _parse_areas(value: str) -> list[COSHHArea]:
    if not value.strip():
        return MaterialInput(material_name="placeholder").coshh_areas
    result: list[COSHHArea] = []
    for raw in value.replace(";", ",").split(","):
        raw = raw.strip().upper().replace(" ", "_").replace("&", "AND")
        aliases = {
            "GOODS_IN": "GOODS_IN_WAREHOUSE",
            "WAREHOUSE": "GOODS_IN_WAREHOUSE",
            "GOODS_IN/WAREHOUSE": "GOODS_IN_WAREHOUSE",
            "R&D": "R_AND_D",
            "R_AND_D": "R_AND_D",
        }
        raw = aliases.get(raw, raw)
        try:
            area = COSHHArea(raw)
        except ValueError:
            continue
        if area not in result:
            result.append(area)
    return result or MaterialInput(material_name="placeholder").coshh_areas


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
                    coshh_areas TEXT NOT NULL DEFAULT 'GOODS_IN_WAREHOUSE,SAMPLING,QC,PRODUCTION',
                    people_exposed TEXT NOT NULL DEFAULT '',
                    typical_quantity TEXT NOT NULL DEFAULT '',
                    existing_controls TEXT NOT NULL DEFAULT '',
                    frequency TEXT NOT NULL DEFAULT 'Infrequent',
                    duration TEXT NOT NULL DEFAULT '<30 mins',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    cleaning_status TEXT NOT NULL DEFAULT 'PENDING',
                    coshh_status TEXT NOT NULL DEFAULT 'PENDING',
                    output_dir TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(materials)")}
            additions = {
                "coshh_areas": "TEXT NOT NULL DEFAULT 'GOODS_IN_WAREHOUSE,SAMPLING,QC,PRODUCTION'",
                "people_exposed": "TEXT NOT NULL DEFAULT ''",
                "typical_quantity": "TEXT NOT NULL DEFAULT ''",
                "existing_controls": "TEXT NOT NULL DEFAULT ''",
                "frequency": "TEXT NOT NULL DEFAULT 'Infrequent'",
                "duration": "TEXT NOT NULL DEFAULT '<30 mins'",
                "cleaning_status": "TEXT NOT NULL DEFAULT 'PENDING'",
                "coshh_status": "TEXT NOT NULL DEFAULT 'PENDING'",
            }
            for name, ddl in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE materials ADD COLUMN {name} {ddl}")
            conn.commit()

    def add(self, item: MaterialInput) -> int:
        now = _now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO materials
                    (material_name, dosage_forms, routes, product_context,
                     coshh_areas, people_exposed, typical_quantity, existing_controls,
                     frequency, duration, status, cleaning_status, coshh_status,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 'PENDING', 'PENDING', ?, ?)
                """,
                (
                    item.material_name,
                    item.dosage_forms,
                    item.routes,
                    item.product_context,
                    _area_text(item.coshh_areas),
                    item.people_exposed,
                    item.typical_quantity,
                    item.existing_controls,
                    item.frequency,
                    item.duration,
                    now,
                    now,
                ),
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
                self.add(
                    MaterialInput(
                        material_name=name,
                        dosage_forms=(row.get("dosage_forms") or "").strip(),
                        routes=(row.get("routes") or "").strip(),
                        product_context=(row.get("product_context") or "").strip(),
                        coshh_areas=_parse_areas((row.get("coshh_areas") or "").strip()),
                        people_exposed=(row.get("people_exposed") or "Production, QC, Sampling and Warehouse personnel as applicable").strip(),
                        typical_quantity=(row.get("typical_quantity") or "").strip(),
                        existing_controls=(row.get("existing_controls") or "").strip(),
                        frequency=(row.get("frequency") or "Infrequent").strip(),
                        duration=(row.get("duration") or "<30 mins").strip(),
                    )
                )
                count += 1
        return count

    def claim_next(self) -> tuple[int, MaterialInput] | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM materials WHERE status='PENDING' ORDER BY id LIMIT 1"
            ).fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute(
                "UPDATE materials SET status='RESEARCHING', cleaning_status='RESEARCHING', coshh_status='RESEARCHING', updated_at=? WHERE id=?",
                (_now(), row["id"]),
            )
            conn.commit()
            return int(row["id"]), MaterialInput(
                material_name=row["material_name"],
                dosage_forms=row["dosage_forms"],
                routes=row["routes"],
                product_context=row["product_context"],
                coshh_areas=_parse_areas(row["coshh_areas"]),
                people_exposed=row["people_exposed"],
                typical_quantity=row["typical_quantity"],
                existing_controls=row["existing_controls"],
                frequency=row["frequency"],
                duration=row["duration"],
            )

    def update(
        self,
        material_id: int,
        status: str,
        output_dir: str | None = None,
        error: str | None = None,
        *,
        cleaning_status: str | None = None,
        coshh_status: str | None = None,
    ) -> None:
        if status not in STATUSES:
            raise ValueError(f"Unknown queue status: {status}")
        if coshh_status is not None and coshh_status not in COSHH_STATUSES:
            raise ValueError(f"Unknown COSHH status: {coshh_status}")
        with self.connect() as conn:
            current = conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
            current_cleaning = current["cleaning_status"] if current else "PENDING"
            current_coshh = current["coshh_status"] if current else "PENDING"
            conn.execute(
                """
                UPDATE materials
                SET status=?, cleaning_status=?, coshh_status=?, output_dir=?, error=?, updated_at=?
                WHERE id=?
                """,
                (
                    status,
                    cleaning_status or current_cleaning,
                    coshh_status or current_coshh,
                    output_dir,
                    error,
                    _now(),
                    material_id,
                ),
            )
            conn.commit()

    def get_row(self, material_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()

    def list_rows(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM materials ORDER BY id DESC"))
