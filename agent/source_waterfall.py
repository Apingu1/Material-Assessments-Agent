from __future__ import annotations


_SOURCE_WATERFALLS: dict[str, tuple[str, ...]] = {
    # BNF/NICE is already the primary research lane. Automated BNF capture can be
    # blocked, so evidence rescue deliberately starts with capture-friendly UK
    # alternatives before moving outside the UK.
    "Potency": (
        "NICE_GUIDANCE",
        "EMC_SMPC",
        "MHRA_EMA",
        "FDA_DAILYMED",
        "OTHER_TIER1",
    ),
    "Water Solubility": (
        "BRITISH_EUROPEAN_PHARMACOPOEIA",
        "PUBCHEM",
        "PUBMED_PMC",
        "DRUGBANK",
        "MANUFACTURER_TECHNICAL",
    ),
    "70% IPA Solubility": (
        "BRITISH_EUROPEAN_PHARMACOPOEIA",
        "PUBCHEM",
        "PUBMED_PMC",
        "DRUGBANK",
        "MANUFACTURER_TECHNICAL",
    ),
    "2% Decon Solubility": (
        "DIRECT_MATERIAL_DECON",
        "BRITISH_EUROPEAN_PHARMACOPOEIA",
        "PUBCHEM",
        "PUBMED_PMC",
        "DRUGBANK",
        "MANUFACTURER_TECHNICAL",
    ),
    "Physical Cleanability": (
        "PROCESS_PRODUCT_INFORMATION",
        "EMC_SMPC",
        "FDA_DAILYMED",
        "MANUFACTURER_TECHNICAL",
    ),
    "Hazard": (
        "UK_EU_REGULATORY",
        "PUBCHEM_ECHA",
        "PUBMED_PMC",
        "MANUFACTURER_SDS",
    ),
}


def rescue_source_families(group: str) -> tuple[str, ...]:
    """Return the fixed source-family order used when appendix evidence capture fails."""
    return _SOURCE_WATERFALLS.get(group, ("OTHER_TIER1",))
