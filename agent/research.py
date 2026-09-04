from __future__ import annotations

import json
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from .config import Settings
from .models import (
    CleanabilityResearch,
    EvidenceRescueResearch,
    HazardResearch,
    IdentityResearch,
    MaterialInput,
    PotencyResearch,
    ResearchBundle,
)
from .prompts import cleanability_prompt, hazard_prompt, identity_prompt, potency_prompt
from .rescue_prompts import source_family_rescue_prompt

T = TypeVar("T", bound=BaseModel)


class ResearchAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def _structured_web_research(self, prompt: str, model_cls: type[T], schema_name: str) -> T:
        schema = model_cls.model_json_schema()
        response = self.client.responses.create(
            model=self.settings.openai_model,
            tools=[{"type": "web_search"}],
            input=prompt,
            reasoning={"effort": "medium"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
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
