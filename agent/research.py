from __future__ import annotations

import hashlib
import json
from typing import TypeVar
from pathlib import Path
import fitz

from openai import OpenAI
from pydantic import BaseModel

from .config import Settings
from .models import (
    COSHHResearch,
    CleanabilityResearch,
    EvidenceRescueResearch,
    HazardResearch,
    IdentityResearch,
    MaterialInput,
    PotencyResearch,
    ResearchBundle,
)
from .prompts import cleanability_prompt, coshh_prompt, coshh_rescue_prompt, hazard_prompt, identity_prompt, potency_prompt
from .rescue_prompts import source_family_rescue_prompt
from .sds import StoredSDS

T = TypeVar("T", bound=BaseModel)


def _safe_schema_name(value: str) -> str:
    """Keep OpenAI structured-output schema names within the 64-character API limit."""
    if len(value) <= 64:
        return value
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{value[:55]}_{digest}"


class ResearchAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def _structured_web_research(
        self, prompt: str, model_cls: type[T], schema_name: str, *, search_web: bool = True
    ) -> T:
        schema = model_cls.model_json_schema()
        api_schema_name = _safe_schema_name(schema_name)
        response = self.client.responses.create(
            model=self.settings.openai_model,
            tools=[{"type": "web_search"}] if search_web else [],
            input=prompt,
            reasoning={"effort": "medium"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": api_schema_name,
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        if not response.output_text:
            raise RuntimeError(f"Research model returned no output for {schema_name}")
        try:
            payload = json.loads(response.output_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Research model returned invalid structured JSON for {schema_name}: {exc}"
            ) from exc
        return model_cls.model_validate(payload)

    @staticmethod
    def _chemical_identity(identity: IdentityResearch) -> str:
        return identity.chemical_identity or identity.canonical_material_name

    @staticmethod
    def _active_moiety(identity: IdentityResearch) -> str:
        return identity.active_moiety or identity.chemical_identity or identity.canonical_material_name

    def research(self, item: MaterialInput) -> ResearchBundle:
        """Run the cleaning-validation research. COSHH is a separate pass so one failure cannot erase the other output."""
        identity = self._structured_web_research(
            identity_prompt(item.material_name, item.dosage_forms, item.routes, item.product_context),
            IdentityResearch,
            "material_identity",
        )
        chemical_identity = self._chemical_identity(identity)
        active_moiety = self._active_moiety(identity)

        hazard = self._structured_web_research(
            hazard_prompt(
                item.material_name,
                chemical_identity,
                active_moiety,
                identity.synonyms,
                item.product_context,
            ),
            HazardResearch,
            "hazard_research",
        )
        potency = self._structured_web_research(
            potency_prompt(
                item.material_name,
                active_moiety,
                identity.synonyms,
                identity.clinical_search_terms,
                item.routes or identity.routes_of_administration,
                item.product_context,
                identity.population_basis,
            ),
            PotencyResearch,
            "potency_research",
        )
        cleanability = self._structured_web_research(
            cleanability_prompt(
                item.material_name,
                chemical_identity,
                active_moiety,
                identity.synonyms,
                identity.physicochemical_search_terms,
                item.dosage_forms or identity.dosage_forms,
                item.product_context,
                identity.process_material_description,
            ),
            CleanabilityResearch,
            "cleanability_research",
        )
        return ResearchBundle(
            material_input=item,
            identity=identity,
            hazard=hazard,
            potency=potency,
            cleanability=cleanability,
        )

    def research_coshh(self, item: MaterialInput, identity: IdentityResearch) -> COSHHResearch:
        """Run the SDS-first COSHH research using the already-resolved material identity."""
        return self._structured_web_research(
            coshh_prompt(
                item.material_name,
                self._chemical_identity(identity),
                self._active_moiety(identity),
                identity.synonyms,
                identity.process_material_description,
                item.product_context,
            ),
            COSHHResearch,
            "coshh_research",
        )

    def research_coshh_from_verified_pdf(
        self,
        item: MaterialInput,
        identity: IdentityResearch,
        stored_sds: StoredSDS,
        *,
        reference: bool,
    ) -> COSHHResearch:
        """Extract classification from the PDF ACTUALLY saved, not a previous SDS.

        Supplier specificity is never inferred merely from a web document.
        """
        if stored_sds.status != "STORED_UNCHANGED":
            raise ValueError("An original SDS PDF must be saved before re-extraction")
        with fitz.open(stored_sds.local_path) as document:
            full_text = "\n\n".join(page.get_text(sort=True) for page in document)
        if len(full_text.strip()) < 300:
            raise ValueError("Downloaded SDS PDF did not yield sufficient extractable text")
        from .prompts import coshh_verified_pdf_prompt
        result = self._structured_web_research(
            coshh_verified_pdf_prompt(
                material_name=item.material_name,
                chemical_identity=self._chemical_identity(identity),
                active_moiety=self._active_moiety(identity),
                synonyms=identity.synonyms,
                process_material_description=identity.process_material_description,
                product_context=item.product_context,
                source_url=stored_sds.resolved_pdf_url,
                source_text=full_text[:65000],
            ),
            COSHHResearch,
            "coshh_verified_pdf_extraction",
            search_web=False,  # PDF is already supplied; don't pay for a web search.
        )
        # Anchor the factual output to the actual PDF bytes; avoid a model
        # returning a different or inaccessible URL.
        result.sds.url = stored_sds.resolved_pdf_url
        result.sds.source.url = stored_sds.resolved_pdf_url
        if reference:
            result.sds.match_status = "REFERENCE_SDS"
            result.sds.is_supplier_specific = False
            result.sds.match_rationale = (
                "Reference SDS downloaded from a third-party publisher; confirm "
                "the incoming material supplier and chemical/salt identity."
            )
        if not any(source.url == stored_sds.resolved_pdf_url for source in result.sources):
            result.sources.insert(0, result.sds.source)
        return result

    def research_coshh_alternative(
        self,
        item: MaterialInput,
        identity: IdentityResearch,
        existing: COSHHResearch,
        attempted_urls: list[str],
        lane: str,
    ) -> COSHHResearch:
        """Second/third SDS-specific web search, including a fresh hazard extraction."""
        return self._structured_web_research(
            coshh_rescue_prompt(
                material_name=item.material_name,
                chemical_identity=self._chemical_identity(identity),
                active_moiety=self._active_moiety(identity),
                synonyms=identity.synonyms,
                process_material_description=identity.process_material_description,
                product_context=item.product_context,
                expected_cas=existing.sds.cas_number,
                excluded_urls=attempted_urls,
                lane=lane,
            ),
            COSHHResearch,
            f"coshh_sds_rescue_{lane}",
        )

    def rescue_evidence_from_family(
        self,
        *,
        item: MaterialInput,
        identity: IdentityResearch,
        family: str,
        group: str,
        target_summary: str,
        existing_urls: list[str],
    ) -> EvidenceRescueResearch:
        """Search one fixed source family in the deterministic rescue waterfall."""
        safe_family = family.lower().replace("%", "pct").replace(" ", "_")
        safe_group = group.lower().replace("%", "pct").replace(" ", "_")
        return self._structured_web_research(
            source_family_rescue_prompt(
                family=family,
                group=group,
                material_name=item.material_name,
                chemical_identity=self._chemical_identity(identity),
                active_moiety=self._active_moiety(identity),
                synonyms=identity.synonyms,
                clinical_search_terms=identity.clinical_search_terms,
                physicochemical_search_terms=identity.physicochemical_search_terms,
                routes=item.routes or identity.routes_of_administration,
                context=item.product_context,
                target_summary=target_summary,
                existing_urls=existing_urls,
            ),
            EvidenceRescueResearch,
            f"evidence_rescue_{safe_group}_{safe_family}",
        )
