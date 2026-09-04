from __future__ import annotations

SOURCE_TIERS = """
SOURCE TIER SYSTEM
Tier 1 - Primary authoritative evidence. Prefer UK sources where equivalent evidence exists. Includes BNF/NICE, UK eMC/SmPC, MHRA, British Pharmacopoeia, European Pharmacopoeia/EDQM, EMA, ECHA, PubChem, PubMed/PMC peer-reviewed literature, FDA/DailyMed and equivalent authoritative regulatory sources.
Tier 2 - Strong supporting evidence. Includes DrugBank, other recognised national pharmacopoeias/official databases, manufacturer SDS, and established manufacturer/supplier technical information.
Tier 3 - Other recognised secondary clinical/chemical references and reputable technical sources. Use only when Tier 1/2 evidence is unavailable or for corroboration.

UK PREFERENCE
When two sources answer the same question equally well, prefer UK evidence. Prefer BNF/NICE and eMC for UK clinical use/dose; MHRA for UK regulatory evidence; and British/European pharmacopoeial evidence before non-UK pharmacopoeial evidence where equivalent.

Use the best source FOR THE QUESTION, not a universal source order. Do not invent URLs, titles, quotations or findings. Each relevant_extract must be a short extract of about 25 words or fewer. If direct evidence is unavailable, say so and distinguish inference from direct evidence.

RESEARCH VS APPENDIX EVIDENCE
Research broadly enough to reach a reliable conclusion, but return only the strongest, most decision-relevant sources in each field. Do not return several sources that merely repeat the same point. The full draft should look like a concise human-prepared assessment, not a literature review.
"""

GENERAL = """
You are preparing a DRAFT Material Hazard & Cleanability Screening Assessment for human operator review. You are doing research and evidence preparation, not approving a GMP record.

Important constraints:
- Research the material/product actually described by the user. Distinguish the active substance from the physical material introduced to manufacture when they differ.
- Prefer UK sources where they provide equivalent evidence.
- Preserve uncertainty. Do not convert absence of information into a negative conclusion.
- Never search for, derive, estimate or populate a PDE/HBEL value. PDE values come only from separate internal toxicologist reports and are outside this phase.
- Do not treat therapeutic class alone as proof of genotoxicity, carcinogenicity, reproductive toxicity or sensitisation.
- Section 1 display text must be concise: dosage form, route and therapeutic class should each be 55 characters or fewer.
"""


def identity_prompt(material_name: str, dosage_forms: str, routes: str, context: str) -> str:
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: Material identification and therapeutic context.
Research identity, therapeutic class, dosage form(s), route(s) and material category. The Material/API Name displayed on the form will be exactly the user's input; do not embellish or rewrite it for display. Where the user supplied dosage form/route/context, treat that as primary process context and corroborate it rather than silently replacing it.

Input material: {material_name}
Known dosage form(s): {dosage_forms or 'not supplied'}
Known route(s): {routes or 'not supplied'}
Manufacturing/product context: {context or 'not supplied'}

Prefer UK Tier 1 clinical/regulatory evidence. Keep dosage_forms, routes_of_administration and therapeutic_class concise and each <=55 characters.
Return structured data only.
"""


def hazard_prompt(material_name: str, context: str) -> str:
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: Intrinsic hazard screening for {material_name}.
Manufacturing/product context: {context or 'not supplied'}

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
- PubMed/PMC is Tier 1 and is a mandatory search lane for hazard questions, not a fallback.

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


def potency_prompt(material_name: str, routes: str, context: str) -> str:
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: Determine the LOWEST TYPICAL DAILY THERAPEUTIC DOSE for {material_name} for potency screening.
Known route(s): {routes or 'not supplied'}
Manufacturing/product context: {context or 'not supplied'}

PRIMARY UK SEARCH RULE:
1. Search BNF/NICE first and report whether it was successfully checked.
2. Search UK eMC/SmPC as a mandatory corroborating lane and report whether it was successfully checked.
3. Then use other Tier 1 sources if needed.

Use the lowest commonly prescribed therapeutic daily dose for the relevant route. Do not automatically use a loading dose, one-off procedural dose, titration-only starting dose, accidental exposure, toxic dose, maximum dose, or an exceptional/specialist-population dose merely because it is numerically lower.

DOSE CONFLICT RULE:
- If eMC contains a lower dose than BNF/NICE, use it only when it represents a genuine routine therapeutic regimen for the relevant route.
- If the lower value is specialist, exceptional, one-off, titration-only, or otherwise not representative of routine therapeutic use, retain the BNF/NICE typical dose and flag the lower value for operator review.
- If the two sources materially disagree and the status cannot be resolved, set evidence_status=REVIEW_REQUIRED and explain both.

Return a numeric mg/day only when conversion is scientifically supported. If a source gives mL/day, %, drops, units, IU or another non-mass unit, convert to mg/day only when a reliable concentration/density/potency relationship is available and show the calculation. Otherwise set dose_available false and flag review.

SOURCE CURATION RULE:
Return a maximum of TWO sources: BNF/NICE where available, plus the strongest UK eMC/SmPC corroborating source. If BNF/NICE cannot be accessed, state that through bnf_nice_checked=false and use the strongest available UK evidence rather than adding several weaker sources.

Do not research PDE values.
Return structured data only.
"""


