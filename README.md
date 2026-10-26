# Material Assessments Agent

Autonomous research and draft-generation agent for two linked Eaststone workflows:

1. **ES.SOP.272.F01.V02 - Material Hazard & Cleanability Screening Assessment** for Cleaning Validation; and
2. **ES.SOP.089.F01.V01 COSHH Assessment** in the controlled Word layout, supported by a separately stored Safety Data Sheet (SDS).

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

The COSHH module now populates Eaststone's approved-layout **ES.SOP.089.F01.V01 – COSHH Assessment** DOCX template rather than drawing its own standalone form. The template is a controlled, three-page form with 134 individually tagged fields and checkboxes. The immutable template resource lives at `templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx`; source document headers, hazard pictograms, PPE matrix, section structure, and human sign-off areas are retained.

### Page 1

- substance/product identity, CAS, process/use context and applicable personnel;
- SDS details and current GB CLP pictogram selections;
- H-code/statement wording and relevant health effects;
- exposure routes and average exposure duration;
- first aid and spill/environmental response.

### Page 2

- departmental PPE matrix;
- three concise task/activity assessment rows (full detailed assessment remains in `coshh_assessment.json`);
- risk ratings, exposure monitoring and health-surveillance considerations;
- storage and disposal.

### Page 3

- conditions/restrictions, next review date and communication record;
- blank human assessment, review and approval names, signatures and dates.

The agent writes only tagged fields and preserves the template's page structure. It does not sign, approve or confirm control adequacy on behalf of an Eaststone reviewer.

### No-credit refresh of an existing COSHH document

After code updates, a completed assessment's saved `coshh_assessment.json`
and original SDS PDF can be reused using **Refresh form (no AI)**. This
repopulates the same controlled Word form and optional PDF using the already
saved H-statements and workplace logic. It does not re-contact OpenAI,
re-research Cleaning Validation or change the saved SDS/research JSON; it
verifies the new Word package before replacing the previous file.
No-AI refresh is deliberately blocked when no H-statements or original
SDS were saved, to prevent unjustified automatic pictogram classifications.

### Pictogram and checkbox fidelity

The generator retains every controlled Word checkbox's original formatted run.
In particular, the approved PPE matrix has 20 pt checkbox glyphs (Word
`w:sz=40`), not the smaller 10 pt glyphs used for other fields. Only the
checked state and visible glyph are changed.

The Safety Data Sheet may encode its GHS diamonds as **images**, so a
text-extraction research model can return `pictograms=[]` despite Section 2
listing classified H-statements. The COSHH renderer therefore cross-checks
explicit pictograms against the classified H-codes in SDS-derived hazard
statements before ticking the controlled hazard boxes. It applies CLP skull /
exclamation precedence and does not infer the environmental pictogram from
H412 or H413 alone. The SDS and the resulting selections remain subject to
competent-person review. For Levomepromazine Maleate, the official British
Pharmacopoeia SDS (26 August 2026) reports H302, H317, H319 and H336, thus
GHS07 is selected even if its PDF-embedded pictogram was not identified by
text extraction.

### SDS-first research

The COSHH researcher seeks one strong SDS first, preferring:

1. the actual Eaststone supplier/manufacturer SDS when identifiable;
2. a manufacturer SDS for the exact chemical species/CAS;
3. a recognised major chemical supplier SDS for the exact chemical species/CAS.

A different salt/base form or mixture cannot silently substitute for the assessed substance. A non-supplier SDS is explicitly recorded as a **reference SDS** and flagged for verification before approval.

SDS searching strips incoming presentations (e.g. "Powder", "Tablets", dose, "Oral") and prioritises the actual chemical/salt, with the base moiety as a flagged reference option. A confirmed British Pharmacopoeia/MHRA Levomepromazine Maleate reference SDS (CAS 7104-38-3) is checked by direct HTTP **before any paid COSHH research**. If it is blocked, supplier SDS links and embedded viewers are attempted, followed by a cost-limited manufacturer/distributor research pass (`COSHH_MAX_RESCUE_SEARCHES=1` by default). When a substitute SDS is downloaded, the agent re-extracts the hazard package from the saved PDF itself before producing a COSHH document. Each alternative search regenerates the COSHH research from its newly selected SDS rather than mixing suppliers' hazard statements. The record includes every attempted URL and its failure reason in `sds/SDS_METADATA.json`; it does **not** silently substitute a different CAS or salt. No source being found remains a human-review gap, not an approved assessment.

Every new assessment runs in its own unique output directory to prevent old COSHH DOCX files with the same material name being served inadvertently. The generated document must retain the controlled form's 134 tags, headers and Word styles, and `COSHH_STATUS.json` records both the original template checksum and output checksum. Previous unsuccessful assessments are labelled with their actual COSHH generation error, rather than being described as old-format documents. A COSHH-only rebuild can use the previously completed Cleaning Validation research, without repeating paid Cleaning Validation queries.

The controlled 134-field template is mandatory: startup rejects absent/mismatched templates, and the old programmatically drawn COSHH form has been removed. The form is always read as the exact binary DOCX at `templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx` (no embedded resource copies or template substitution). After switching branches, **restart the existing Codespaces Python web server** to load the updated code. Use `python -m agent.cli check` to verify both templates.

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

Activity risk combines intrinsic hazard severity with exposure potential. PPE is task-specific and does not replace engineering controls. The Eaststone local rule uses a contained/extracted fume hood for QC airborne powder/vapour tasks, with no QC respirator selection. For Production/R&D, full-face respiratory protection with a task-appropriate powder and/or vapour filter is selected where airborne RPE is required; surgical masks are never accepted as airborne-hazard RPE. Where a relevant engineering or containment arrangement is unconfirmed, the draft flags it for human review rather than claiming control adequacy.

## Compatibility with older COSHH queue records

The queue reader tolerates legacy `COSHH_STATUS.json` files lacking `stage`,
`sds_attempt_count` and other fields. A bad COSHH status cannot hide the
Cleaning Validation queue. The UI shows an explicit server error instead of
silently presenting an empty assessment list. Records already in SQLite are
not modified by this compatibility fix. A `RESEARCHING` record without a
detected web worker is highlighted for checking rather than automatically
restarted (which could repeat paid research).

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
- `Attach SDS PDF` for a blocked SDS source, preserving the uploaded original;
- `Rebuild COSHH only` from saved Cleaning Validation work (no Cleaning Validation repeat; one PDF-specific extraction call if an SDS is available);
- COSHH error/SDS download-attempt diagnostics, and a no-AI download of the approved Word master;
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

Each individual assessment receives a unique folder under `outputs/<material>/<run-id>/`, preventing an old Word form from being mistaken for a new COSHH draft. The folder contains the Cleaning Validation outputs plus, where COSHH generation succeeds:

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
