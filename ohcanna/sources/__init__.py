from ohcanna.sources.base import Source
from ohcanna.sources.bloom import BloomSource
from ohcanna.sources.dutchie import DutchieSource
from ohcanna.sources.locals_cannabis import LocalsCannabisSource

# Bloom is production-verified. Dutchie and Locals are scaffolding validated
# against synthetic fixtures only — they need one live capture before
# production use (see each module's docstring and the Phase 2 PR notes).
REGISTRY: dict[str, type[Source]] = {
    BloomSource.name: BloomSource,
    DutchieSource.name: DutchieSource,
    LocalsCannabisSource.name: LocalsCannabisSource,
}
