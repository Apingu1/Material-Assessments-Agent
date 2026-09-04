from __future__ import annotations

from .prompts import GENERAL, SOURCE_TIERS


_FAMILY_RULES: dict[str, str] = {
    "NICE_GUIDANCE": "Return only NICE guidance or NICE-hosted clinical dosing evidence from nice.org.uk. Do not return BNF pages for this rescue family.",
    "EMC_SMPC": "Return only UK eMC Summary of Product Characteristics evidence from medicines.org.uk. Search relevant route-appropriate formulations and strengths, not only the Eaststone starting-material presentation.",
    "MHRA_EMA": "Return only MHRA/GOV.UK or EMA regulatory evidence.",
    "FDA_DAILYMED": "Return only FDA or DailyMed regulatory evidence.",
    "OTHER_TIER1": "Return another authoritative Tier 1 source not already attempted, prioritising direct relevance and capture-friendly public access.",
    "BRITISH_EUROPEAN_PHARMACOPOEIA": "Return only British Pharmacopoeia, European Pharmacopoeia/EDQM, or an official equivalent pharmacopoeial monograph if the preferred UK/EU source is unavailable.",
    "PUBCHEM": "Return only PubChem evidence about the assessed chemical species.",
    "PUBMED_PMC": "Return only PubMed/PMC peer-reviewed evidence directly relevant to the endpoint.",
    "DRUGBANK": "Return only DrugBank evidence directly relevant to the endpoint.",
    "MANUFACTURER_TECHNICAL": "Return only an established manufacturer/supplier technical document or SDS that directly addresses the assessed material/property.",
    "DIRECT_MATERIAL_DECON": "Return only evidence that directly reports the assessed chemical species/material in Decon 90 or a 2% Decon cleaning solution. Cleaner composition, dilution instructions and product advertising are prohibited.",
    "PROCESS_PRODUCT_INFORMATION": "Return only evidence about the actual process material or product presentation that materially supports physical cleanability. Prefer the supplied manufacturing context where it is more directly relevant than generic product literature.",
    "UK_EU_REGULATORY": "Return only UK/EU regulatory hazard evidence from MHRA/GOV.UK, eMC, EMA or ECHA.",
    "PUBCHEM_ECHA": "Return only PubChem or ECHA hazard evidence.",
    "MANUFACTURER_SDS": "Return only an established manufacturer SDS with explicit relevant hazard classification.",
}


def _joined(values: list[str]) -> str:
    return ", ".join(value for value in values if value) or "none"


def source_family_rescue_prompt(
    *,
    family: str,
    group: str,
    material_name: str,
    chemical_identity: str,
    active_moiety: str,
    synonyms: list[str],
    clinical_search_terms: list[str],
    physicochemical_search_terms: list[str],
    routes: str,
    context: str,
    target_summary: str,
    existing_urls: list[str],
) -> str:
    family_rule = _FAMILY_RULES.get(family, _FAMILY_RULES["OTHER_TIER1"])
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: TARGETED EVIDENCE SUPPORT for {group}.

The scientific assessment already has a draft conclusion/score. Your job is only to find a suitable supporting source from the SPECIFIC SOURCE FAMILY below. Do not change the scientific conclusion to make evidence easier to find. If this source family cannot support the existing conclusion, set supports_existing_conclusion=false and return an empty sources list.

SOURCE FAMILY: {family}
SOURCE FAMILY RULE: {family_rule}

Controlled material: {material_name}
Chemical species: {chemical_identity or material_name}
Clinical active identity: {active_moiety or chemical_identity or material_name}
Synonyms: {_joined(synonyms)}
Clinical search expansion: {_joined(clinical_search_terms)}
Physicochemical search expansion: {_joined(physicochemical_search_terms)}
Relevant route(s): {routes or 'not supplied'}
Manufacturing/product context: {context or 'not supplied'}
Existing conclusion/rationale to support: {target_summary}
Previously attempted URLs: {_joined(existing_urls)}

ENDPOINT RULES
- POTENCY: search the active ingredient across relevant strengths/formulations for the route. Do not restrict to the incoming strength, tablet/powder presentation or Eaststone starting material. Use routine adult dosing unless the supplied context explicitly requires paediatric/neonatal use.
- WATER/IPA/DECON: search the chemical species, preserving meaningful salt/hydrate/form while dropping presentation words such as powder/tablets.
- 2% DECON: never use Decon product composition, surfactants, dilution instructions or cleaner advertising as evidence of material solubility.
- PHYSICAL CLEANABILITY: prioritise the actual process residue/material described by the user.
- Avoid URLs already attempted unless the URL is a genuinely different official representation.
- Return normally ONE source and never more than TWO.
- Interpretation must be plain professional language and must not mention tiers, AI, agents, rescue/search mechanics or source-family names.

Never research PDE values.
Return structured data only.
"""
