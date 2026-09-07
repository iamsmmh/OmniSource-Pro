"""API routes for OmniSource."""

from omnisource.api.routes.apps import router as apps_router
from omnisource.api.routes.search import router as search_router
from omnisource.api.routes.releases import router as releases_router
from omnisource.api.routes.categories import router as categories_router
from omnisource.api.routes.platforms import router as platforms_router
from omnisource.api.routes.developers import router as developers_router
from omnisource.api.routes.trending import router as trending_router
from omnisource.api.routes.latest import router as latest_router
from omnisource.api.routes.stats import router as stats_router
from omnisource.api.routes.health import router as health_router
from omnisource.api.routes.feeds import router as feeds_router

__all__ = [
    "apps_router",
    "search_router",
    "releases_router",
    "categories_router",
    "platforms_router",
    "developers_router",
    "trending_router",
    "latest_router",
    "stats_router",
    "health_router",
    "feeds_router",
]
