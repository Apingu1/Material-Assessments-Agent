from __future__ import annotations

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
                queue.update(material_id, _final_status(bundle), str(output_dir), None)
            except Exception as exc:
                queue.update(material_id, "FAILED", None, str(exc)[:1200])
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


@app.get("/api/download/{material_id}/{kind}")
def download(material_id: int, kind: str):
    settings = _settings()
    queue = MaterialQueue(settings.database_path)
    row = queue.get_row(material_id)
    if not row or not row["output_dir"]:
        raise HTTPException(status_code=404, detail="Output is not available yet.")
    output_dir = Path(row["output_dir"]).resolve()
    patterns = {
        "form": "*F01 V02 - DRAFT.docx",
        "dossier": "*Assessment Dossier - DRAFT.docx",
        "pdf": "*Assessment Dossier - DRAFT.pdf",
        "summary": "REVIEW_SUMMARY.txt",
        "json": "assessment.json",
    }
    pattern = patterns.get(kind)
    if not pattern:
        raise HTTPException(status_code=404, detail="Unknown download type.")
    matches = list(output_dir.glob(pattern))
    if not matches:
        raise HTTPException(status_code=404, detail="Requested output file is not available.")
    return FileResponse(matches[0], filename=matches[0].name)


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Material Assessment Agent</title>
<style>
:root{font-family:Arial,sans-serif;color:#17202a;background:#f5f7f9}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1120px;margin:38px auto;padding:0 20px}.top{display:flex;align-items:end;justify-content:space-between;margin-bottom:22px}h1{font-size:26px;margin:0}.muted{color:#667085;font-size:13px}.card{background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:20px;margin-bottom:18px;box-shadow:0 2px 8px rgba(16,24,40,.04)}.grid{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px}.full{grid-column:1/-1}label{display:block;font-size:12px;font-weight:700;margin-bottom:6px}input,textarea{width:100%;border:1px solid #d0d5dd;border-radius:8px;padding:10px 11px;font:inherit;background:#fff}textarea{height:76px;resize:vertical}.count{font-size:11px;color:#667085;text-align:right;margin-top:3px}.actions{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}button,.filebtn{border:0;border-radius:8px;padding:10px 14px;font-weight:700;cursor:pointer;background:#17202a;color:white}.secondary{background:#eef2f6;color:#17202a}.filebtn{display:inline-block}.filebtn input{display:none}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #eaecf0;vertical-align:top}th{color:#667085;font-size:11px;text-transform:uppercase}.status{font-weight:700}.links a{margin-right:8px;color:#175cd3;text-decoration:none}.error{color:#b42318;max-width:300px}.notice{font-size:13px;margin-top:10px;color:#475467}@media(max-width:760px){.grid{grid-template-columns:1fr}.top{display:block}.top .muted{margin-top:6px}table{display:block;overflow:auto}}
</style>
</head>
<body><div class="wrap">
<div class="top"><div><h1>Material Assessment Agent</h1><div class="muted">Research, draft F01 completion and evidence dossier generation.</div></div><div class="muted">All outputs require operator review.</div></div>
<div class="card"><div class="grid">
<div><label>Material / API Name</label><input id="material" maxlength="55" placeholder="Haloperidol 10 mg Tablets"><div class="count"><span id="mc">0</span>/55</div></div>
<div><label>Dosage Form</label><input id="dosage" maxlength="55" placeholder="Suspension"></div>
<div><label>Route</label><input id="route" maxlength="55" placeholder="Oral"></div>
<div class="full"><label>Manufacturing Context</label><textarea id="context" placeholder="Optional process context. This is used for research but is not added to the Material / API Name box."></textarea></div>
</div><div class="actions"><button onclick="add(false)">Add to Queue</button><button onclick="add(true)">Add & Run</button><button class="secondary" onclick="runAll()">Run Pending</button><label class="filebtn secondary">Import CSV<input id="csv" type="file" accept=".csv" onchange="uploadCsv()"></label></div><div id="notice" class="notice"></div></div>
<div class="card"><div style="display:flex;justify-content:space-between;align-items:center"><strong>Assessment Queue</strong><button class="secondary" onclick="refresh()">Refresh</button></div><div style="overflow:auto"><table><thead><tr><th>ID</th><th>Material</th><th>Status</th><th>Output</th><th>Issue</th></tr></thead><tbody id="rows"></tbody></table></div></div>
</div>
<script>
const m=document.getElementById('material');m.addEventListener('input',()=>document.getElementById('mc').textContent=m.value.length);
function note(t){document.getElementById('notice').textContent=t}
async function add(run){const body={material_name:m.value.trim(),dosage_forms:document.getElementById('dosage').value.trim(),routes:document.getElementById('route').value.trim(),product_context:document.getElementById('context').value.trim()};if(!body.material_name){note('Enter a material name.');return}const r=await fetch('/api/materials',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok){note('Could not add material: '+await r.text());return}note('Material added to queue.');if(run)await runAll();await refresh()}
async function runAll(){await fetch('/api/run',{method:'POST'});note('Pending assessments are being processed.');setTimeout(refresh,1000)}
async function uploadCsv(){const f=document.getElementById('csv').files[0];if(!f)return;const fd=new FormData();fd.append('file',f);const r=await fetch('/api/import-csv',{method:'POST',body:fd});const x=await r.json();note(r.ok?`${x.imported} material(s) imported.`:(x.detail||'Import failed.'));await refresh()}
function links(row){if(!row.output_dir)return '';const b=`/api/download/${row.id}/`;return `<span class="links"><a href="${b}form">Form</a><a href="${b}dossier">Dossier</a><a href="${b}pdf">PDF</a><a href="${b}summary">Summary</a></span>`}
async function refresh(){const r=await fetch('/api/queue');const data=await r.json();document.getElementById('rows').innerHTML=data.map(x=>`<tr><td>${x.id}</td><td>${esc(x.material_name)}</td><td class="status">${esc(x.status)}</td><td>${links(x)}</td><td class="error">${esc(x.error||'')}</td></tr>`).join('')||'<tr><td colspan="5" class="muted">Queue is empty.</td></tr>'}
function esc(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
refresh();setInterval(refresh,5000);
</script></body></html>'''
