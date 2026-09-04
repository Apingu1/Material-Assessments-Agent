# Phase 1 Research & Completion Method

The agent prepares a draft ES.SOP.272.F01.V02 through the Section 6 PDE requirement decision and packages supporting evidence. It does not search for, calculate, estimate or infer a PDE/HBEL value from online information. If a PDE is recommended or mandatory, Section 7 remains pending for later completion from the approved internal toxicologist report.

## Endpoint-specific material identity

The exact material entered by the user is the **controlled material name** and remains unchanged on F01. It is not automatically the correct scientific search term for every endpoint.

Before specialist research, the identity step resolves:

1. **Controlled material** - the exact Eaststone material name, including presentation/strength where entered.
2. **Chemical identity** - the chemical species used for physicochemical and solubility research. Strength and presentation terms such as `powder` or `10mg tablets` are removed, while a meaningful salt/hydrate/form is retained where it can affect properties.
3. **Active moiety** - the therapeutic active identity used for clinical dose and therapeutic research, without the Eaststone starting-material strength or presentation.
4. **Clinical search expansion** - route-appropriate clinical formulations and strengths that can support dosing evidence.
5. **Physicochemical search expansion** - established names/synonyms centred on the actual chemical species.
6. **Process material** - what physically contacts the manufacturing equipment in the Eaststone process.

Examples:

- `Levothyroxine Sodium Powder` remains the controlled name; physicochemical research should normally use **levothyroxine sodium**, while clinical dose research should use **levothyroxine** across appropriate oral formulations.
- `Haloperidol 10mg Tablets` remains the controlled name; hazard/dose research should use **haloperidol** and must not be restricted to the 10 mg strength, while physical cleanability can use the process fact that tablets are crushed/dispersed into a suspension.

Evidence sources receive internal applicability tags (`EXACT_MATERIAL`, `CHEMICAL_SPECIES`, `ACTIVE_MOIETY`, `CLINICAL_FORMULATION`, `PROCESS_CONTEXT`). These help curation choose evidence at the level where the property actually exists and are never printed in the appendix.

## Source tiers

Tier 1 contains the primary authoritative sources used by the research engine: BNF/NICE, UK eMC/SmPC, MHRA, British Pharmacopoeia, European Pharmacopoeia/EDQM, EMA, ECHA, PubChem, PubMed/PMC peer-reviewed literature, FDA/DailyMed and equivalent authoritative regulatory sources.

Tier 2 contains strong supporting evidence including DrugBank, other recognised national pharmacopoeias/official databases, manufacturer SDS and established manufacturer/supplier technical information.

Tier 3 contains other recognised secondary clinical/chemical references and reputable technical sources and is used only where stronger evidence is unavailable or for useful corroboration.

UK sources are preferred where evidence quality and relevance are otherwise equivalent. The tier is an internal research aid and is not printed in the assessment appendices. Appendix `Interpretation` text must also avoid system language such as evidence-tier labels, AI/agent wording or research-process commentary.

## Hazard screening

Each intrinsic hazard is stored internally as YES, NO, UNKNOWN or CONFLICTING. Silence is not treated as NO. PubMed/PMC is a mandatory Tier 1 hazard-search lane rather than a fallback.

Hazard research is performed against the resolved chemical species/active moiety and established synonyms rather than being restricted to the incoming strength or presentation. For salts/related forms, direct evidence for the actual chemical species is preferred where available, while parent-active evidence can be used where scientifically applicable and is tagged accordingly.

For each hazard the agent actively searches positive and negative evidence across regulatory, official database and peer-reviewed literature lanes. If credible Tier 1 positive evidence conflicts with credible Tier 1 reassuring evidence, the hazard is conservatively selected and the internal evidence status is recorded as CONFLICTING.

Sensitisation is not selected solely from SmPC hypersensitivity/anaphylaxis adverse-event wording. Explicit sensitiser classification, recognised study evidence, occupational evidence or equivalent toxicological evidence is preferred.

