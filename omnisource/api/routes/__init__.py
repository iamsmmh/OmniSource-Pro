"""API routes for OmniSource."""

from omnisource.api.routes.admin import router as admin_router
from omnisource.api.routes.analytics import router as analytics_router
from omnisource.api.routes.apps import router as apps_router
from omnisource.api.routes.categories import router as categories_router
from omnisource.api.routes.collections import router as collections_router
from omnisource.api.routes.developers import router as developers_router
from omnisource.api.routes.favorites import router as favorites_router
from omnisource.api.routes.feeds import router as feeds_router
from omnisource.api.routes.health import router as health_router
from omnisource.api.routes.integration import router as integration_router
from omnisource.api.routes.latest import router as latest_router
from omnisource.api.routes.platforms import router as platforms_router
from omnisource.api.routes.popular import router as popular_router
from omnisource.api.routes.recommendations import router as recommendations_router
from omnisource.api.routes.releases import router as releases_router
from omnisource.api.routes.search import router as search_router
from omnisource.api.routes.security import router as security_router
from omnisource.api.routes.stats import router as stats_router
from omnisource.api.routes.trending import router as trending_router
from omnisource.api.routes.trust import router as trust_router
from omnisource.api.routes.webhook_management import router as webhook_management_router
from omnisource.api.routes.webhooks import router as webhooks_router

__all__ = [
    "admin_router",
    "analytics_router",
    "apps_router",
    "categories_router",
    "collections_router",
    "developers_router",
    "favorites_router",
    "feeds_router",
    "health_router",
    "integration_router",
    "latest_router",
    "platforms_router",
    "popular_router",
    "recommendations_router",
    "releases_router",
    "search_router",
    "security_router",
    "stats_router",
    "trending_router",
    "trust_router",
    "webhook_management_router",
    "webhooks_router",
]
