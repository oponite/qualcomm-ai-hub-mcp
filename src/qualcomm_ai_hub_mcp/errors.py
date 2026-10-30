"""Safe tool errors: classify SDK causes, never forward credential-bearing text."""

import json

import qai_hub as hub
import requests
from mcp.types import CallToolResult, TextContent
from qai_hub.client import RateLimitedError
from qai_hub.public_rest_api import APIException


class ConnectorError(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


def classify(exc):
    chain, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        chain.append(exc)
        exc = exc.__cause__ or exc.__context__
    for error in chain:
        if isinstance(error, ConnectorError):
            return error
        status = error.status_code if isinstance(error, APIException) else None
        if status in (401, 1000):
            return ConnectorError(
                "AUTHENTICATION", "Configure a valid Qualcomm API token or SDK profile."
            )
        if status == 403:
            return ConnectorError(
                "PERMISSION_DENIED", "The Qualcomm account cannot access this resource."
            )
        if status == 404:
            return ConnectorError(
                "NOT_FOUND", "The requested Qualcomm resource was not found."
            )
        if status == 429 or isinstance(error, RateLimitedError):
            return ConnectorError(
                "RATE_LIMITED", "Qualcomm rate limit reached; retry later.", True
            )
        if status is not None and status >= 500 and status < 600:
            return ConnectorError(
                "SERVICE_UNAVAILABLE", "Qualcomm service is unavailable.", True
            )
        if status is not None and 400 <= status < 500:
            return ConnectorError(
                "INVALID_INPUT", "Qualcomm rejected the operation parameters."
            )
    if any(isinstance(e, (TimeoutError, requests.exceptions.Timeout)) for e in chain):
        return ConnectorError(
            "TIMEOUT",
            "The operation timed out. Remote work may still be running.",
            True,
        )
    if any(isinstance(e, requests.exceptions.RequestException) for e in chain):
        return ConnectorError(
            "NETWORK_ERROR", "Cannot communicate with Qualcomm.", True
        )
    if any(isinstance(e, (ValueError, KeyError, FileNotFoundError)) for e in chain):
        return ConnectorError(
            "INVALID_INPUT",
            "Invalid parameter, unsupported operation, or unsafe file path.",
        )
    if any(isinstance(e, FileExistsError) for e in chain):
        return ConnectorError(
            "ALREADY_EXISTS", "The output path already exists; choose a new path."
        )
    if any(isinstance(e, hub.UserError) for e in chain):
        return ConnectorError(
            "SDK_USER_ERROR",
            "Qualcomm rejected the request. Check resource IDs and SDK parameters.",
        )
    return ConnectorError(
        "INTERNAL_ERROR",
        "The operation failed unexpectedly; no credentials or raw SDK errors are returned.",
    )


def error_result(exc, sensitive=False):
    error = classify(exc)
    retryable = error.retryable
    message = error.message
    if sensitive and error.code in (
        "TIMEOUT",
        "NETWORK_ERROR",
        "SERVICE_UNAVAILABLE",
        "INTERNAL_ERROR",
    ):
        retryable = False
        message += " Check existing jobs/resources before resubmitting; the remote change may have completed."
    record = {"error": {"code": error.code, "message": message, "retryable": retryable}}
    return CallToolResult(
        is_error=True,
        structured_content=record,
        content=[TextContent(text=json.dumps(record, allow_nan=False))],
    )
