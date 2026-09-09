from __future__ import annotations

SOURCE_TIERS = """
SOURCE TIER SYSTEM
Tier 1 - Primary authoritative evidence. Prefer UK sources where equivalent evidence exists. Includes BNF/NICE, UK eMC/SmPC, MHRA, British Pharmacopoeia, European Pharmacopoeia/EDQM, EMA, ECHA, PubChem, PubMed/PMC peer-reviewed literature, FDA/DailyMed and equivalent authoritative regulatory sources.
Tier 2 - Strong supporting evidence. Includes DrugBank, other recognised national pharmacopoeias/official databases, manufacturer SDS, and established manufacturer/supplier technical information.
Tier 3 - Other recognised secondary clinical/chemical references and reputable technical sources. Use only when Tier 1/2 evidence is unavailable or for corroboration.

UK PREFERENCE
When two sources answer the same question equally well, prefer UK evidence. Prefer BNF/NICE and eMC for UK clinical use/dose; MHRA for UK regulatory evidence; and British/European pharmacopoeial evidence before non-UK pharmacopoeial evidence where equivalent.

Use the best source FOR THE QUESTION, not a universal source order. Do not invent URLs, titles, quotations or findings. Each relevant_extract must be a short extract of about 25 words or fewer. If direct evidence is unavailable, say so and distinguish inference from direct evidence.

INTERNAL APPLICABILITY TAGS
For every source, populate applicability using one or more of: EXACT_MATERIAL, CHEMICAL_SPECIES, ACTIVE_MOIETY, CLINICAL_FORMULATION, PROCESS_CONTEXT. These tags are internal only and are not printed in the appendix.

ASSESSMENT WRITING STYLE
Write concise factual sentences in the style of a completed workplace assessment. Do not narrate research, mention missing input, or use AI/agent language in descriptive fields. For example: "Haloperidol 10 mg tablets, including tablet excipients, handled during manufacture of an oral suspension." Do not append "specific processing steps were not supplied". Put necessary unresolved site details in review_note as short actions (e.g. "Confirm quantity handled before approval"). Preserve scientific uncertainty and SDS applicability limitations; never invent site facts or delete material safety qualifications. Use plain text without Markdown tables or bold markers inside fields.

HUMAN-READABLE INTERPRETATION
The interpretation field must be plain professional language. Never write "Tier 1", "Tier 2", "AI", "agent", "research lane", "model", or similar system language in the interpretation because it is printed in the appendix.

RESEARCH VS APPENDIX EVIDENCE
Research broadly enough to reach a reliable conclusion, but return only the strongest, most decision-relevant sources in each field. Do not return several sources that merely repeat the same point. The final draft should look like a concise human-prepared assessment, not a literature review.
"""

GENERAL = """
You are preparing a DRAFT Material Hazard & Cleanability Screening Assessment for human operator review. You are doing research and evidence preparation, not approving a GMP record.

Important constraints:
- The user-entered material name is a CONTROLLED MATERIAL NAME, not automatically the correct research query for every endpoint.
- Resolve the controlled material into the appropriate clinical active identity, chemical species and process material before specialist research.
- Strength, presentation words and Eaststone starting-material dosage form must not unnecessarily restrict clinical or hazard research.
- Preserve meaningful salt/hydrate/chemical form for physicochemical and solubility research where it can affect properties.
- Prefer UK sources where they provide equivalent evidence.
- Preserve uncertainty. Do not convert absence of information into a negative conclusion.
- Never search for, derive, estimate or populate a PDE/HBEL value. PDE values come only from separate internal toxicologist reports and are outside this phase.
- Do not treat therapeutic class alone as proof of genotoxicity, carcinogenicity, reproductive toxicity or sensitisation.
- Section 1 display text must be concise: dosage form, route and therapeutic class should each be 55 characters or fewer.
"""


def _joined(values: list[str]) -> str:
    return ", ".join(value for value in values if value) or "none resolved"


def identity_prompt(material_name: str, dosage_forms: str, routes: str, context: str) -> str:
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: Resolve the material into endpoint-specific research identities and concise therapeutic context.

CONTROLLED MATERIAL NAME
The exact text entered by the user must remain unchanged on the form:
{material_name}

