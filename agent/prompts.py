from __future__ import annotations

SOURCE_TIERS = """
SOURCE TIER SYSTEM
Tier 1 - Regulatory / expert / official clinical: UK SmPC/eMC, BNF, MHRA, EMA, FDA and official regulatory assessments. Internal toxicologist PDE/HBEL reports would also be Tier 1, but PDE reports are OUT OF SCOPE for this phase and must not be searched online.
Tier 2 - Authoritative scientific / pharmacopoeial: European or other recognised pharmacopoeias, PubChem, ECHA and recognised official toxicology/chemical databases.
Tier 3 - Peer-reviewed scientific literature: PubMed-indexed studies and recognised journals.
Tier 4 - Manufacturer / supplier technical sources: manufacturer SDS, Thermo Fisher, Merck/Sigma and equivalent technical data.
Tier 5 - Secondary references: DrugBank, Drugs.com, MIMS and other recognised secondary clinical/chemical references.

Use the best source tier FOR THE QUESTION, not one universal ranking. Do not invent URLs, titles, quotations or findings. Each relevant_extract must be a short extract of about 25 words or fewer from the source. If direct evidence is unavailable, say so and distinguish inference from direct evidence.
"""

GENERAL = """
You are preparing a DRAFT Material Hazard & Cleanability Screening Assessment for human operator review. You are doing research and evidence preparation, not approving a GMP record.

Important constraints:
- Research the material/product actually described by the user. Distinguish the active substance from the physical material introduced to manufacture when they differ (for example crushed tablets used to make a suspension).
- Prefer authoritative evidence and use multiple credible sources when useful.
- Preserve uncertainty. Use UNKNOWN when evidence is insufficient and CONFLICTING when credible sources disagree.
- Never search for, derive, estimate or populate a PDE/HBEL value. PDE values come only from separate internal toxicologist reports and are outside this phase.
- Do not treat therapeutic class alone as proof of genotoxicity, carcinogenicity, reproductive toxicity or sensitisation.
"""


def identity_prompt(material_name: str, dosage_forms: str, routes: str, context: str) -> str:
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: Material identification and therapeutic context.
Research the identity, therapeutic class, dosage form(s), route(s) of administration and material category. Where the user provided dosage form/route/context, treat that as primary process context and research to corroborate rather than silently replacing it.

Input material: {material_name}
Known dosage form(s): {dosage_forms or 'not supplied'}
Known route(s): {routes or 'not supplied'}
Manufacturing/product context: {context or 'not supplied'}

Preferred sources for this task: Tier 1 clinical/regulatory sources first; Tier 2 authoritative databases second.
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

For each category return YES, NO, UNKNOWN or CONFLICTING.
- YES requires positive evidence relevant to the material.
- NO requires evidence that genuinely supports a negative/absence conclusion, not merely silence.
- UNKNOWN means information is insufficient.
- CONFLICTING means credible sources materially disagree.

Preferred source order for hazard questions: Tier 1 regulatory toxicology/official assessments; Tier 2 ECHA/PubChem/official toxicology; Tier 3 peer-reviewed toxicology; Tier 4 SDS/manufacturer; Tier 5 only as support.
Do not research PDE values.
Return structured data only.
"""


def potency_prompt(material_name: str, routes: str, context: str) -> str:
    return f"""{GENERAL}\n{SOURCE_TIERS}
TASK: Determine the LOWEST TYPICAL DAILY THERAPEUTIC DOSE for {material_name} for potency screening.
Known route(s): {routes or 'not supplied'}
Manufacturing/product context: {context or 'not supplied'}

Use the lowest commonly prescribed therapeutic daily dose, not a loading dose, one-off procedural dose, accidental exposure, toxic dose or maximum dose. Prefer the relevant route used by the material/product.
Preferred sources: BNF and UK SmPC/eMC first; then EMA/FDA official prescribing information; then other recognised clinical sources.

Return a numeric mg/day only when the conversion is scientifically supported. If a source gives mL/day, %, drops, units, IU or another non-mass unit, convert to mg/day only when a reliable concentration/density/potency relationship is available and show the calculation. Otherwise set dose_available false and flag review.
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
- Solubility: recognised pharmacopoeia -> PubChem/ECHA/official databases -> peer-reviewed experimental literature -> manufacturer technical/SDS -> secondary databases.
- Physical cleanability: evidence describing the API/material's physical form, plus the actual material/product introduced to manufacture. If tablets are crushed or a suspension residue is expected, evaluate that real process material rather than only the pure API crystal.

70% IPA rules:
- Prefer direct 70% IPA or isopropanol evidence.
- Ethanol/alcohol evidence may support an INFERRED conclusion, but label it INFERRED and explain why.
- Consider that 70% IPA contains about 30% water; do not automatically equate ethanol solubility with 70% IPA solubility.

2% Decon rules:
- Prefer direct evidence if it exists.
- Direct 2% Decon data is often unavailable. Because the solution is aqueous, water-solubility behaviour may be used as supporting evidence for an INFERRED conclusion. Clearly label the inference.

When evidence does not justify a category, use REVIEW_REQUIRED rather than inventing a result.
Do not research PDE values.
Return structured data only.
"""
