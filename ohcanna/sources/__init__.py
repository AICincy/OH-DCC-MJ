from ohcanna.sources.base import Source
from ohcanna.sources.bloom import BloomSource
from ohcanna.sources.dutchie import DutchieSource
from ohcanna.sources.klutch import KlutchSource
from ohcanna.sources.locals_cannabis import LocalsCannabisSource

# Bloom is production-verified. Dutchie, Locals, and Klutch are scaffolding
# validated against synthetic fixtures only — they need one live capture
# before production use (see each module's docstring and the Phase 2 PR
# notes). Klutch additionally does an N+1 per-product page fetch; tune its
# rate with the CLI --delay flag.
REGISTRY: dict[str, type[Source]] = {
    BloomSource.name: BloomSource,
    DutchieSource.name: DutchieSource,
    KlutchSource.name: KlutchSource,
    LocalsCannabisSource.name: LocalsCannabisSource,
}
