from django.conf import settings
from django.db import connections
from django.http import JsonResponse
from redis import Redis


def liveness(_request):
    return JsonResponse({"status": "ok"})


def readiness(_request):
    unavailable = []
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        unavailable.append("database")

    try:
        Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=settings.HEALTHCHECK_TIMEOUT_SECONDS,
            socket_timeout=settings.HEALTHCHECK_TIMEOUT_SECONDS,
        ).ping()
    except Exception:
        unavailable.append("redis")

    if unavailable:
        return JsonResponse({"status": "unavailable", "dependencies": unavailable}, status=503)
    return JsonResponse({"status": "ready"})
