from __future__ import annotations

import json
import subprocess
import shutil
import tempfile
import threading
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .config import Settings, REPO_ROOT
from .coshh_recovery import (
    regenerate_coshh_only, refresh_existing_coshh_document,
    upload_sds_for_existing_run,
)
from .models import MaterialInput
from .pipeline import AssessmentPipeline
from .queue import MaterialQueue

COSHH_ENGINE_BUILD = "2026-10-26-controlled-v8-revised-template-site-ppe-references"
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


def _coshh_payload(output_dir: Path) -> dict:
    """Read both new and legacy COSHH records without breaking the entire queue.

    Earlier COSHH_STATUS.json files often omit stage, attempt count or even
    the status JSON altogether. Never let one record hide every assessment.
    """
    defaults = {
        "status": "FAILED",
        "sds_status": "NOT_AVAILABLE",
        "template_verified": False,
        "template": "",
        "error": "",
        "stage": "",
        "sds_attempt_count": 0,
    }
    path = output_dir / "COSHH_STATUS.json"
    if not path.is_file():
        return {**defaults, "error": "No COSHH status file is available for this assessment."}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("COSHH status must be a JSON object")
        attempt_count = payload.get("sds_attempt_count")
        try:
            attempt_count = max(0, int(attempt_count or 0))
        except (TypeError, ValueError, OverflowError):
            attempt_count = 0
        return {
            **defaults,
            "status": str(payload.get("status") or defaults["status"]),
            "sds_status": str(payload.get("sds_status") or defaults["sds_status"]),
            "template_verified": payload.get("template_verified") is True,
            "template": str(payload.get("template") or ""),
            "error": str(payload.get("error") or ""),
            "stage": str(payload.get("stage") or ""),
            "sds_attempt_count": attempt_count,
        }
    except (OSError, ValueError, TypeError) as exc:
        return {
            **defaults,
            "error": "The COSHH status record could not be read: "
                     + type(exc).__name__ + ". Existing assessment files have not been deleted.",
        }


def _coshh_status(output_dir: Path) -> str:
    return _coshh_payload(output_dir)["status"]


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


