# Phase 1 Research & Completion Method

The agent prepares a draft ES.SOP.272.F01.V02 through the Section 6 PDE requirement decision and packages supporting evidence. It does not search for, calculate, estimate or infer a PDE/HBEL value from online information. If a PDE is recommended or mandatory, Section 7 remains pending for later completion from the approved internal toxicologist report.

## Source tiers

Tier 1 contains the primary authoritative sources used by the research engine: BNF/NICE, UK eMC/SmPC, MHRA, British Pharmacopoeia, European Pharmacopoeia/EDQM, EMA, ECHA, PubChem, PubMed/PMC peer-reviewed literature, FDA/DailyMed and equivalent authoritative regulatory sources.

Tier 2 contains strong supporting evidence including DrugBank, other recognised national pharmacopoeias/official databases, manufacturer SDS and established manufacturer/supplier technical information.

Tier 3 contains other recognised secondary clinical/chemical references and reputable technical sources and is used only where stronger evidence is unavailable or for useful corroboration.

UK sources are preferred where evidence quality and relevance are otherwise equivalent. The tier is an internal research aid and is not printed in the assessment appendices.

## Hazard screening

Each intrinsic hazard is stored internally as YES, NO, UNKNOWN or CONFLICTING. Silence is not treated as NO. PubMed/PMC is a mandatory Tier 1 hazard-search lane rather than a fallback.

For each hazard the agent actively searches positive and negative evidence across regulatory, official database and peer-reviewed literature lanes. If credible Tier 1 positive evidence conflicts with credible Tier 1 reassuring evidence, the hazard is conservatively selected and the internal evidence status is recorded as CONFLICTING.

Sensitisation is not selected solely from SmPC hypersensitivity/anaphylaxis adverse-event wording. Explicit sensitiser classification, recognised study evidence, occupational evidence or equivalent toxicological evidence is preferred.

The research pool may contain several sources, but the dossier is curated: a supported positive hazard normally retains one strongest source; a material conflict may retain the strongest positive source plus the strongest conflicting source. The whole hazard appendix is capped and repetitive corroborating evidence is kept in assessment.json rather than appended.

## Potency

BNF/NICE is the primary UK daily-dose lane and UK eMC/SmPC is the mandatory corroborating lane. The lowest commonly prescribed therapeutic daily dose is used for the relevant route. Loading, one-off, titration-only and exceptional/specialist-population doses are not automatically selected merely because they are numerically lower.

If BNF/NICE cannot be successfully checked, the review summary says so and the strongest available UK evidence is used. The appendix normally contains no more than two dose sources.

## Cleanability

Water, 70% IPA and 2% Decon use scores 1/3/5 for freely soluble, slightly/moderately soluble and practically insoluble/very low solubility. Physical cleanability scores crystalline/non-sticky/non-film-forming = 1, caking powder/suspension residue = 3 and oily/sticky/film-forming = 5. The actual introduced material/product context is considered, not only the isolated API.

### Water

Prefer British/European Pharmacopoeia, then PubChem, regulatory quality data, PubMed/PMC experimental literature and Tier 2 sources. The appendix normally retains one strongest direct source.

### 70% IPA

Prefer direct 70% IPA or isopropanol/2-propanol evidence about the assessed material. Ethanol/alcohol evidence may support a clearly labelled inference. Direct isopropanol evidence may be more relevant than a higher-tier source that only describes a different alcohol.

### 2% Decon

The assessment question is the solubility/behaviour of the assessed material in 2% Decon 90. Decon 90 composition, surfactants, detergent ingredients, dilution instructions, product advertising and cleaning-agent characteristics are not evidence of material solubility and must not be used to justify the score.

The search order is:

1. direct assessed-material-in-Decon evidence;
2. if unavailable, assessed-material solubility/behaviour in relevant solvents such as water, isopropanol, ethanol, methanol or other documented solvent systems;
3. a clearly identified inference where the material-solvent evidence supports one;
4. REVIEW_REQUIRED where the material evidence remains insufficient.

A Decon manufacturer page is excluded from the evidence set unless its relevant finding specifically reports the assessed material's solubility or behaviour in that system.

### Physical cleanability

The real process material is assessed. User-supplied manufacturing context such as tablets being crushed and dispersed into a suspension may form the primary physical-cleanability basis, with product literature used only to corroborate the presentation where appropriate.

## Overall screening and PDE decision

D = A x B x C. D <=80 = PDE not required; 81-149 = PDE recommended; >=150 = PDE mandatory. Hard rules override thresholds: Genotoxicity/Mutagenicity selected -> PDE mandatory; Carcinogenicity selected with C >=12 -> PDE mandatory.

## Evidence curation and packaging

Research remains broad in assessment.json, but the controlled dossier contains only the strongest, decision-relevant evidence that could be automatically verified and captured.

Typical appendix budgets are:

- Hazard: up to 5 evidence items, normally fewer.
- Potency: up to 2.
- Water: 1.
- 70% IPA: 1.
- 2% Decon: up to 2 only where needed for a material-solvent inference; existing captured evidence is cross-referenced where identical.
- Physical cleanability: 1.

Exact repeated evidence is cross-referenced rather than appended again. Failed, blocked, 403, 404 or irrelevant screenshots are not included in the dossier; technical diagnostics remain in the evidence folder. PubMed capture uses an official NCBI text fallback when the standard webpage blocks automated capture.

The visible appendix is intentionally simple and human-readable. It contains only:

- Source
- URL
- Relevant finding
- Interpretation
- Evidence (the verified source screenshot/page)

Publisher, source tier, capture status, capture notes and hosting-site commentary are retained only in machine-readable research metadata where useful and are not printed in the assessment dossier.

Every generated record remains a draft for full operator review.
