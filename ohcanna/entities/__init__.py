"""Entity aggregation layer.

Pure data rollups over loaded product dicts: by brand, by processor
(legal entity / operating LLC), and by dispensary (location). No HTML.
"""
from __future__ import annotations

from .graph import (  # noqa: F401
    BrandRollup,
    ProcessorRollup,
    DispensaryRollup,
    UNKNOWN_PROCESSOR,
    slugify,
    rollup_by_brand,
    rollup_by_processor,
    rollup_by_dispensary,
    build_all_rollups,
    load_and_rollup,
)
from .dcc_registry import (  # noqa: F401
    DCCLicense,
    BrandProcessorLink,
    load_registry,
    diff_registries,
    load_brand_processor_map,
    resolve_processor,
)
