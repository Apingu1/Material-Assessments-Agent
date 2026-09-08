from __future__ import annotations

import json
import shutil
import tempfile
import threading
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .config import Settings
from .models import MaterialInput
from .pipeline import AssessmentPipeline
from .queue import MaterialQueue

app = FastAPI(title="Material Assessment Agent")
_worker_lock = threading.Lock()


def _settings() -> Settings:
    settings = Settings.load()
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
    if not path.exists():
        return "FAILED"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return str(payload.get("status") or "FAILED")
    except Exception:
        return "FAILED"


def _process_pending() -> None:
    if not _worker_lock.acquire(blocking=False):
        return
    try:
        settings = _settings()
        queue = MaterialQueue(settings.database_path)
        pipeline = AssessmentPipeline(settings)
        while True:
            claimed = queue.claim_next()
            if not claimed:
                break
            material_id, item = claimed
            try:
                bundle, output_dir = pipeline.run(item)
                cleaning = _final_status(bundle)
                coshh = _coshh_status(output_dir)
                queue.update(
                    material_id,
                    cleaning,
                    str(output_dir),
                    None,
                    cleaning_status=cleaning,
                    coshh_status=coshh,
                )
            except Exception as exc:
                queue.update(
                    material_id,
                    "FAILED",
                    None,
                    str(exc)[:1200],
                    cleaning_status="FAILED",
                    coshh_status="FAILED",
                )
    finally:
        _worker_lock.release()


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return HTML


@app.get("/api/queue")
def queue_rows() -> list[dict]:
    settings = _settings()
    queue = MaterialQueue(settings.database_path)
    return [dict(row) for row in queue.list_rows()]


@app.post("/api/materials")
def add_material(item: MaterialInput) -> dict:
    settings = _settings()
    queue = MaterialQueue(settings.database_path)
    material_id = queue.add(item)
    return {"id": material_id, "status": "PENDING"}


@app.post("/api/run")
def run_pending(background_tasks: BackgroundTasks) -> dict:
    background_tasks.add_task(_process_pending)
    return {"started": True}


