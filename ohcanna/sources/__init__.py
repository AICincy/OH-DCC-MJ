from ohcanna.sources.base import Source
from ohcanna.sources.bloom import BloomSource

REGISTRY: dict[str, type[Source]] = {
    BloomSource.name: BloomSource,
}
