# Material Assessments Agent

Autonomous research and draft-generation agent for **ES.SOP.272.F01.V02 - Material Hazard & Cleanability Screening Assessment**.

The agent is a heavy-lifting research assistant, not an approver. Every generated assessment remains a draft for manual operator review.

## Current phase

For each material the agent researches identity/therapeutic context, intrinsic hazards, lowest typical daily dose, water/70% IPA/2% Decon solubility and physical cleanability. It applies the deterministic F01 scoring rules, determines the Section 6 PDE requirement, fills the existing agent-ready Word form without redesigning it, captures supporting evidence where possible and builds a draft dossier.

### PDE boundary

The agent does **not** search for, derive, estimate or populate a PDE/HBEL value from the internet. Approved PDE values come from separate internal toxicologist reports. If Section 6 recommends or requires a PDE, Section 7 is left `PENDING`. If no PDE is required, the relevant Section 7 fields are populated `N/A`.

A later phase can add a local reader for the password-protected toxicologist PDE reports.

See `docs/RESEARCH_METHOD.md` for the hardened evidence tiers and assessment rules.

## Evidence hardening

The current research method uses three source tiers. UK evidence is preferred where equivalent evidence exists. BNF/NICE and eMC are the primary dose sources. British/European Pharmacopoeia, PubChem and PubMed/PMC are Tier 1. DrugBank is Tier 2.

Hazard research is deliberately adversarial: the agent searches regulatory evidence, PubChem/ECHA/official toxicology sources and PubMed/PMC literature, and searches both positive and negative evidence. Credible Tier 1 positive hazard evidence is conservatively selected for scoring even when another Tier 1 source is reassuring; the evidence is then labelled conflicting for operator review.

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

Linux / GitHub Codespaces:

```bash
source .venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium
cp .env.example .env
```

The `--with-deps` option is important in Codespaces because Chromium requires Linux system libraries such as ATK.

Add your OpenAI API key to `.env`. The agent uses the OpenAI Responses API with built-in web search.

## Check installation

```bash
python -m agent.cli check
```

## Minimal web interface

Start the local UI:

```bash
python -m agent.cli serve --port 8000
```

In Codespaces, open the forwarded port 8000. The UI provides:

- Material / API input with the 55-character Section 1 limit;
- dosage form, route and manufacturing context;
- Add to Queue / Add & Run / Run Pending;
- CSV import;
- live queue status;
- links to generated F01, dossier, PDF, summary and JSON outputs.

Manufacturing context is used by the research engine but is not appended to the Material/API Name field.

## Run one material from CLI

```bash
python -m agent.cli assess "Haloperidol 10 mg Tablets" \
  --dosage-form "Suspension" \
  --route "Oral" \
  --context "Tablets are crushed and used as the starting material for suspension manufacture"
```

## Autonomous queue

```bash
python -m agent.cli add "Levothyroxine Sodium Powder" --dosage-form "Suspension & Solution" --route "Oral"
python -m agent.cli import-csv sample_materials.csv
python -m agent.cli list
python -m agent.cli run
```

To leave it running:

```bash
python -m agent.cli run --continuous --poll-seconds 60
```

Queue statuses include `PENDING`, `RESEARCHING`, `READY_FOR_REVIEW`, `PDE_RECOMMENDED`, `PDE_REQUIRED`, `EVIDENCE_GAP` and `FAILED`.

## Output

Each material receives a folder under `outputs/` containing:

- completed `F01 V02 - DRAFT.docx`;
- `Assessment Dossier - DRAFT.docx` with the unchanged form followed by evidence appendices;
- optional dossier PDF when LibreOffice is installed;
- `REVIEW_SUMMARY.txt`;
- `assessment.json`;
- an `evidence/` folder with source metadata, source files/screenshots and technical diagnostic logs where needed.

Appendix text is Arial. Evidence pages use `Interpretation` rather than `Agent interpretation`. Browser/Playwright diagnostics are never inserted into the dossier.

PDF evidence capture no longer falls back to a random first page: if the relevant evidence page cannot be located by exact/fuzzy matching, the PDF is retained and the dossier states that manual page review is required.

## Tests

```bash
pytest -q
```

## Current limitations

- no internal PDE report processing yet;
- no password handling for PDE reports yet;
- authenticated sources such as BNF may still require manual evidence capture;
- web UI is intentionally minimalist rather than a full application dashboard.
