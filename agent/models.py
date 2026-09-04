from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Conclusion(str, Enum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"


class EvidenceStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    INFERRED = "INFERRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class HazardEvidenceStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT = "INSUFFICIENT"


class SourceType(str, Enum):
    REGULATORY = "REGULATORY"
    CLINICAL = "CLINICAL"
    PHARMACOPOEIAL = "PHARMACOPOEIAL"
    OFFICIAL_DATABASE = "OFFICIAL_DATABASE"
    PEER_REVIEWED = "PEER_REVIEWED"
    MANUFACTURER = "MANUFACTURER"
    SECONDARY = "SECONDARY"
    OTHER = "OTHER"


class EvidenceApplicability(str, Enum):
    EXACT_MATERIAL = "EXACT_MATERIAL"
    CHEMICAL_SPECIES = "CHEMICAL_SPECIES"
    ACTIVE_MOIETY = "ACTIVE_MOIETY"
    CLINICAL_FORMULATION = "CLINICAL_FORMULATION"
    PROCESS_CONTEXT = "PROCESS_CONTEXT"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceSource(StrictModel):
    title: str = Field(description="Exact page/document title")
    publisher: str = Field(description="Publisher or source organisation")
    url: str = Field(description="Exact URL returned by web research")
    tier: Literal[1, 2, 3]
    source_type: SourceType
    relevant_extract: str = Field(
        description="A short source extract, maximum about 25 words; do not invent wording"
    )
    interpretation: str = Field(
        description=(
            "Plain-language interpretation of how the source supports, contradicts, or limits "
            "the assessment. Do not mention evidence tiers, AI, agents, or research lanes."
        )
    )
    applicability: list[EvidenceApplicability] = Field(
        default_factory=list,
        description=(
            "Internal applicability tags identifying whether the source applies to the exact "
            "controlled material, chemical species, active moiety, clinical formulation, "
            "or process context."
        ),
    )


class IdentityResearch(StrictModel):
    canonical_material_name: str
    material_category: Literal[
        "API", "ACTIVE_INGREDIENT", "EXCIPIENT_FUNCTIONAL_MATERIAL", "OIL", "OTHER"
    ]
    dosage_forms: str
    routes_of_administration: str
    therapeutic_class: str
    context_notes: str
    chemical_identity: str = Field(
        default="",
        description=(
            "Chemical species relevant to physicochemical research, retaining meaningful salt/"
            "hydrate form but removing presentation and strength."
        ),
    )
    active_moiety: str = Field(
        default="",
        description=(
            "Therapeutically active identity used for clinical dose and therapeutic research, "
            "without strength or starting-material presentation."
        ),
    )
    synonyms: list[str] = Field(
        default_factory=list,
        description="Useful scientific/clinical synonyms and established alternative names.",
    )
    clinical_search_terms: list[str] = Field(
        default_factory=list,
        description=(
            "Broad clinical formulations/search terms appropriate to the stated route, not "
            "restricted to the Eaststone starting-material strength or presentation."
        ),
    )
    physicochemical_search_terms: list[str] = Field(
        default_factory=list,
        description=(
            "Search terms for chemical/solubility research based on the actual chemical species."
        ),
    )
    process_material_description: str = Field(
        default="",
        description=(
            "Concise description of what physically contacts manufacturing equipment, derived "
            "from the entered material plus manufacturing context."
        ),
    )
    population_basis: Literal[
        "ADULT_DEFAULT", "PAEDIATRIC", "NEONATAL", "MIXED", "UNSPECIFIED"
    ] = "ADULT_DEFAULT"
    sources: list[EvidenceSource]


class HazardItem(StrictModel):
    conclusion: Conclusion
    evidence_status: HazardEvidenceStatus
    rationale: str
    sources: list[EvidenceSource]


class HazardResearch(StrictModel):
    mutagenicity_genotoxicity: HazardItem
    carcinogenicity: HazardItem
    reproductive_developmental_toxicity: HazardItem
    sensitisation_potential: HazardItem
    overall_notes: str


class PotencyResearch(StrictModel):
    dose_available: bool
    lowest_typical_daily_dose_mg: float | None
    dose_statement: str
    route_used_for_dose: str
    dose_calculation: str
    evidence_status: EvidenceStatus
    review_note: str
    bnf_nice_checked: bool
    emc_checked: bool
    sources: list[EvidenceSource]


class SolubilityClass(str, Enum):
    FREELY_SOLUBLE = "FREELY_SOLUBLE"
    SLIGHT_MODERATE = "SLIGHT_MODERATE"
    PRACTICALLY_INSOLUBLE = "PRACTICALLY_INSOLUBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class PhysicalClass(str, Enum):
    CRYSTALLINE_NON_STICKY = "CRYSTALLINE_NON_STICKY"
    CAKING_SUSPENSION_RESIDUE = "CAKING_SUSPENSION_RESIDUE"
    OILY_STICKY_FILM_FORMING = "OILY_STICKY_FILM_FORMING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class SolubilityFinding(StrictModel):
    classification: SolubilityClass
    evidence_status: EvidenceStatus
    rationale: str
    review_note: str
    sources: list[EvidenceSource]


class PhysicalFinding(StrictModel):
    classification: PhysicalClass
    evidence_status: EvidenceStatus
    assessment_basis: str = Field(
        description=(
            "Whether the physical assessment is based on pure API or the material/product "
            "actually introduced to manufacture"
        )
    )
    rationale: str
    review_note: str
    sources: list[EvidenceSource]


class CleanabilityResearch(StrictModel):
    water: SolubilityFinding
    ipa70: SolubilityFinding
    decon2: SolubilityFinding
    physical: PhysicalFinding
    overall_notes: str


class EvidenceRescueResearch(StrictModel):
    supports_existing_conclusion: bool
    review_note: str
    sources: list[EvidenceSource]


class MaterialInput(StrictModel):
    material_name: str = Field(min_length=1, max_length=55)
    dosage_forms: str = Field(default="", max_length=55)
    routes: str = Field(default="", max_length=55)
    product_context: str = ""


class ScoringResult(StrictModel):
    hazard_score_a: int
    hazard_selected: str
    potency_score_b: int | None
    cleanability_score_c: int
    water_score: int
    ipa70_score: int
    decon2_score: int
    physical_score: int
    overall_screening_risk_d: int | None
    pde_requirement: Literal[
        "NOT_REQUIRED", "RECOMMENDED", "MANDATORY", "UNDETERMINED"
    ]
    hard_escalation_reason: str
    review_flags: list[str]


class ResearchBundle(StrictModel):
    material_input: MaterialInput
    identity: IdentityResearch
    hazard: HazardResearch
    potency: PotencyResearch
    cleanability: CleanabilityResearch
    scoring: ScoringResult | None = None
