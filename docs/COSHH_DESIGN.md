# COSHH module — controlled-template and recovery design

## Controlled document (only supported rendering path)
`agent/coshh_document.py` calls the tagged-template filler in `agent/coshh_template.py`.
No legacy programmatically assembled COSHH document remains. The exact Word resource:
`templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx` has 134 individually
tagged content controls. Startup validates them; generating a Word form validates
the output against the master header, styles and the 134 tags. The human
review/approval names, dates, signoffs and adequacy decision stay blank.

The Cleaning Validation form `ES.SOP.272.F01.V02 - Material Hazard &
Cleanability Screening Assessment.docx` remains independent and unchanged.
Every run has a unique output directory, so no earlier COSHH form may be
returned in place of the current one.

## SDS identity and source matching
Use incoming material to define the actual substance and physical exposure,
not to restrict SDS searches by presentation, strength, dosage form or route.
For `Levomepromazine Maleate Powder` the substance SDS query is
`levomepromazine maleate`, CAS `7104-38-3`, with `levomepromazine` as a
review-required base-moiety fallback. Do not silently substitute a different
salt, excipient blend, or manufactured dosage form. A third-party SDS is a
reference and requires actual site-supplier verification.

A deterministic official British Pharmacopoeia SDS URL is checked with HTTP
and PDF identity/readability validation **before** paid COSHH web research.
If it succeeds, the complete downloaded PDF text is provided to a single
COSHH-only structured extraction call with the web-search tool disabled.
If it fails, normal SDS research may try the initial URL, linked supplier PDFs,
and limited alternative searches. `COSHH_MAX_RESCUE_SEARCHES` defaults to 1 to
avoid burning API credits across repeated blocked supplier websites.

## No-cost troubleshooting and controlled restart
`GET /api/templates/coshh` returns the unmodified master template without AI.
`GET /api/coshh/{id}/diagnostics` exposes the actual generation error and
recorded SDS HTTP attempts; the UI never describes an absent form as an "old
form". Download of an unverified generated COSHH remains blocked.

The original SDS may be attached with
`POST /api/coshh/{id}/sds` (multipart file). The app checks PDF structure,
readability, candidate substance identity and size, preserves the original
bytes and SHA-256, and records the provenance as USER_UPLOAD.
Upload alone does NOT approve the document or consume an AI call.

`POST /api/coshh/{id}/retry` rebuilds COSHH **only** from that row's
`assessment.json` (the paid Cleaning Validation work is not repeated).
If no acceptable SDS can be found, the preflight fails with no AI usage.
Otherwise one PDF-grounded extraction call runs, followed by deterministic
activity/PPE assessment, controlled Word filling and structural verification.
Any failure is recorded in `COSHH_ERROR.txt` and
`COSHH_STATUS.json` without marking the Cleaning Validation report failed.

## Departmental controls and approval
QC airborne handling uses the contained, externally extracted fume hood;
Production/R&D use appropriate half-face respirators where required. The
fume hood remains in the controlled form's PPE matrix by Eaststone convention.
The form retains all 9 current GB CLP pictogram options. All results are
drafts, require appropriate review, and must be checked against the site
supplier SDS and actual work activity before approval.