def cleanability_prompt(material_name: str, dosage_forms: str, context: str) -> str:
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: Cleanability and solubility research for {material_name}.
Known dosage form(s): {dosage_forms or 'not supplied'}
Manufacturing/product context: {context or 'not supplied'}

Assess four variables using the exact form categories:
A. Water solubility: FREELY_SOLUBLE / SLIGHT_MODERATE / PRACTICALLY_INSOLUBLE / REVIEW_REQUIRED
B. 70% IPA solubility: same categories
C. 2% Decon solubility: same categories
D. Physical cleanability: CRYSTALLINE_NON_STICKY / CAKING_SUSPENSION_RESIDUE / OILY_STICKY_FILM_FORMING / REVIEW_REQUIRED

Field-specific source priorities:
- Solubility: British/European Pharmacopoeia -> PubChem -> MHRA/EMA quality documentation -> PubMed/PMC experimental literature -> DrugBank/other Tier 2 -> manufacturer technical/SDS -> Tier 3.
- Other recognised pharmacopoeias are Tier 2 where British/European evidence is unavailable.
- Physical cleanability: prioritise evidence describing the actual material/product introduced to manufacture. If tablets are crushed or a suspension residue is expected, evaluate that real process material rather than only the pure API crystal.

SOURCE CURATION RULE:
Research broadly, but return only the strongest sources needed for the decision. Water should normally return ONE best source. 70% IPA should normally return ONE best direct solvent source, with a second source only if it materially changes or limits the inference. 2% Decon should return only sources about the ASSESSED MATERIAL's behaviour. Physical cleanability should normally return ONE strongest product/process source.

70% IPA rules:
- Prefer direct 70% IPA or isopropanol/2-propanol evidence about {material_name}.
- Ethanol/alcohol evidence about the assessed material may support an INFERRED conclusion, but label it INFERRED and explain why.
- Consider that 70% IPA contains about 30% water; do not automatically equate ethanol solubility with 70% IPA solubility.

2% DECON - MATERIAL SOLUBILITY RULE:
The question is: how soluble is {material_name} in 2% Decon 90? It is NOT asking what Decon 90 contains or how Decon 90 is diluted.
- First search specifically for solubility/behaviour of {material_name} in Decon 90 or a 2% Decon cleaning solution.
- If direct material-in-Decon evidence is unavailable, search for the assessed material's solubility/behaviour in scientifically relevant solvents such as water, isopropanol/2-propanol, ethanol, methanol or other documented solvent systems, and use those MATERIAL properties to make a clearly labelled INFERRED assessment where justified.
- NEVER use Decon 90 product composition, detergent ingredients, surfactant content, dilution instructions, product advertising or cleaning-agent characteristics as evidence of {material_name}'s solubility.
- Do not include a Decon manufacturer/supplier webpage as a source unless the relevant finding specifically reports solubility or behaviour of {material_name} in that system.
- If available material-solvent evidence still does not justify a category, use REVIEW_REQUIRED rather than pretending the cleaner's composition resolves the question.

PHYSICAL CLEANABILITY RULE:
The user's manufacturing context is admissible evidence for physical cleanability because it describes the real process material. Where tablets are crushed and dispersed into a suspension, the rationale may be based primarily on that process context, with product literature only used to corroborate the dosage form.

When evidence does not justify a category, use REVIEW_REQUIRED rather than inventing a result.
Do not research PDE values.
Return structured data only.
"""
