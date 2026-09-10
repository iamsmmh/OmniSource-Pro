"""Application relationship detection."""

from collections.abc import Iterable
from dataclasses import dataclass

from omnisource.processing.deduplication import jaccard


@dataclass
class DetectedRelationship:
    """A detected relationship between two applications."""

    from_slug: str
    to_slug: str
    relationship_type: str  # alternative_to | similar_to
    confidence: float
    method: str


def _token_set(tags: Iterable[str] | None, categories: Iterable[str] | None) -> set[str]:
    return {str(t).strip().lower() for t in (tags or [])} | {
        str(c).strip().lower() for c in (categories or [])
    }


class RelationshipDetector:
    """Detects similarity/alternative relationships between applications."""

    def __init__(
        self,
        similarity_threshold: float = 0.45,
        alternative_threshold: float = 0.75,
    ):
        self.similarity_threshold = similarity_threshold
        self.alternative_threshold = alternative_threshold

    def compare(
        self,
        app_a: dict,
        app_b: dict,
    ) -> DetectedRelationship | None:
        """Compare two application profiles and return a relationship if any."""
        tokens_a = _token_set(app_a.get("tags"), app_a.get("categories"))
        tokens_b = _token_set(app_b.get("tags"), app_b.get("categories"))

        overlap = jaccard(tokens_a, tokens_b)

        if overlap >= self.alternative_threshold:
            rel_type = "alternative_to"
            confidence = overlap
        elif overlap >= self.similarity_threshold:
            rel_type = "similar_to"
            confidence = overlap
        else:
            return None

        return DetectedRelationship(
            from_slug=app_a["slug"],
            to_slug=app_b["slug"],
            relationship_type=rel_type,
            confidence=round(confidence, 3),
            method="token_overlap",
        )

    def detect(self, apps: list[dict]) -> list[DetectedRelationship]:
        """Detect relationships among a list of application profiles."""
        relationships: list[DetectedRelationship] = []
        for i, app_a in enumerate(apps):
            for app_b in apps[i + 1 :]:
                rel = self.compare(app_a, app_b)
                if rel is not None:
                    relationships.append(rel)
        return relationships