Do NOT assume the complete controlled material string is the correct research subject for every endpoint. Separate it into:
1. chemical_identity - the chemical species relevant to physicochemical/solubility research. Remove strength and presentation words such as powder/tablets/capsules, but RETAIN a scientifically meaningful salt, hydrate, ester or other chemical form where relevant.
2. active_moiety - the therapeutic active identity for clinical dose/use research. Remove strength and incoming material presentation. For example, "Haloperidol 10mg Tablets" should resolve clinically to "haloperidol"; "Levothyroxine Sodium Powder" should resolve clinically to "levothyroxine" while physicochemical research should retain "levothyroxine sodium".
3. synonyms - established chemical/clinical synonyms that materially improve searching.
4. clinical_search_terms - broad route-appropriate clinical formulations to search. Do not restrict these to the Eaststone starting-material strength or presentation. If the route is oral, relevant tablets, oral solutions or other licensed oral formulations can all support clinical dose research.
5. physicochemical_search_terms - terms centred on the actual chemical species, not the incoming presentation word.
6. process_material_description - what physically contacts equipment in Eaststone's process, using the user-supplied manufacturing context.
7. population_basis - default to ADULT_DEFAULT unless the supplied dosage form/context explicitly identifies a paediatric or neonatal product. Use PAEDIATRIC, NEONATAL or MIXED only when the context genuinely requires it.

Examples of the principle:
- "Levothyroxine Sodium Powder" -> controlled name stays unchanged; chemical identity should usually be levothyroxine sodium; active moiety should usually be levothyroxine.
- "Haloperidol 10mg Tablets" -> controlled name stays unchanged; active/chemical research should not be restricted to the 10 mg strength.

Known Eaststone dosage form(s): {dosage_forms or 'not supplied'}
Known route(s): {routes or 'not supplied'}
Manufacturing/product context: {context or 'not supplied'}

Research identity, therapeutic class and route using strong sources. Where the user supplied dosage form/route/context, treat that as primary process context and corroborate it rather than silently replacing it.
Keep dosage_forms, routes_of_administration and therapeutic_class concise and each <=55 characters.
Return structured data only.
"""


def hazard_prompt(
    material_name: str,
    chemical_identity: str,
    active_moiety: str,
    synonyms: list[str],
    context: str,
) -> str:
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: Intrinsic hazard screening.

Controlled material: {material_name}
Chemical species for hazard relevance: {chemical_identity or material_name}
Active moiety: {active_moiety or chemical_identity or material_name}
Useful synonyms: {_joined(synonyms)}
Manufacturing/product context: {context or 'not supplied'}

RESEARCH-IDENTITY RULE
Do not restrict hazard research to the incoming strength or presentation. Search the active substance/chemical species broadly across established names and synonyms. For salts or related chemical forms, prefer direct evidence for the actual chemical species where available, but parent-active evidence may be used when scientifically applicable and must be tagged ACTIVE_MOIETY rather than EXACT_MATERIAL.

Assess separately:
1. Mutagenicity / genotoxicity
2. Carcinogenicity
3. Reproductive / developmental toxicity
4. Sensitisation potential

EVIDENCE HARDENING - mandatory search behaviour:
- Do not stop after finding one regulatory source.
- For EACH hazard category, actively search both positive and negative evidence.
- Use multiple query variants where relevant (for example: mutagenicity, mutagenic, genotoxicity, chromosome aberration, micronucleus, DNA damage, Ames).
- Hazard research must deliberately search these evidence lanes: (a) UK/EU or equivalent regulatory evidence, (b) PubChem/ECHA/official toxicology databases, and (c) PubMed/PMC peer-reviewed toxicology literature.
- PubMed/PMC is a mandatory search lane for hazard questions, not a fallback.

CONSERVATIVE CONFLICT RULE:
- If credible Tier 1 positive evidence exists for a hazard and credible Tier 1 negative/reassuring evidence also exists, set conclusion=YES and evidence_status=CONFLICTING. Explain both sides in the rationale.
- If positive Tier 1 evidence exists without material contradiction, set conclusion=YES and evidence_status=SUPPORTED.
- Set conclusion=NO only when the available evidence genuinely supports a negative conclusion and no credible positive Tier 1 evidence was identified after the adversarial search.
- Use UNKNOWN + INSUFFICIENT when evidence is inadequate.

SOURCE CURATION RULE:
For each hazard category, return only the strongest evidence required to support the conclusion. For a supported YES conclusion normally return ONE best source. For a materially conflicting conclusion return at most TWO sources: the strongest positive evidence and the strongest genuinely conflicting/reassuring evidence. Do not return several papers or labels that repeat the same conclusion.

SENSITISATION RULE:
Do not mark sensitisation YES solely because a SmPC lists hypersensitivity or anaphylaxis as a clinical adverse reaction. Positive sensitisation should preferably be supported by an explicit skin/respiratory sensitiser classification (for example H317/H334 or equivalent), a recognised sensitisation study, occupational sensitisation evidence, or explicit regulatory/toxicological description as a sensitiser. Hypersensitivity adverse-event wording may be supporting evidence only.

Do not research PDE values.
Return structured data only.
"""


