import logging

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, connections
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request, version=None):
    backend = settings.CACHES["default"]["BACKEND"]
    cache_backend = "redis" if backend.endswith("redis.RedisCache") else "local-memory"
    cache_status = "connected"
    try:
        cache.set("health-check", "ok", timeout=5)
        if cache.get("health-check") != "ok":
            cache_status = "unavailable"
    except Exception:
        cache_status = "unavailable"
        logger.exception("Shared cache health check failed.")
    return Response({
        "status": "ok",
        "cache": {"backend": cache_backend, "status": cache_status},
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def database_health_check(request, version=None):
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.warning("Database health check failed.")
        return Response(
            {"status": "error", "database": "unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"status": "ok", "database": "ok"})
