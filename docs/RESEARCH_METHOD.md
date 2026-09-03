# Phase 1 Research & Completion Method

The agent prepares a draft ES.SOP.272.F01.V02 through the Section 6 PDE requirement decision and packages supporting evidence. It does not search for, calculate, estimate or infer a PDE/HBEL value from online information. If a PDE is recommended or mandatory, Section 7 remains pending for later completion from the approved internal toxicologist report.

## Source tiers

### Tier 1 - primary authoritative evidence

Prefer UK evidence where equivalent information is available. Tier 1 includes BNF/NICE, UK eMC/SmPC, MHRA, British Pharmacopoeia, European Pharmacopoeia/EDQM, EMA, ECHA, PubChem, PubMed/PMC peer-reviewed literature, FDA/DailyMed and equivalent authoritative regulatory sources.

### Tier 2 - strong supporting evidence

DrugBank, other recognised national pharmacopoeias/official databases, manufacturer SDS, and established manufacturer/supplier technical information.

### Tier 3 - secondary/supporting evidence

Other recognised secondary clinical/chemical references and reputable technical sources. Use when Tier 1/2 evidence is unavailable or as corroboration.

UK preference sits above tier numbering: where two sources answer the same question equally well, prefer the UK source. This does not prohibit international Tier 1 evidence.

## Question-specific priority

- Daily dose: BNF/NICE is the primary lane; UK eMC/SmPC is mandatory corroboration. Other Tier 1 evidence follows when needed.
- Hazard/toxicology: research must deliberately cover regulatory evidence, PubChem/ECHA/official toxicology evidence, and PubMed/PMC peer-reviewed literature. PubMed is not a fallback.
- Solubility: British/European Pharmacopoeia -> PubChem -> MHRA/EMA quality documentation -> PubMed experimental evidence -> DrugBank/other Tier 2 -> manufacturer technical/SDS -> Tier 3.
- Physical cleanability: prioritise the actual material/product introduced to manufacture, not merely isolated API crystal data.

## Hazard evidence hardening

The hazard search is adversarial rather than confirmatory. For each category the agent searches both positive and negative evidence and uses multiple relevant search terms. For genotoxicity this includes terms such as mutagenicity, mutagenic, genotoxicity, chromosome aberration, micronucleus, DNA damage and Ames.

If credible Tier 1 positive evidence exists and credible Tier 1 negative/reassuring evidence also exists, the hazard is conservatively selected YES for scoring and its evidence status is recorded as CONFLICTING. The rationale must explain both sides and retain both source types. A Tier 1 positive hazard must not be ignored simply because another Tier 1 source is reassuring.

Silence is not treated as NO. UNKNOWN/INSUFFICIENT is used where evidence cannot support a conclusion.

### Sensitisation

Clinical SmPC wording such as hypersensitivity or anaphylaxis is supporting information but does not by itself prove sensitisation potential. A positive sensitisation conclusion should preferably be supported by explicit skin/respiratory sensitiser classification, H317/H334 or equivalent, a recognised sensitisation study, occupational sensitisation evidence, or an explicit regulatory/toxicological description as a sensitiser.

## Potency

BNF/NICE is checked first and UK eMC/SmPC is checked as a mandatory corroborating lane. The agent uses the lowest commonly prescribed therapeutic daily dose for the relevant route.

A numerically lower eMC dose is used only when it represents a genuine routine therapeutic regimen. Loading doses, one-off doses, titration-only values and exceptional/specialist-population regimens are not automatically used merely because they are lower. Material disagreement between BNF/NICE and eMC is surfaced for operator review.

Dose is converted to mg/day only when scientifically supported. Otherwise B and D remain pending rather than being invented.

## Cleanability

Water, 70% IPA and 2% Decon use scores 1/3/5 for freely soluble, slightly/moderately soluble and practically insoluble/very low solubility. 70% IPA may use ethanol/alcohol evidence only as an identified inference. 2% Decon may use aqueous behaviour as supporting evidence because the solution is aqueous, again marked as inferred.

Physical cleanability scores crystalline/non-sticky/non-film-forming = 1, caking powder/suspension residue = 3 and oily/sticky/film-forming = 5. The real introduced material/product context is considered, including crushed tablets or expected suspension residue.

Where a cleanability classification remains unsupported, a provisional intermediate score 3 is used in the draft and explicitly flagged for human review.

## Overall screening and PDE decision

D = A x B x C. D <=80 = PDE not required; 81-149 = PDE recommended; >=150 = PDE mandatory. Hard rules override thresholds: Genotoxicity/Mutagenicity selected -> PDE mandatory; Carcinogenicity selected with C >=12 -> PDE mandatory.

## Section 1 display rules

Each populated Section 1 text field is limited to 55 characters. The Material/API Name is exactly the user-entered material name and is never expanded with manufacturing context. Dosage form, route and therapeutic class are kept concise. Manufacturing context remains available to the research engine and evidence record.

## Evidence packaging

Evidence is grouped as Appendix 1 Hazard, 2 Potency, 3 Water, 4 70% IPA, 5 2% Decon and 6 Physical Cleanability. Appendix text is Arial and uses the label `Interpretation`, not `Agent interpretation`.

PDF evidence is downloaded and the relevant page is located using exact and fuzzy text matching. If the relevant page cannot be located, no arbitrary first page is appended. Web evidence is captured using Chromium/Playwright. Codespaces must install Chromium with Linux dependencies using `playwright install --with-deps chromium`.

Technical Playwright/browser logs are written only to diagnostic files in the evidence folder. They are never inserted into the dossier. The dossier receives a concise capture note only.

Every generated record remains a draft for full operator review.
