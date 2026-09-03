# Material Assessments Agent

Autonomous research and draft-generation agent for **ES.SOP.272.F01.V02 - Material Hazard & Cleanability Screening Assessment**.

The agent is a **heavy-lifting research assistant**, not an approver. Every generated assessment remains a draft for manual operator review.

## Phase 1

For each queued material the agent researches identity/therapeutic context, intrinsic hazards, lowest typical daily dose, water/70% IPA/2% Decon solubility and physical cleanability. It then applies the deterministic F01 scoring rules, determines the Section 6 PDE requirement, fills the existing agent-ready Word form without redesigning it, captures supporting evidence where possible and appends labelled evidence pages to a complete draft dossier.

### PDE boundary

Phase 1 **does not search for, derive, estimate or populate a PDE/HBEL value from the internet**. Approved PDE values come from separate internal toxicologist reports. If Section 6 recommends or requires a PDE, Section 7 is left `PENDING`. If no PDE is required, the relevant Section 7 fields are populated `N/A`.

A later phase can add a local reader for the password-protected toxicologist PDE reports.

See `docs/RESEARCH_METHOD.md` for the evidence tiers and assessment rules.

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Add your OpenAI API key to `.env`. The agent uses the OpenAI Responses API with built-in web search. The default model is `gpt-5.6-terra` and can be changed with `OPENAI_MODEL`.

## Check installation

```bash
python -m agent.cli check
```

This also verifies that the repository DOCX contains the required agent-ready content-control tags.

## Run one material

```bash
python -m agent.cli assess "Haloperidol 10 mg Tablets" --dosage-form "Suspension" --route "Oral" --context "Tablets are crushed and used as the starting material for suspension manufacture"
```

## Autonomous queue

```bash
python -m agent.cli add "Levothyroxine Sodium Powder" --dosage-form "Suspension & Solution" --route "Oral"
python -m agent.cli import-csv sample_materials.csv
python -m agent.cli list
python -m agent.cli run
```

To leave it running and automatically process new items:

```bash
python -m agent.cli run --continuous --poll-seconds 60
```

Queue statuses include `PENDING`, `RESEARCHING`, `READY_FOR_REVIEW`, `PDE_RECOMMENDED`, `PDE_REQUIRED`, `EVIDENCE_GAP` and `FAILED`.

## Output

Each material receives a folder under `outputs/` containing:

- completed `F01 V02 - DRAFT.docx`;
- `Assessment Dossier - DRAFT.docx` containing the unchanged form pages followed by evidence appendices;
- optional dossier PDF when LibreOffice is installed;
- `REVIEW_SUMMARY.txt`;
- `assessment.json` with all structured research/findings;
- an `evidence/` folder with source metadata and captured source files/screenshots.

PDF sources are downloaded and the relevant page is rendered/highlighted where possible. Normal web pages are captured with Chromium/Playwright. If a source blocks automated capture or requires authentication (for example BNF), the URL and structured evidence metadata are retained and the dossier clearly marks the failed capture for manual operator access.

## Tests

```bash
pytest -q
```

The test suite covers deterministic scoring, PDE escalation rules and the agent-ready DOCX tags.

## Current limitations

- no internal PDE report processing yet;
- no password handling for PDE reports yet;
- authenticated sources may require manual evidence capture;
- Phase 1 is CLI + SQLite queue rather than a graphical dashboard.