@app.get("/api/templates/coshh")
def controlled_coshh_template():
    """Download the unmodified approved COSHH template without any API calls."""
    settings = _settings()
    return FileResponse(
        settings.coshh_template_path,
        filename=settings.coshh_template_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.get("/api/version")
def version() -> dict:
    """Identify the actual code and controlled COSHH template of this running process."""
    settings = _settings()
    try:
        git_head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True, timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        git_head = "unknown"
    return {
        "commit": git_head,
        "loaded_engine_build": COSHH_ENGINE_BUILD,
        "coshh_template_path": str(settings.coshh_template_path),
        "cleaning_template_path": str(settings.template_path),
        "coshh_template": settings.coshh_template_path.name,
        "coshh_template_fields": 134,
        "legacy_coshh_renderer": False,
    }


@app.get("/api/queue")
def queue_rows() -> list[dict]:
    settings = _settings()
    queue = MaterialQueue(settings.database_path)
    result: list[dict] = []
    for row in queue.list_rows():
        payload = dict(row)
        payload["sds_status"] = "NOT_AVAILABLE"
        payload["coshh_template_verified"] = False
        payload["coshh_template"] = ""
        payload["coshh_error"] = ""
        payload["coshh_stage"] = ""
        payload["sds_attempt_count"] = 0
        payload["worker_active"] = _worker_lock.locked()
        payload["run_needs_status_check"] = (
            payload.get("status") == "RESEARCHING" and not _worker_lock.locked()
        )
        if row["output_dir"]:
            coshh = _coshh_payload(Path(row["output_dir"]).resolve())
            payload["sds_status"] = coshh.get("sds_status", "NOT_AVAILABLE")
            payload["coshh_template_verified"] = coshh.get("template_verified", False)
            payload["coshh_template"] = coshh.get("template", "")
            payload["coshh_error"] = coshh.get("error", "")
            payload["coshh_stage"] = coshh.get("stage", "")
            payload["sds_attempt_count"] = coshh.get("sds_attempt_count", 0)
            if not payload.get("coshh_status"):
                payload["coshh_status"] = coshh.get("status", "FAILED")
        result.append(payload)
    return result


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
    resolved = Path(row["output_dir"]).resolve()
    if not resolved.is_relative_to(settings.output_dir.resolve()):
        raise HTTPException(status_code=403, detail="Assessment output path is outside the configured output directory.")
    return resolved


def _match_output(material_id: int, pattern: str) -> Path:
    output_dir = _output_dir(material_id)
    matches = list(output_dir.glob(pattern))
    if not matches:
        raise HTTPException(status_code=404, detail="Requested output file is not available.")
    return matches[0]


def _recover_coshh_only(material_id: int) -> None:
    """Independent COSHH recovery; NEVER rerun the Cleaning Validation research."""
    if not _worker_lock.acquire(blocking=False):
        return
    try:
        settings = _settings()
        queue = MaterialQueue(settings.database_path)
        row = queue.get_row(material_id)
        if not row or not row["output_dir"]:
            return
        output_dir = _output_dir(material_id)
        queue.update(
            material_id, row["status"], str(output_dir), None,
            cleaning_status=row["cleaning_status"], coshh_status="RESEARCHING",
        )
        result = regenerate_coshh_only(settings, output_dir)
        queue.update(
            material_id, row["status"], str(output_dir),
            result.get("error") or None,
            cleaning_status=row["cleaning_status"],
            coshh_status=result["status"],
        )
    finally:
        _worker_lock.release()


@app.post("/api/coshh/{material_id}/retry")
def retry_coshh_only(material_id: int, background_tasks: BackgroundTasks) -> dict:
    output_dir = _output_dir(material_id)
    if not (output_dir / "assessment.json").is_file():
        raise HTTPException(
            status_code=409, detail="Saved assessment.json unavailable: cannot retry COSHH independently."
        )
    if _worker_lock.locked():
        raise HTTPException(status_code=409, detail="An assessment is already running.")
    background_tasks.add_task(_recover_coshh_only, material_id)
    return {"started": True, "scope": "COSHH_ONLY", "cleaning_validation_rerun": False}


@app.post("/api/coshh/{material_id}/refresh-form")
def refresh_coshh_form(material_id: int) -> dict:
    """Rebuild ONLY a finished Word/PDF COSHH; zero OpenAI requests."""
    if not _worker_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An assessment is already running.")
    try:
        settings = _settings()
        output_dir = _output_dir(material_id)
        try:
            status = refresh_existing_coshh_document(settings, output_dir)
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "refreshed": True,
            "ai_calls": 0,
            "template_verified": status["template_verified"],
        }
    finally:
        _worker_lock.release()


@app.post("/api/coshh/{material_id}/sds")
async def attach_sds(material_id: int, file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Attach an original PDF Safety Data Sheet.")
    output_dir = _output_dir(material_id)
    if _worker_lock.locked():
        raise HTTPException(status_code=409, detail="Wait until the current assessment finishes.")
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="SDS PDF cannot exceed 20 MB.")
    try:
        stored = upload_sds_for_existing_run(output_dir, content, file.filename)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    settings = _settings()
    queue = MaterialQueue(settings.database_path)
    row = queue.get_row(material_id)
    queue.update(
        material_id, row["status"], str(output_dir), None,
        cleaning_status=row["cleaning_status"], coshh_status="FAILED",
    )
    return {"sds_status": stored.status, "identity_match": stored.identity_match,
            "message": "SDS stored unchanged. Select 'Rebuild COSHH only' to generate the controlled form."}


