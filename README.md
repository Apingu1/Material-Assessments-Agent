# Material Assessments Agent

Autonomous research and draft-generation agent for two linked Eaststone workflows:

1. **ES.SOP.272.F01.V02 - Material Hazard & Cleanability Screening Assessment** for Cleaning Validation; and
2. a new **agent-generated COSHH Assessment** supported by a separately stored Safety Data Sheet (SDS).

The agent performs research and prepares draft records. It is **not an approver**. All generated records remain subject to human review, with COSHH reviewer/approver/signature/date fields intentionally left blank for physical approval.

## Combined architecture

The exact material entered by the user remains the controlled material for the Cleaning Validation assessment, but the research engine resolves endpoint-specific identities:

- clinical dose research uses the active moiety across relevant formulations and strengths;
- physicochemical/solubility research uses the actual chemical species, retaining meaningful salt/hydrate form;
- physical cleanability uses the material/process state that actually contacts equipment;
- COSHH resolves to the underlying hazardous substance while preserving the exact Eaststone material/use context.

Example:

- `Haloperidol 10 mg Tablets` remains the Cleaning Validation material name;
- clinical research uses `haloperidol` and is not restricted to the 10 mg tablet strength;
- COSHH is headed `Haloperidol`, while retaining `Haloperidol 10 mg Tablets` as the use/material context.

## Cleaning Validation assessment

For each material the agent researches:

- intrinsic toxicological hazards;
- lowest typical daily therapeutic dose;
- water solubility;
- 70% IPA solubility;
- 2% Decon cleanability/solubility;
- physical cleanability/process residue.

It applies the deterministic F01 scoring rules, fills the existing agent-ready Word form, captures concise supporting evidence and creates a draft evidence dossier.

### PDE boundary

The agent does **not** search for, derive, estimate or populate a PDE/HBEL value from the internet. Approved PDE values come from separate internal toxicologist reports. If Section 6 recommends or requires a PDE, Section 7 remains `PENDING`.

## Enhanced Decon logic

Direct solubility data in 2% Decon 90 is uncommon. The agent therefore uses a scientific evidence waterfall:

1. direct evidence in Decon 90 / 2% Decon;
2. material-specific evidence in a comparable alkaline cleaner;
3. solubility/behaviour in dilute alkali, alkaline buffer or approximately pH 10-11 conditions;
4. experimental pH-solubility data;
5. pKa/ionisation inference;
6. human review if the category cannot be justified.

The chemistry safeguard is explicit: **Decon being alkaline does not automatically mean the material becomes more soluble**. Basic compounds may become less ionised and less soluble as pH increases, while acidic compounds may behave in the opposite direction. Indirect conclusions are marked as inferred.

## BNF/NICE evidence capture

Clinical dose research still prioritises BNF/NICE and UK eMC/SmPC.

BNF research and screenshot capture are treated as separate states. A valid BNF dose result is not converted to `Unknown` merely because the website blocks automated evidence capture.

The evidence collector now gives BNF a dedicated browser-session attempt using:

- a warmed first-party BNF/NICE session;
- UK locale/timezone and browser headers;
- cookie handling;
- more tolerant matching for dose text split across DOM elements;
- scrolling around stable BNF sections such as `Indications and dose`.

If BNF still blocks capture, the scientific result remains in the research record and the canonical evidence waterfall seeks a capture-friendly authoritative corroborating source.

## COSHH assessment

COSHH is generated as a deliberately simple, visually consistent document rather than reproducing the old multi-page departmental form pack.

The normal signed draft is designed around two concise pages:

### Page 1

- substance and material/use context;
- CAS number and selected SDS;
- current GHS/CLP pictograms, signal word and H-statements;
- exposure routes;
- core controls;
- people exposed, frequency/duration and quantity/scale context.

### Page 2

- activity-specific risk/control assessment for applicable Eaststone areas;
- concise PPE/RPE requirements;
- initial and residual risk;
- first aid, spill response, storage and disposal;
- SDS traceability;
- blank human review/approval/signature/date fields.

The detailed task-level assessment remains available in `coshh_assessment.json`; the signed Word document intentionally shows only the principal workplace activities to remain easy to read and review.

### SDS-first research

