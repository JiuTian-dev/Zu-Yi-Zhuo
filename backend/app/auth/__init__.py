"""Authentication adapters owned by the application boundary."""

from .zhihu import (
    ZhihuOAuthConfig,
    ZhihuOAuthService,
    build_zhihu_oauth_service,
    register_zhihu_auth_routes,
)

__all__ = (
    "ZhihuOAuthConfig",
    "ZhihuOAuthService",
    "build_zhihu_oauth_service",
    "register_zhihu_auth_routes",
)
