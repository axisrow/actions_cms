"""Find indexed articles whose title is too close to a proposed one."""
from __future__ import annotations

from difflib import SequenceMatcher

from .config import Site
from .content import load_index


def similar(site: Site, title: str, threshold: float = 0.75) -> list[tuple[float, dict]]:
    """(ratio, index entry) for every article at or above the threshold, closest first."""
    title = title.lower()
    hits = [
        (ratio, item) for item in load_index(site.index)
        if (ratio := SequenceMatcher(None, title, str(item["title"]).lower()).ratio()) >= threshold
    ]
    return sorted(hits, key=lambda hit: -hit[0])