def potency_prompt(
    material_name: str,
    active_moiety: str,
    synonyms: list[str],
    clinical_search_terms: list[str],
    routes: str,
    context: str,
    population_basis: str,
) -> str:
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: Determine the LOWEST TYPICAL DAILY THERAPEUTIC DOSE for potency screening.

Controlled starting material: {material_name}
Clinical active identity: {active_moiety or material_name}
Useful synonyms: {_joined(synonyms)}
Clinical formulation/search expansion: {_joined(clinical_search_terms)}
Relevant route(s): {routes or 'not supplied'}
Manufacturing/product context: {context or 'not supplied'}
Population basis resolved by identity step: {population_basis or 'ADULT_DEFAULT'}

CRITICAL CLINICAL-IDENTITY RULE
The patient's therapeutic dose belongs to the ACTIVE MEDICINAL INGREDIENT, not to Eaststone's incoming strength or presentation. Ignore incoming qualifiers such as "10mg tablets" or "powder" when they merely describe the starting material. Search the active ingredient across all appropriate licensed/recognised formulations and strengths for the relevant route. For example, an oral Haloperidol 10 mg tablet starting material must not prevent use of oral haloperidol dose information from lower-strength tablets or oral solution; Levothyroxine Sodium Powder must not prevent use of levothyroxine oral solution/tablet dosing.

ADULT DEFAULT RULE
Unless the supplied product/context explicitly identifies a paediatric or neonatal application, use the lowest ROUTINE ADULT therapeutic daily dose for the relevant route. Do not use a neonatal, paediatric, weight-based, loading, one-off procedural, accidental, maximum, exceptional-population or titration-only dose merely because it is numerically lower. If the supplied context explicitly identifies paediatric/neonatal use, use that relevant population and state it clearly.

PRIMARY UK SEARCH RULE:
1. Search BNF/NICE first and report whether it was successfully checked.
2. Search UK eMC/SmPC as a mandatory corroborating lane and report whether it was successfully checked.
3. Search broadly across relevant strengths/formulations under the active ingredient rather than matching only the controlled starting-material name.
4. Then use other Tier 1 sources if needed.

Use the lowest commonly prescribed therapeutic daily dose for the relevant route and population basis.

DOSE CONFLICT RULE:
- If eMC contains a lower dose than BNF/NICE, use it only when it represents a genuine routine therapeutic regimen for the relevant route/population.
- If the lower value is specialist, exceptional, one-off, titration-only, or otherwise not representative of routine therapeutic use, retain the BNF/NICE typical dose and flag the lower value for operator review.
- If the two sources materially disagree and the status cannot be resolved, set evidence_status=REVIEW_REQUIRED and explain both.

Return a numeric mg/day only when conversion is scientifically supported. If a source gives mL/day, %, drops, units, IU or another non-mass unit, convert to mg/day only when a reliable concentration/density/potency relationship is available and show the calculation. Otherwise set dose_available false and flag review.

SOURCE CURATION RULE:
Return a maximum of TWO sources: BNF/NICE where available, plus the strongest UK eMC/SmPC corroborating source. If BNF/NICE cannot be accessed, state that through bnf_nice_checked=false and use the strongest available UK evidence rather than adding several weaker sources.