@app.get("/api/coshh/{material_id}/diagnostics")
def coshh_diagnostics(material_id: int) -> dict:
    output_dir = _output_dir(material_id)
    result = _coshh_payload(output_dir)
    metadata = output_dir / "sds" / "SDS_METADATA.json"
    if metadata.is_file():
        try:
            info = json.loads(metadata.read_text(encoding="utf-8"))
            result["attempts"] = info.get("attempts") or []
            result["identity_match"] = info.get("identity_match") or ""
            result["sds_note"] = info.get("note") or ""
        except (OSError, ValueError):
            result["sds_note"] = "SDS metadata could not be read."
    return result


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
        "coshh_error": "COSHH_ERROR.txt",
    }
    pattern = patterns.get(kind)
    if not pattern:
        raise HTTPException(status_code=404, detail="Unknown download type.")
    if kind in {"coshh", "coshh_pdf"}:
        output_dir = _output_dir(material_id)
        status = _coshh_payload(output_dir)
        if not status["template_verified"]:
            detail = (
                "COSHH generation failed or has not completed; no verified document "
                "is available. " + (status.get("error") or "")
            ) if status.get("status") == "FAILED" else (
                "This COSHH document is unverified. Rebuild COSHH only to use "
                "ES.SOP.089.F01.V01."
            )
            raise HTTPException(status_code=409, detail=detail)
        from .coshh_template import verify_generated_coshh_document
        docx_files = list(output_dir.glob("*COSHH Assessment - DRAFT.docx"))
        if len(docx_files) != 1:
            raise HTTPException(status_code=409, detail="Ambiguous or missing controlled COSHH document.")
        try:
            verify_generated_coshh_document(docx_files[0], _settings().coshh_template_path)
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=409, detail=f"Controlled COSHH form verification failed: {exc}") from exc
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
<div class="top"><div><h1>Material Assessment Agent</h1><div class="muted">One research run. Separate Cleaning Validation and COSHH draft outputs.</div><div class="muted" id="build-status">Verifying running COSHH version…</div><div class="muted"><a href="/api/templates/coshh">View controlled COSHH master template (no AI cost)</a></div></div><div class="muted">All generated records require human review.</div></div>
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
async function runAll(){
 try {
  const r=await fetch('/api/run',{method:'POST'});
  if(!r.ok)throw new Error('HTTP '+r.status+': '+(await r.text()).slice(0,150));
  const data=await r.json();
  note(data.started?'Run request accepted. Check queue status below; an accepted request does not confirm completion.':'No run started: '+(data.detail||'worker already active'));
 } catch(e) {note('Unable to start assessment: '+e.message);}
 setTimeout(refresh,1000);
}
async function uploadCsv(){const f=document.getElementById('csv').files[0];if(!f)return;const fd=new FormData();fd.append('file',f);const r=await fetch('/api/import-csv',{method:'POST',body:fd});const x=await r.json();note(r.ok?`${x.imported} material(s) imported.`:(x.detail||'Import failed.'));await refresh()}
function cleaning(row){if(!row.output_dir)return `<span class="pill">${esc(row.cleaning_status||row.status)}</span>`;const b=`/api/download/${row.id}/`;return `<div class="status">${esc(row.cleaning_status||row.status)}</div><span class="links"><a href="${b}form">Form</a><a href="${b}dossier">Dossier</a><a href="${b}pdf">PDF</a><a href="${b}summary">Summary</a></span>`}
function coshh(row){
if(!row.output_dir)return `<span class="pill">${esc(row.coshh_status||'PENDING')}</span>`;
const b=`/api/download/${row.id}/`;const verified=row.coshh_template_verified;
let links=verified?`<a href="${b}coshh">Controlled COSHH V01</a><a href="${b}coshh_pdf">PDF</a><a href="${b}coshh_summary">Summary</a><button class="secondary" style="padding:5px 8px;font-size:11px" onclick="refreshCoshhForm(${row.id})">Refresh form (no AI)</button>`:'';
if(!verified && row.coshh_status==='FAILED'){
 links+=`<div class="error">COSHH not generated: ${esc(row.coshh_error||'Review diagnostics')}</div>`;
}
links+=`<a href="/api/coshh/${row.id}/diagnostics" target="_blank">Error / SDS diagnostics</a>`;
if(row.sds_status==='STORED_UNCHANGED'){
links+=`<a href="/api/view/${row.id}/sds" target="_blank">View SDS</a><a href="${b}sds">Download SDS</a>`;
}
if(!verified && row.coshh_status!=='RESEARCHING'){
links+=`<button class="secondary" style="padding:5px 8px;font-size:11px" onclick="retryCoshh(${row.id})">Rebuild COSHH only</button>`;
}
links+=`<label class="filebtn secondary" style="padding:5px 8px;font-size:11px">Attach SDS PDF<input type="file" accept=".pdf,application/pdf" onchange="uploadSds(${row.id},this)"></label>`;
return `<div class="status">${esc(row.coshh_status||'')}</div><div class="muted">SDS: ${esc(row.sds_status||'NOT_AVAILABLE')}</div><span class="links">${links}</span>`;
}
async function refreshCoshhForm(id){
 if(!confirm('Refresh COSHH from previously saved hazard data and SDS? The existing Word/PDF will be replaced, but Cleaning Validation and SDS research will NOT rerun. AI calls: 0.'))return;
 try{
  const response=await fetch('/api/coshh/'+id+'/refresh-form',{method:'POST'});
  const result=await response.json();
  if(!response.ok)throw Error(result.detail||'COSHH form refresh failed');
  note('COSHH form refreshed with corrected hazard pictograms and full-size PPE checkboxes. AI calls: 0. Please download the new Word/PDF.');
 }catch(error){note('Unable to refresh COSHH: '+error.message);}
 await refresh();
}
async function retryCoshh(id){
 if(!confirm('Rebuild COSHH from saved Cleaning Validation research and an SDS PDF? No Cleaning Validation re-run. If an SDS exists, one COSHH PDF-extraction AI call may be billed.'))return;
 const r=await fetch('/api/coshh/'+id+'/retry',{method:'POST'});
 const x=await r.json();note(r.ok?'COSHH-only rebuild started. Cleaning Validation will NOT rerun.':(x.detail||'COSHH retry failed.'));
 await refresh();
}
async function uploadSds(id, input){
 const f=input.files[0];if(!f)return;
 const form=new FormData();form.append('file',f);
 const r=await fetch('/api/coshh/'+id+'/sds',{method:'POST',body:form});
 const x=await r.json();note(r.ok?'SDS PDF saved unchanged. Click Rebuild COSHH only to extract and populate the form.':(x.detail||'SDS upload rejected.'));
 await refresh();
}
async function refresh(){
const body=document.getElementById('rows');
try{
 const response=await fetch('/api/queue',{cache:'no-store'});
 if(!response.ok){throw new Error('HTTP '+response.status+' '+(await response.text()).slice(0,200))}
 const data=await response.json();
 if(!Array.isArray(data))throw new Error('Unexpected queue response');
 body.innerHTML=data.map(x=>{
   const warning=x.run_needs_status_check?'<div class="error">Previously marked RESEARCHING; no web worker currently detected. Check the saved record before starting another paid run.</div>':'';
   return `<tr><td>${x.id}</td><td><div class="output-title">${esc(x.material_name)}</div><span class="muted">${esc(x.coshh_areas||'')}</span>${warning}</td><td>${cleaning(x)}</td><td>${coshh(x)}</td><td class="error">${esc(x.error||'')}</td></tr>`;
 }).join('')||'<tr><td colspan="5" class="muted">No assessments have been added to this queue database.</td></tr>';
}catch(error){
 body.innerHTML='<tr><td colspan="5" class="error">Assessment queue could not be loaded ('+esc(String(error.message))+'). This does not mean prior records have been deleted. Review server diagnostics; do not submit another paid run solely to restore the list.</td></tr>';
}
}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[c]))}
async function showBuild(){const e=document.getElementById('build-status');try{const r=await fetch('/api/version',{cache:'no-store'});if(!r.ok)throw Error('version endpoint unavailable');const v=await r.json();e.textContent='COSHH: '+v.coshh_template+' ('+v.coshh_template_fields+' fields) | Loaded engine: '+(v.loaded_engine_build||'legacy')+' | Repository: '+v.commit;}catch(e){document.getElementById('build-status').textContent='COSHH version could not be verified — restart the Codespaces web server after pulling the branch.';}}
showBuild();refresh();setInterval(refresh,5000);
</script></body></html>'''
