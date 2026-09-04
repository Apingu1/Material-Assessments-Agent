# Material Assessments Agent

Autonomous research and draft-generation agent for **ES.SOP.272.F01.V02 - Material Hazard & Cleanability Screening Assessment**.

The agent is a heavy-lifting research assistant, not an approver. Every generated assessment remains a draft for manual operator review.

## Current phase

For each material the agent researches identity/therapeutic context, intrinsic hazards, lowest typical daily dose, water/70% IPA/2% Decon solubility and physical cleanability. It applies the deterministic F01 scoring rules, determines the Section 6 PDE requirement, fills the existing agent-ready Word form without redesigning it, captures supporting evidence where possible and builds a draft dossier.

### PDE boundary

The agent does **not** search for, derive, estimate or populate a PDE/HBEL value from the internet. Approved PDE values come from separate internal toxicologist reports. If Section 6 recommends or requires a PDE, Section 7 is left `PENDING`. If no PDE is required, the relevant Section 7 fields are populated `N/A`.

A later phase can add a local reader for the password-protected toxicologist PDE reports.

See `docs/RESEARCH_METHOD.md` for the hardened evidence tiers and assessment rules.

## Evidence hardening and curation

The research method uses three internal source tiers. UK evidence is preferred where equivalent evidence exists. BNF/NICE and eMC are the primary dose sources. British/European Pharmacopoeia, PubChem and PubMed/PMC are Tier 1. DrugBank is Tier 2.

Hazard research is deliberately adversarial: the agent searches regulatory evidence, PubChem/ECHA/official toxicology sources and PubMed/PMC literature, and searches both positive and negative evidence. Credible Tier 1 positive hazard evidence is conservatively selected for scoring even when another Tier 1 source is reassuring; the evidence is then labelled conflicting internally for operator review.

Research can remain broad, but the generated dossier is deliberately concise. Only the strongest, decision-relevant evidence that was successfully verified and captured is appended. Repetitive corroborating sources remain available in `assessment.json` instead of inflating the controlled dossier.

For 2% Decon, the research question is specifically the assessed material's solubility/behaviour in Decon 90. Decon product composition, surfactants, dilution instructions and cleaner advertising are not admissible evidence of material solubility. If direct material-in-Decon evidence is unavailable, the agent uses documented material behaviour in relevant solvents to support a clearly labelled inference or flags review.

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

In Codespaces, open the forwarded port 8000. The UI provides material/API input, dosage form, route, manufacturing context, queue controls, CSV import, live status and links to generated files.

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
- `Assessment Dossier - DRAFT.docx` with the unchanged form followed by curated evidence appendices;
- optional dossier PDF when LibreOffice is installed;
- `REVIEW_SUMMARY.txt`;
- `assessment.json` containing the full research pool;
- an `evidence/` folder containing the selected evidence, source metadata, appendix-selection metadata and technical diagnostics where needed.

The visible appendix is intentionally simple and human-readable. It contains only **Source**, **URL**, **Relevant finding**, **Interpretation** and **Evidence** followed by the verified screenshot/source page. Source tier, publisher, capture status, capture notes and hosting-site commentary are not printed in the dossier.

Appendix text is Arial. Blocked, 403, 404, irrelevant or unverified screenshots are not appended. PubMed uses an official NCBI text fallback when the normal webpage blocks browser capture. PDF evidence is appended only when the relevant page can be located by exact/fuzzy matching; a random first page is never substituted.

Exact repeated evidence is cross-referenced instead of appended twice, and the appendix image is scaled to keep most evidence items on a single page.

## Tests

```bash
pytest -q
```

## Current limitations

- no internal PDE report processing yet;
- no password handling for PDE reports yet;
- authenticated sources such as BNF may still require manual evidence capture;
- web UI is intentionally minimalist rather than a full application dashboard.
