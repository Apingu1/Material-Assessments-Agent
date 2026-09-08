from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class SDSMatchType(str, Enum):
    ACTUAL_SUPPLIER = "ACTUAL_SUPPLIER"
    REFERENCE_SUBSTANCE = "REFERENCE_SUBSTANCE"
    MIXTURE_OR_FORMULATION = "MIXTURE_OR_FORMULATION"
    UNCERTAIN = "UNCERTAIN"


class SDSResearch(StrictModel):
    title: str
    publisher: str
    url: str
    substance_name: str
    cas_number: str = ""
    product_number: str = ""
    revision_date: str = ""
    match_type: SDSMatchType
    identity_match_rationale: str
    currentness_note: str = ""


class WorkplaceExposureLimit(StrictModel):
    identified: bool
    value: str = ""
    source: str = ""
    note: str = ""


class COSHHHazardResearch(StrictModel):
    substance_name: str = Field(description="Base hazardous substance name for COSHH display")
    material_context: str = Field(description="Exact Eaststone material / use context")
    synonyms: list[str]
    cas_number: str
    physical_form: str
    colour: str = ""
    odour: str = ""
    signal_word: str = ""
    ghs_pictograms: list[str] = Field(
        description="GHS codes such as GHS07, GHS08. Return only applicable codes."
    )
    hazard_statements: list[str]
    precautionary_statements: list[str]
    inhalation_relevant: bool
    skin_relevant: bool
    eye_relevant: bool
    ingestion_relevant: bool
    first_aid_inhalation: str
    first_aid_skin: str
    first_aid_eye: str
    first_aid_ingestion: str
    accidental_release: str
    storage_handling: str
    environmental_precautions: str
    disposal: str
    firefighting_media: str
    glove_recommendation: str = ""
    eye_protection_recommendation: str = ""
    respiratory_protection_recommendation: str = ""
    engineering_controls_recommendation: str = ""
    health_surveillance_consideration: str
    workplace_exposure_limit: WorkplaceExposureLimit
    sds: SDSResearch
    review_flags: list[str]


class ActivityControl(StrictModel):
    area: str
    activity: str
    exposure_scenario: str
    controls: str
    initial_risk: RiskLevel
    residual_risk: RiskLevel
    review_required: bool = False


class COSHHAssessment(StrictModel):
    research: COSHHHazardResearch
    activities: list[ActivityControl]
    applicable_areas: list[str]
    draft_status: Literal["READY_FOR_HUMAN_REVIEW", "REVIEW_REQUIRED"]
    review_flags: list[str]