The COSHH researcher seeks one strong SDS first, preferring:

1. the actual Eaststone supplier/manufacturer SDS when identifiable;
2. a manufacturer SDS for the exact chemical species/CAS;
3. a recognised major chemical supplier SDS for the exact chemical species/CAS.

A different salt/base form or mixture cannot silently substitute for the assessed substance. A non-supplier SDS is explicitly recorded as a **reference SDS** and flagged for verification before approval.

The agent also checks whether a GB Workplace Exposure Limit is identified and considers whether health surveillance may require human review.

### Original SDS handling

When an SDS PDF can be obtained, it is stored separately **byte-for-byte unchanged**. The application records:

- source URL;
- resolved PDF URL;
- manufacturer/product details;
- revision date;
- CAS number;
- supplier/reference status;
- SHA-256 hash.

The SDS is not embedded, highlighted, re-saved or altered inside the COSHH document.

## COSHH workplace/activity engine

The system separates intrinsic substance hazard from the work actually performed.

Supported areas:

- Goods In / Warehouse;
- Sampling;
- QC;
- Production;
- R&D;
- Housekeeping;
- Office.

Goods In specifically distinguishes checking/opening **outer packaging** from opening the primary material container. A hazardous powder therefore does not automatically trigger high-level respiratory PPE simply because a transit carton is opened.

Activity risk combines intrinsic hazard severity with exposure potential. PPE is task-specific and does not replace engineering controls. Where significant open powder/vapour handling is identified but the actual local engineering controls have not been supplied, the draft remains flagged for human review rather than claiming an artificially low residual risk.

## Web interface

Start the local UI:

```bash
python -m agent.cli serve --port 8000
```

The interface now separates the two outputs:

### Cleaning Validation

- F01 form;
- evidence dossier;
- PDF;
- review summary.

### COSHH

- COSHH draft DOCX;
- COSHH PDF;
- review summary;
- original SDS `View` / `Download` actions;
- COSHH JSON record.

The input screen also allows the operator to select applicable COSHH areas and supply:

- people potentially exposed;
- typical quantity/scale;
- existing engineering/containment controls;
- frequency;
- duration.

These workplace facts are not invented by the model.

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

Add your OpenAI API key to `.env`. The agent uses the OpenAI Responses API with built-in web search.

## Check installation

```bash
python -m agent.cli check
```

## Run one material

```bash
python -m agent.cli assess "Haloperidol 10 mg Tablets" \
  --dosage-form "Suspension" \
  --route "Oral" \
  --context "Tablets are crushed and used as the starting material for suspension manufacture" \
  --coshh-areas "GOODS_IN_WAREHOUSE,SAMPLING,QC,PRODUCTION" \
  --quantity "Typical dispensing quantity to be confirmed" \
  --controls "Dispensing booth / local extraction"
```

## Queue / CSV

```bash
python -m agent.cli add "Levothyroxine Sodium Powder" --dosage-form "Suspension & Solution" --route "Oral"
python -m agent.cli import-csv sample_materials.csv
python -m agent.cli list
python -m agent.cli run
```

CSV may additionally contain:

- `coshh_areas`;
- `people_exposed`;
- `typical_quantity`;
- `existing_controls`;
- `frequency`;
- `duration`.

## Output folder

Each material receives a folder under `outputs/` containing the Cleaning Validation outputs plus, where COSHH generation succeeds:

- `* - COSHH Assessment - DRAFT.docx`;
- optional COSHH PDF;
- `coshh_assessment.json`;
- `COSHH_REVIEW_SUMMARY.txt`;
- `COSHH_STATUS.json`;
- `sds/SDS_METADATA.json`;
- `sds/* - Safety Data Sheet.pdf` when the original PDF can be captured unchanged.

If COSHH generation fails, the Cleaning Validation assessment is retained and the reason is written to `COSHH_ERROR.txt`.

## Tests

```bash
pytest -q
```

The test suite covers Cleaning Validation scoring/curation plus COSHH activity rules, document generation, SDS discovery helpers and the enhanced Decon/COSHH prompts.

## Important boundary

This application automates research and preparation of **draft** GMP/COSHH records. It does not replace competent-person review, workplace verification, control validation, health-surveillance decisions or approval signatures.
