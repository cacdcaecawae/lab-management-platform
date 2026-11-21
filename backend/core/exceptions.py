"""Uniform API error body: {"code": str, "message": str, "errors"?: {field: [msg]}}."""

from rest_framework import exceptions
from rest_framework.views import exception_handler as drf_exception_handler


class Conflict(exceptions.APIException):
    status_code = 409
    default_detail = "资源冲突"
    default_code = "conflict"


class InsufficientStorage(exceptions.APIException):
    status_code = 507
    default_detail = "服务器磁盘剩余空间不足，暂时不能上传，请联系运维"
    default_code = "insufficient_storage"


class MailFailed(exceptions.APIException):
    status_code = 502
    default_detail = "邮件发送失败，请稍后再试"
    default_code = "mail_failed"


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> Django 500, logged
    if isinstance(exc, exceptions.ValidationError):
        errors = response.data if isinstance(response.data, dict) else {"non_field_errors": response.data}
        response.data = {"code": "validation_error", "message": "提交的数据有误", "errors": errors}
    else:
        detail = response.data.get("detail", "") if isinstance(response.data, dict) else response.data
        code = getattr(detail, "code", None) or getattr(exc, "default_code", "error")
        response.data = {"code": str(code), "message": str(detail)}
    return response