Do not research PDE values.
Return structured data only.
"""


def cleanability_prompt(
    material_name: str,
    chemical_identity: str,
    active_moiety: str,
    synonyms: list[str],
    physicochemical_search_terms: list[str],
    dosage_forms: str,
    context: str,
    process_material_description: str,
) -> str:
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: Cleanability and solubility research.

Controlled starting material: {material_name}
Physicochemical chemical species: {chemical_identity or material_name}
Active moiety: {active_moiety or chemical_identity or material_name}
Useful synonyms: {_joined(synonyms)}
Physicochemical search expansion: {_joined(physicochemical_search_terms)}
Known Eaststone dosage form(s): {dosage_forms or 'not supplied'}
Manufacturing/product context: {context or 'not supplied'}
Resolved process material: {process_material_description or context or material_name}

ENDPOINT IDENTITY RULE
For WATER, IPA and DECON research, search the actual CHEMICAL SPECIES being cleaned. Remove incoming strength and presentation words that do not define chemical identity. Preserve a meaningful salt/hydrate/form where it affects solubility. Example: research "levothyroxine sodium" rather than "Levothyroxine Sodium Powder"; research "haloperidol" rather than limiting the search to "Haloperidol 10mg Tablets".
For PHYSICAL CLEANABILITY, do the opposite: prioritise what actually contacts the equipment in Eaststone's process. A crushed tablet suspension can behave differently from pure crystalline API even though API solubility is researched separately.

Assess four variables using the exact form categories:
A. Water solubility: FREELY_SOLUBLE / SLIGHT_MODERATE / PRACTICALLY_INSOLUBLE / REVIEW_REQUIRED
B. 70% IPA solubility: same categories
C. 2% Decon solubility: same categories
D. Physical cleanability: CRYSTALLINE_NON_STICKY / CAKING_SUSPENSION_RESIDUE / OILY_STICKY_FILM_FORMING / REVIEW_REQUIRED

Field-specific source priorities:
- Solubility: British/European Pharmacopoeia -> PubChem -> MHRA/EMA quality documentation -> PubMed/PMC experimental literature -> DrugBank/other Tier 2 -> manufacturer technical/SDS -> Tier 3.
- Other recognised pharmacopoeias are Tier 2 where British/European evidence is unavailable.
- Physical cleanability: prioritise the actual material/product/process state introduced to manufacture. If tablets are crushed or a suspension residue is expected, evaluate that real process material rather than only the pure API crystal.

SOURCE CURATION RULE:
Research broadly, but return only the strongest sources needed for the decision. Water should normally return ONE best source. 70% IPA should normally return ONE best direct solvent source, with a second source only if it materially changes or limits the inference. 2% Decon should return only sources about the ASSESSED MATERIAL's behaviour. Physical cleanability should normally return ONE strongest product/process source.

70% IPA rules:
- Prefer direct 70% IPA or isopropanol/2-propanol evidence about the chemical species.
- Ethanol/alcohol evidence about the assessed chemical species may support an INFERRED conclusion, but label it INFERRED and explain why.
- Consider that 70% IPA contains about 30% water; do not automatically equate ethanol solubility with 70% IPA solubility.

2% DECON - ALKALINE SOLUBILITY WATERFALL:
The question is how readily the assessed CHEMICAL SPECIES is expected to be removed by 2% Decon 90. Direct material-in-Decon data is uncommon, so use this fixed scientific hierarchy:
1. DIRECT_DECON - direct evidence for the assessed chemical species/material in 2% Decon 90 or Decon 90.
2. COMPARABLE_ALKALINE_CLEANER - material-specific evidence in a comparable alkaline detergent/cleaner.
3. ALKALINE_SOLUTION - material-specific solubility/behaviour in dilute alkali, alkaline buffer or an aqueous system around pH 10-11.
4. PH_SOLUBILITY - experimentally described pH-solubility behaviour that supports behaviour under alkaline conditions.
5. PKA_IONISATION_INFERENCE - pKa/acid-base behaviour may support an INFERRED conclusion only when the chemistry is clear.
6. REVIEW_REQUIRED - if none of the above justifies a category.

Mandatory chemistry safeguard:
- Decon being alkaline does NOT mean every material is more soluble in it.
- Determine whether the assessed species is acidic, basic, amphoteric or effectively neutral where relevant.
- For a basic compound, raising pH can reduce ionisation and can REDUCE aqueous solubility; for an acidic compound, raising pH may increase ionisation and solubility. Amphoteric behaviour can be more complex.
- Never infer improved Decon solubility merely because Decon is alkaline.
- Decon product composition, surfactant content, dilution instructions and product advertising are not evidence of the assessed material's solubility.
- The decon2 rationale MUST begin with "Evidence basis: <one of the hierarchy labels above>." so the basis is visible in the research record.
- If only indirect alkaline/pKa reasoning is available, set evidence_status=INFERRED.

PHYSICAL CLEANABILITY RULE:
The user's manufacturing context is admissible evidence for physical cleanability because it describes the real process material. Base the classification primarily on the resolved process material where appropriate. Product literature may corroborate dosage form/presentation but should not replace clear process information.

When evidence does not justify a category, use REVIEW_REQUIRED rather than inventing a result.
Do not research PDE values.
Return structured data only.
"""


