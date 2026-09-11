import logging
import uuid

from django.db import IntegrityError
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.response import Response

from .errors import BusinessError

logger = logging.getLogger("chihuitong")


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4()
        response = self.get_response(request)
        response["X-Request-ID"] = str(request.request_id)
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response


def exception_handler(exc, context):
    request_id = str(getattr(context["request"], "request_id", ""))
    if isinstance(exc, BusinessError):
        return Response(
            {"code": exc.code, "message": exc.message, "details": exc.details, "request_id": request_id},
            status=exc.status,
        )
    if isinstance(exc, IntegrityError):
        logger.warning("database_conflict request_id=%s", request_id)
        return Response({"code": "conflict", "message": "记录冲突，请刷新后重试", "request_id": request_id}, status=409)
    response = drf_exception_handler(exc, context)
    if response is not None:
        response.data = {"code": "invalid_request", "details": response.data, "request_id": request_id}
        return response
    logger.error("unhandled_error type=%s request_id=%s", type(exc).__name__, request_id)
    return Response({"code": "internal_error", "message": "处理失败，请提供请求编号联系平台", "request_id": request_id}, status=500)
