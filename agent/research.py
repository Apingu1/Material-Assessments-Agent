from __future__ import annotations

import json
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from .config import Settings
from .models import (
    CleanabilityResearch,
    HazardResearch,
    IdentityResearch,
    MaterialInput,
    PotencyResearch,
    ResearchBundle,
)
from .prompts import cleanability_prompt, hazard_prompt, identity_prompt, potency_prompt

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

    def research(self, item: MaterialInput) -> ResearchBundle:
        identity = self._structured_web_research(
            identity_prompt(item.material_name, item.dosage_forms, item.routes, item.product_context),
            IdentityResearch,
            "material_identity",
        )
        hazard = self._structured_web_research(
            hazard_prompt(item.material_name, item.product_context),
            HazardResearch,
            "hazard_research",
        )
        potency = self._structured_web_research(
            potency_prompt(item.material_name, item.routes, item.product_context),
            PotencyResearch,
            "potency_research",
        )
        cleanability = self._structured_web_research(
            cleanability_prompt(item.material_name, item.dosage_forms, item.product_context),
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