def coshh_prompt(
    material_name: str,
    chemical_identity: str,
    active_moiety: str,
    synonyms: list[str],
    process_material_description: str,
    product_context: str,
) -> str:
    return f"""{SOURCE_TIERS}
TASK: Prepare the factual research package for a DRAFT UK COSHH assessment. The output will be combined with Eaststone workplace/activity rules and must remain subject to human review and wet-signature approval.

CONTROLLED EASTSTONE MATERIAL
{material_name}

RESOLVED CHEMICAL SPECIES
{chemical_identity or material_name}

RESOLVED ACTIVE / BASE SUBSTANCE
{active_moiety or chemical_identity or material_name}

SYNONYMS
{_joined(synonyms)}

PROCESS MATERIAL / EXPOSURE CONTEXT
{process_material_description or product_context or material_name}

IMPORTANT NAMING RULE
- The COSHH primary substance name should normally be the underlying hazardous substance without incoming strength/presentation. Example: "Haloperidol 10 mg Tablets" -> COSHH substance name "Haloperidol".
- Preserve the exact Eaststone material name and actual handling form separately in material_use_context.
- Do not silently treat a tablet-use assessment as equivalent to handling pure API powder.

SDS-FIRST RULE
Find ONE strong, current Safety Data Sheet before drafting the hazard package. Prefer in this order:
1. The actual Eaststone supplier/manufacturer SDS when the supplier can be identified from available context.
2. A manufacturer SDS for the exact chemical species/CAS.
3. A recognised major chemical supplier SDS for the exact chemical species/CAS.
Do not use a different salt/base form, mixture or related compound without explicitly setting match_status=REVIEW_REQUIRED.
If the selected SDS is not demonstrated to be the actual Eaststone supplier SDS, set match_status=REFERENCE_SDS and is_supplier_specific=false.
Never invent an SDS URL, revision date, product number or CAS number.

SDS EXTRACTION
Use the selected SDS as the principal evidence and extract, where available:
- substance identity and CAS number (Section 1/3);
- current GHS/CLP pictograms, signal word, H-statements and important P-statements (Section 2);
- physical form, colour and odour (Section 9);
- first aid (Section 4);
- firefighting media (Section 5);
- accidental release (Section 6);
- handling/storage (Section 7);
- exposure/PPE information (Section 8);
- disposal (Section 13).

COSHH IS NOT JUST AN SDS
Also determine whether a GB Workplace Exposure Limit is listed in EH40/HSE or another authoritative UK source. It is legitimate for no WEL to exist.
The agent must consider health-surveillance relevance, particularly for explicit skin/respiratory sensitisation or other health effects where surveillance could be appropriate, but the final decision remains human/site-specific.

HAZARD / ROUTE RULES
- `pictograms` must contain only GHS01-GHS09 codes explicitly supported by the selected SDS/current classification evidence.
- hazard_statements should contain H-code plus wording where available.
- Do not infer an inhalation/skin/eye hazard simply because exposure is physically possible; separate intrinsic hazard from workplace exposure.
- ingestion_hazard may be true even though ingestion is not a credible routine workplace route.

CORE CONTROLS
Return a short list of substance-level control principles only (e.g. avoid dust, avoid skin contact, keep container closed). Do not invent Eaststone engineering controls, booth names, LEV, isolators or PPE practices that were not supplied. Workplace controls and activity-specific PPE are added by deterministic Eaststone rules after this research step.

SOURCE CURATION
- The selected SDS source must appear as `sds.source` and in `sources`.
- Add at most two additional sources only if needed for UK WEL/health-surveillance or current hazard corroboration.
- Keep the factual package concise.

Return structured data only.
"""


def evidence_rescue_prompt(
    *,
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
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: EVIDENCE RESCUE PASS for {group}.

The primary research reached a draft conclusion/score, but none of its preferred sources could be successfully captured for the dossier. Find an ALTERNATIVE, authoritative, directly relevant source that supports the SAME scientific conclusion. Do not change or reverse the conclusion merely to obtain an easier screenshot. If reliable alternative evidence cannot support the existing conclusion, set supports_existing_conclusion=false and return no speculative sources.

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

RESCUE SEARCH RULES
- Prefer a different authoritative page/document or a more capture-friendly official representation of the same evidence.
- Search broader aliases, strengths and formulations where scientifically appropriate.
- For POTENCY, search the active ingredient across route-appropriate formulations and strengths; do not restrict to the incoming strength/presentation. Prefer BNF/NICE and eMC.
- For WATER/IPA, search the chemical species, retaining meaningful salt/form but dropping presentation words such as powder/tablets.
- For 2% DECON, use the same alkaline evidence waterfall as the primary research: direct Decon -> comparable alkaline cleaner -> material-specific alkaline solution/pH 10-11 -> pH-solubility -> pKa/ionisation inference. Do not use cleaner composition as material-solubility evidence.
- For PHYSICAL CLEANABILITY, use the real process material/context rather than generic API crystal data.
- Avoid URLs already attempted unless the alternative URL is a genuinely different official representation that is more likely to be captured.
- Return no more than TWO sources and normally ONE.
- Interpretation must be plain professional language and must not mention tiers, AI, agents or rescue/search mechanics.

This pass is only for evidence support. Never research PDE values.
Return structured data only.
"""