The research pool may contain several sources, but the dossier is curated: a supported positive hazard normally retains one strongest source; a material conflict may retain the strongest positive source plus the strongest conflicting source. The whole hazard appendix is capped and repetitive corroborating evidence is kept in assessment.json rather than appended.

## Potency

Clinical potency is researched against the **active medicinal ingredient**, not the Eaststone starting-material strength or presentation. The agent searches across relevant licensed/recognised formulations and strengths for the stated route.

BNF/NICE is the primary UK daily-dose lane and UK eMC/SmPC is the mandatory corroborating lane. Unless the supplied context explicitly identifies a paediatric or neonatal application, the default is the lowest routine **adult** therapeutic daily dose for the relevant route. Loading, one-off, titration-only, neonatal/paediatric, weight-based and exceptional/specialist-population doses are not automatically selected merely because they are numerically lower.

If BNF/NICE cannot be successfully checked, the review summary says so and the strongest available UK evidence is used. The appendix normally contains no more than two dose sources.

## Cleanability

Water, 70% IPA and 2% Decon use scores 1/3/5 for freely soluble, slightly/moderately soluble and practically insoluble/very low solubility. Physical cleanability scores crystalline/non-sticky/non-film-forming = 1, caking powder/suspension residue = 3 and oily/sticky/film-forming = 5.

### Chemical vs process identity

Water, IPA and Decon research uses the resolved **chemical species**: remove strength/presentation words that do not define chemical identity, but retain a meaningful salt/form. Physical cleanability instead prioritises the **real process material/residue** because crushed tablets, suspensions, oils and powders can behave differently from an isolated API crystal.

### Water

Prefer British/European Pharmacopoeia, then PubChem, regulatory quality data, PubMed/PMC experimental literature and Tier 2 sources. The appendix normally retains one strongest direct source.

### 70% IPA

Prefer direct 70% IPA or isopropanol/2-propanol evidence about the resolved chemical species. Ethanol/alcohol evidence may support a clearly labelled inference. Direct isopropanol evidence may be more relevant than a higher-tier source that only describes a different alcohol.

### 2% Decon

The assessment question is the solubility/behaviour of the assessed chemical species in 2% Decon 90. Decon 90 composition, surfactants, detergent ingredients, dilution instructions, product advertising and cleaning-agent characteristics are not evidence of material solubility and must not be used to justify the score.

The search order is:

1. direct assessed-material-in-Decon evidence;
2. if unavailable, assessed-material solubility/behaviour in relevant solvents such as water, isopropanol, ethanol, methanol or other documented solvent systems;
3. a clearly identified inference where the material-solvent evidence supports one;
4. REVIEW_REQUIRED where the material evidence remains insufficient.

A Decon manufacturer page is excluded from the evidence set unless its relevant finding specifically reports the assessed material's solubility or behaviour in that system.

### Physical cleanability

The real process material is assessed. User-supplied manufacturing context such as tablets being crushed and dispersed into a suspension may form the primary physical-cleanability basis, with product literature used only to corroborate the presentation where appropriate.

## Evidence rescue pass

The scientific research conclusion and the ability to capture a screenshot are treated separately. If a field has a draft conclusion/score but none of its preferred evidence can be verified/captured, the pipeline performs one targeted evidence-rescue pass.

The rescue pass:

- searches for an alternative authoritative source supporting the **same** conclusion;
- broadens aliases, strengths and clinical formulations where appropriate;
- uses the active ingredient for potency and the chemical species for solubility;
- uses process context for physical cleanability;
- retains the Decon cleaner-only exclusion;
- does not reverse/change the scientific conclusion merely to obtain a more capture-friendly source;
- returns no speculative source if the existing conclusion cannot be independently supported.

If rescue still produces no verified appendix evidence, the field remains explicitly flagged for operator review. Rescue metadata is kept in the evidence folder and is not printed in the appendix.

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

Publisher, source tier, applicability tags, capture status, capture notes and hosting-site commentary are retained only in machine-readable research metadata where useful and are not printed in the assessment dossier.

Every generated record remains a draft for full operator review.
