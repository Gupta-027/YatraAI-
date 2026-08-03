"""All ORM models. Importing this package registers every table on ``Base``."""

from yatraai.db.base import Base
from yatraai.db.models.catalog import (
    Attraction,
    AttractionCost,
    AttractionSchedule,
    AttractionSource,
    DestinationCluster,
)
from yatraai.db.models.itinerary import (
    Feedback,
    Itinerary,
    ItineraryActivity,
    ItineraryDay,
    RecommendationScore,
)
from yatraai.db.models.knowledge import (
    ChunkEmbedding,
    DocumentChunk,
    RagEvaluation,
    SourceDocument,
)
from yatraai.db.models.location import LocationPoint, LocationSharingSession, SosAlert
from yatraai.db.models.ops import (
    AnalyticsEvent,
    AuditLog,
    ModelRun,
    PipelineRun,
    RouteCacheEntry,
    ServiceCallLog,
    WeatherSnapshot,
)
from yatraai.db.models.trip import (
    ChangeProposal,
    ChatMessage,
    MemberPreference,
    Trip,
    TripMember,
    Vote,
)
from yatraai.db.models.user import User

__all__ = [
    "AnalyticsEvent",
    "Attraction",
    "AttractionCost",
    "AttractionSchedule",
    "AttractionSource",
    "AuditLog",
    "Base",
    "ChangeProposal",
    "ChatMessage",
    "ChunkEmbedding",
    "DestinationCluster",
    "DocumentChunk",
    "Feedback",
    "Itinerary",
    "ItineraryActivity",
    "ItineraryDay",
    "LocationPoint",
    "LocationSharingSession",
    "MemberPreference",
    "ModelRun",
    "PipelineRun",
    "RagEvaluation",
    "RecommendationScore",
    "RouteCacheEntry",
    "ServiceCallLog",
    "SosAlert",
    "SourceDocument",
    "Trip",
    "TripMember",
    "User",
    "Vote",
    "WeatherSnapshot",
]
