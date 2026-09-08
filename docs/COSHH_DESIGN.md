# COSHH Assessment Design

## Purpose

The COSHH module converts the historical Eaststone paper COSHH concept into an agent-friendly workflow while preserving the purpose of a COSHH assessment: identify hazardous substances, evaluate how people may be exposed during actual work, define suitable controls, and document the outcome for human review and approval.

The original Eaststone COSHH templates used one hazard sheet plus multiple area-specific PPE sheets. The redesigned module keeps the same conceptual separation internally but renders a much simpler signed draft.

## Source hierarchy

COSHH factual research is SDS-first.

1. Current actual Eaststone supplier/manufacturer SDS where identifiable.
2. Manufacturer SDS for the exact chemical species/CAS.
3. Major recognised chemical supplier SDS for the exact chemical species/CAS.
4. Additional authoritative UK evidence only where needed for workplace exposure limits, health-surveillance considerations or current hazard corroboration.

A reference SDS is not presented as though it were the actual supplier SDS.

## Substance name vs material context

The Cleaning Validation form retains the exact controlled material name.

COSHH normally uses the underlying hazardous substance name. The exact Eaststone starting material and handling context remain visible separately.

Example:

- controlled material: `Haloperidol 10 mg Tablets`;
- COSHH substance: `Haloperidol`;
- use context: tablets used as a starting material and crushed/manipulated during manufacture.

This prevents a tablet-use COSHH from being silently treated as equivalent to a pure API powder assessment.

## Intrinsic hazard vs workplace exposure

The agent separates two questions:

1. **What can the substance do?** - answered principally by the SDS/classification evidence.
2. **How can Eaststone staff be exposed during this task?** - answered by selected area/activity profiles plus operator-supplied workplace context.

The model is therefore not permitted to invent Eaststone LEV, booths, isolators, quantities, frequency or duration.

## Supported areas

- Goods In / Warehouse
- Sampling
- QC
- Production
- R&D
- Housekeeping
- Office

The detailed JSON retains the full activity assessment. The Word draft shows the principal decision-relevant activities only so the form remains concise.

## Goods In logic

Checking/opening **outer packaging** is treated as contained handling unless the package is damaged/leaking. Opening a transit carton is not treated as opening the primary material container.

Spill response is assessed separately as a foreseeable abnormal exposure.

## Risk logic

Initial risk is derived from:

`intrinsic hazard severity x activity exposure potential`

Residual risk considers whether the activity is contained and whether the operator supplied a recognisable engineering/containment control.

PPE is task-specific. Respiratory protection is not used as a substitute for engineering control. High-concern open powder/vapour tasks remain flagged for human review if the actual control arrangement has not been supplied.

## Health surveillance

The research step records whether health surveillance has been considered and whether the evidence suggests that a human reviewer should assess the need for surveillance. The agent does not make a final occupational-health decision.

## SDS preservation

The SDS PDF is stored separately and unchanged. No annotations, highlights, page extraction or re-saving are applied to the original document. SHA-256 is recorded to support integrity/traceability.

## Document design

The signed draft is intentionally simple.

### Page 1

- substance and assessment scope;
- SDS identity;
- GHS pictograms / H-statements;
- exposure routes;
- core controls.

### Page 2

- compact activity/control/PPE table;
- initial/residual risk;
- first aid, spillage, storage and disposal;
- SDS traceability;
- blank reviewer/approver/signature/date fields.

Long or unusual cases may flow beyond two pages rather than clipping content.

## Approval boundary

All outputs are marked as draft. Reviewer/approver names, signatures and dates are deliberately not populated by the agent. Approval remains a human process.