@app.post("/api/import-csv")
def import_csv(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")
    settings = _settings()
    queue = MaterialQueue(settings.database_path)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = Path(tmp.name)
    try:
        count = queue.import_csv(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return {"imported": count}


def _output_dir(material_id: int) -> Path:
    settings = _settings()
    queue = MaterialQueue(settings.database_path)
    row = queue.get_row(material_id)
    if not row or not row["output_dir"]:
        raise HTTPException(status_code=404, detail="Output is not available yet.")
    return Path(row["output_dir"]).resolve()


def _match_output(material_id: int, pattern: str) -> Path:
    output_dir = _output_dir(material_id)
    matches = list(output_dir.glob(pattern))
    if not matches:
        raise HTTPException(status_code=404, detail="Requested output file is not available.")
    return matches[0]


@app.get("/api/download/{material_id}/{kind}")
def download(material_id: int, kind: str):
    patterns = {
        "form": "*F01 V02 - DRAFT.docx",
        "dossier": "*Assessment Dossier - DRAFT.docx",
        "pdf": "*Assessment Dossier - DRAFT.pdf",
        "summary": "REVIEW_SUMMARY.txt",
        "json": "assessment.json",
        "coshh": "*COSHH Assessment - DRAFT.docx",
        "coshh_pdf": "*COSHH Assessment - DRAFT.pdf",
        "coshh_summary": "COSHH_REVIEW_SUMMARY.txt",
        "coshh_json": "coshh_assessment.json",
        "sds": "sds/*Safety Data Sheet.pdf",
        "sds_meta": "sds/SDS_METADATA.json",
    }
    pattern = patterns.get(kind)
    if not pattern:
        raise HTTPException(status_code=404, detail="Unknown download type.")
    path = _match_output(material_id, pattern)
    return FileResponse(path, filename=path.name)


@app.get("/api/view/{material_id}/sds")
def view_sds(material_id: int):
    path = _match_output(material_id, "sds/*Safety Data Sheet.pdf")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Material Assessment Agent</title>
<style>
:root{font-family:Arial,sans-serif;color:#17202a;background:#f3f6f8;--navy:#17365d;--teal:#2b8795;--line:#d9e2e8}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1240px;margin:30px auto;padding:0 20px}.top{display:flex;align-items:end;justify-content:space-between;margin-bottom:18px}h1{font-size:27px;margin:0;color:var(--navy)}.muted{color:#667085;font-size:13px}.card{background:#fff;border:1px solid #e4e7ec;border-radius:14px;padding:20px;margin-bottom:18px;box-shadow:0 3px 12px rgba(16,24,40,.05)}.grid{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px}.full{grid-column:1/-1}.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}label{display:block;font-size:12px;font-weight:700;margin-bottom:6px;color:#344054}input,textarea,select{width:100%;border:1px solid #d0d5dd;border-radius:8px;padding:10px 11px;font:inherit;background:#fff}textarea{height:72px;resize:vertical}.count{font-size:11px;color:#667085;text-align:right;margin-top:3px}.actions{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}button,.filebtn{border:0;border-radius:8px;padding:10px 14px;font-weight:700;cursor:pointer;background:var(--navy);color:white}.secondary{background:#eef3f6;color:var(--navy)}.filebtn{display:inline-block}.filebtn input{display:none}.subhead{font-size:13px;font-weight:800;color:var(--navy);margin:18px 0 10px;border-top:1px solid #edf1f3;padding-top:14px}.areas{display:flex;gap:8px;flex-wrap:wrap}.area{border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:#fafcfd;font-size:12px}.area input{width:auto;margin-right:5px}table{width:100%;border-collapse:collapse;font-size:12.5px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #eaecf0;vertical-align:top}th{color:#667085;font-size:10.5px;text-transform:uppercase}.status{font-weight:800;color:var(--navy)}.links a{display:inline-block;margin:2px 8px 2px 0;color:#175cd3;text-decoration:none}.error{color:#b42318;max-width:260px}.notice{font-size:13px;margin-top:10px;color:#475467}.output-title{font-weight:800;color:#344054;margin-bottom:3px}.pill{display:inline-block;border-radius:99px;background:#eef3f6;padding:3px 7px;font-size:10px;font-weight:800;margin-bottom:4px}@media(max-width:800px){.grid,.two{grid-template-columns:1fr}.top{display:block}.top .muted{margin-top:6px}table{display:block;overflow:auto}}
</style>
</head>
<body><div class="wrap">
<div class="top"><div><h1>Material Assessment Agent</h1><div class="muted">One research run. Separate Cleaning Validation and COSHH draft outputs.</div></div><div class="muted">All generated records require human review.</div></div>
<div class="card"><div class="grid">
<div><label>Material / API Name</label><input id="material" maxlength="55" placeholder="Haloperidol 10 mg Tablets"><div class="count"><span id="mc">0</span>/55</div></div>
<div><label>Dosage Form</label><input id="dosage" maxlength="55" placeholder="Suspension"></div>
<div><label>Route</label><input id="route" maxlength="55" placeholder="Oral"></div>
<div class="full"><label>Manufacturing Context</label><textarea id="context" placeholder="e.g. Tablets are crushed and used as starting material for suspension manufacture"></textarea></div>
</div>
<div class="subhead">COSHH - applicable areas</div>
<div class="areas" id="areas">
<label class="area"><input type="checkbox" value="GOODS_IN_WAREHOUSE" checked>Goods In / Warehouse</label>
<label class="area"><input type="checkbox" value="SAMPLING" checked>Sampling</label>
<label class="area"><input type="checkbox" value="QC" checked>QC</label>
<label class="area"><input type="checkbox" value="PRODUCTION" checked>Production</label>
<label class="area"><input type="checkbox" value="R_AND_D">R&D</label>
<label class="area"><input type="checkbox" value="HOUSEKEEPING">Housekeeping</label>
<label class="area"><input type="checkbox" value="OFFICE">Office</label>
</div>
<div class="two" style="margin-top:12px">
<div><label>People potentially exposed</label><input id="people" value="Production, QC, Sampling and Warehouse personnel as applicable"></div>
<div><label>Typical quantity / scale</label><input id="quantity" placeholder="Optional - reviewer can confirm"></div>
<div><label>Existing engineering / containment controls</label><input id="controls" placeholder="e.g. dispensing booth / LEV / fume cupboard"></div>
<div class="two"><div><label>Frequency</label><input id="frequency" value="Infrequent"></div><div><label>Duration</label><input id="duration" value="<30 mins"></div></div>
</div>
<div class="actions"><button onclick="add(false)">Add to Queue</button><button onclick="add(true)">Add & Run</button><button class="secondary" onclick="runAll()">Run Pending</button><label class="filebtn secondary">Import CSV<input id="csv" type="file" accept=".csv" onchange="uploadCsv()"></label></div><div id="notice" class="notice"></div></div>
<div class="card"><div style="display:flex;justify-content:space-between;align-items:center"><strong>Assessment Queue</strong><button class="secondary" onclick="refresh()">Refresh</button></div><div style="overflow:auto"><table><thead><tr><th>ID</th><th>Material</th><th>Cleaning Validation</th><th>COSHH</th><th>Issue</th></tr></thead><tbody id="rows"></tbody></table></div></div>
</div>
<script>
const m=document.getElementById('material');m.addEventListener('input',()=>document.getElementById('mc').textContent=m.value.length);
function note(t){document.getElementById('notice').textContent=t}
function areas(){return [...document.querySelectorAll('#areas input:checked')].map(x=>x.value)}
async function add(run){const body={material_name:m.value.trim(),dosage_forms:document.getElementById('dosage').value.trim(),routes:document.getElementById('route').value.trim(),product_context:document.getElementById('context').value.trim(),coshh_areas:areas(),people_exposed:document.getElementById('people').value.trim(),typical_quantity:document.getElementById('quantity').value.trim(),existing_controls:document.getElementById('controls').value.trim(),frequency:document.getElementById('frequency').value.trim(),duration:document.getElementById('duration').value.trim()};if(!body.material_name){note('Enter a material name.');return}if(!body.coshh_areas.length){note('Select at least one COSHH area.');return}const r=await fetch('/api/materials',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok){note('Could not add material: '+await r.text());return}note('Material added to queue.');if(run)await runAll();await refresh()}
async function runAll(){await fetch('/api/run',{method:'POST'});note('Pending assessments are being processed.');setTimeout(refresh,1000)}
async function uploadCsv(){const f=document.getElementById('csv').files[0];if(!f)return;const fd=new FormData();fd.append('file',f);const r=await fetch('/api/import-csv',{method:'POST',body:fd});const x=await r.json();note(r.ok?`${x.imported} material(s) imported.`:(x.detail||'Import failed.'));await refresh()}
function cleaning(row){if(!row.output_dir)return `<span class="pill">${esc(row.cleaning_status||row.status)}</span>`;const b=`/api/download/${row.id}/`;return `<div class="status">${esc(row.cleaning_status||row.status)}</div><span class="links"><a href="${b}form">Form</a><a href="${b}dossier">Dossier</a><a href="${b}pdf">PDF</a><a href="${b}summary">Summary</a></span>`}
function coshh(row){if(!row.output_dir)return `<span class="pill">${esc(row.coshh_status||'PENDING')}</span>`;const b=`/api/download/${row.id}/`;let links=`<a href="${b}coshh">COSHH</a><a href="${b}coshh_pdf">PDF</a><a href="${b}coshh_summary">Summary</a>`;if(row.coshh_status!=='FAILED')links+=`<a href="/api/view/${row.id}/sds" target="_blank">View SDS</a><a href="${b}sds">Download SDS</a>`;return `<div class="status">${esc(row.coshh_status||'')}</div><span class="links">${links}</span>`}
async function refresh(){const r=await fetch('/api/queue');const data=await r.json();document.getElementById('rows').innerHTML=data.map(x=>`<tr><td>${x.id}</td><td><div class="output-title">${esc(x.material_name)}</div><span class="muted">${esc(x.coshh_areas||'')}</span></td><td>${cleaning(x)}</td><td>${coshh(x)}</td><td class="error">${esc(x.error||'')}</td></tr>`).join('')||'<tr><td colspan="5" class="muted">Queue is empty.</td></tr>'}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
refresh();setInterval(refresh,5000);
</script></body></html>'''
