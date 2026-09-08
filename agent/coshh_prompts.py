from __future__ import annotations


def coshh_prompt(
    *,
    controlled_material: str,
    chemical_identity: str,
    active_moiety: str,
    synonyms: list[str],
    product_context: str,
) -> str:
    aliases = ", ".join(synonyms) or "none"
    return f"""
You are preparing the factual research package for a DRAFT UK COSHH assessment for human review.
The output is NOT an approval and must not invent workplace facts.

CONTROLLED EASTSTONE MATERIAL
{controlled_material}

RESOLVED CHEMICAL IDENTITY
{chemical_identity}

ACTIVE MOIETY
{active_moiety}

SYNONYMS
{aliases}

KNOWN EASTSTONE PROCESS CONTEXT
{product_context or 'not supplied'}

IMPORTANT NAMING RULE
The COSHH substance name should normally be the hazardous chemical substance, not the incoming strength/presentation.
Example: "Haloperidol 10 mg Tablets" should normally display COSHH substance "Haloperidol" while preserving "Haloperidol 10 mg Tablets" exactly in material_context.
Do not silently equate handling a formulated tablet with handling pure API powder; physical exposure form must be described honestly.

PRIMARY TASK - FIND ONE SUITABLE SDS FIRST
Search for a current, credible Safety Data Sheet for the resolved chemical identity, using the CAS number where possible.
Priority:
1. Actual supplier SDS only when the evidence really shows it is the Eaststone supplier.
2. Otherwise a recognised manufacturer/reference-substance SDS.
3. A mixture/formulation SDS only where it matches the assessed material and is scientifically appropriate.

Never claim a reference SDS is the actual Eaststone supplier SDS.
Validate substance name, CAS number and chemical/salt form. A different salt/ester/mixture must not silently populate the assessment.
Populate sds.match_type accordingly and flag uncertainty.

SDS-LED EXTRACTION
Use the selected SDS as the primary source for:
- GB/EU CLP hazard classification, GHS pictograms, signal word, H statements and relevant P statements
- physical form, colour, odour
- routes of exposure / effects
- first aid
- accidental release
- handling and storage
- environmental precautions
- disposal
- firefighting media
- exposure controls / PPE recommendations
- relevant toxicology and sensitisation information

Use concise professional wording suitable for a COSHH form. Preserve important qualifiers.
Do not overstate PPE. An SDS recommendation is not automatically the final Eaststone PPE decision.

WEL CHECK
Separately check whether a UK Workplace Exposure Limit is identifiable from HSE EH40 or another authoritative UK source.
If no UK WEL is identified, set identified=false and say so. Do not invent a limit from another jurisdiction.

HEALTH SURVEILLANCE
Provide a short consideration, not a final occupational-health decision. Highlight explicit skin/respiratory sensitisation or other factors that warrant human review.

ROUTE RULE
A route can be relevant even when it is not expected in normal operation if it is a credible exposure route for the substance/material. Keep the rationale proportionate.

REVIEW FLAGS
Add review flags for any material issue, including:
- reference rather than actual supplier SDS
- CAS/name/salt-form uncertainty
- old/undated SDS
- respiratory or skin sensitiser
- CMR or serious acute toxicity
- WEL identified
- SDS PPE specification that needs site-specific confirmation
- material exposure form materially different from the SDS substance form

Do not fabricate Eaststone engineering controls, quantities, frequencies, durations, signatures, approval status or occupational-health conclusions.
Return structured data only.
"""
