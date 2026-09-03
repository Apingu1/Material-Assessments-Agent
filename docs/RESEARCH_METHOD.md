# Phase 1 Research & Completion Method

The agent prepares a draft ES.SOP.272.F01.V02 through the Section 6 PDE requirement decision and packages supporting evidence. It does not search for, calculate, estimate or infer a PDE/HBEL value from online information. If a PDE is recommended or mandatory, Section 7 remains pending for later completion from the approved internal toxicologist report.

## Source tiers

1. Regulatory / expert / official clinical: BNF, UK SmPC/eMC, MHRA, EMA, FDA and official regulatory assessments.
2. Authoritative scientific / pharmacopoeial: recognised pharmacopoeias, PubChem, ECHA and official chemical/toxicology databases.
3. Peer-reviewed literature: PubMed-indexed studies and recognised journals.
4. Manufacturer/supplier technical evidence: SDS, Thermo Fisher, Merck/Sigma and equivalent suppliers.
5. Secondary references: DrugBank, Drugs.com, MIMS and other recognised secondary references.

The preferred tier is question-specific. Clinical/regulatory sources are preferred for dose; pharmacopoeial/official scientific sources are preferred for solubility; regulatory toxicology and official hazard sources are preferred for intrinsic hazards.

## Hazard screening

Each intrinsic hazard is stored internally as YES, NO, UNKNOWN or CONFLICTING. Silence is not treated as NO. The form hazard score is the highest positive hazard; if no score 2-5 hazard is positively identified, Therapeutic Category Risk is the score-1 fallback and any unknown/conflicting findings are surfaced to the operator.

## Potency

The lowest typical daily therapeutic dose is converted to mg/day only when the evidence supports the conversion. Bands are: <=0.1 mg/day = 5; >0.1-1 = 4; >1-10 = 3; >10-100 = 2; >100 = 1. If a reliable mg/day value cannot be established, B and D remain pending rather than being invented.

## Cleanability

Water, 70% IPA and 2% Decon use scores 1/3/5 for freely soluble, slightly/moderately soluble and practically insoluble/very low solubility. 70% IPA may use ethanol/alcohol evidence only as an identified inference. 2% Decon may use aqueous behaviour as supporting evidence because the solution is aqueous, again marked as inferred. Physical cleanability scores crystalline/non-sticky/non-film-forming = 1, caking powder/suspension residue = 3 and oily/sticky/film-forming = 5. The actual introduced material/product context is considered, not only the isolated API.

Where a cleanability classification remains unsupported, a provisional intermediate score 3 is used in the draft and explicitly flagged for human review.

## Overall screening and PDE decision

D = A x B x C. D <=80 = PDE not required; 81-149 = PDE recommended; >=150 = PDE mandatory. Hard rules override thresholds: Genotoxicity/Mutagenicity selected -> PDE mandatory; Carcinogenicity selected with C >=12 -> PDE mandatory.

## Evidence packaging

Evidence is grouped as Appendix 1 Hazard, 2 Potency, 3 Water, 4 70% IPA, 5 2% Decon and 6 Physical Cleanability. PDF evidence is downloaded and the relevant page rendered/highlighted where possible. Web evidence is captured using Chromium/Playwright where possible. Failed automated capture is clearly identified so the operator can open the retained URL manually.

Every generated record remains a draft for full operator review.
