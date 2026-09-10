"""
Logging configuration for OmniSource.

Provides structured JSON logging with configurable levels and formats.
"""

import logging
import sys
from datetime import datetime
from typing import Any

from pythonjsonlogger import jsonlogger


class OmniSourceJSONFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for OmniSource logs."""

    def add_fields(
        self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]
    ) -> None:
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)

        # Add standard fields
        log_record["timestamp"] = datetime.utcnow().isoformat() + "Z"
        log_record["level"] = record.levelname
        log_record["logger"] = record.name

        # Add custom OmniSource fields if available
        for field in [
            "service",
            "job_id",
            "source",
            "repository",
            "application_id",
            "operation",
            "duration",
            "status",
            "error_code",
        ]:
            if hasattr(record, field):
                log_record[field] = getattr(record, field)

        # Render any traceback into a string so it survives serialization.
        rendered_exc = self.formatException(record.exc_info) if record.exc_info else None

        # Remove standard LogRecord attributes that duplicate the message.
        # The rendered ``message`` field is intentionally kept.
        for attr in [
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
        ]:
            log_record.pop(attr, None)

        if rendered_exc is not None:
            log_record["exc_info"] = rendered_exc


def setup_logging(log_level: str = "INFO", json_format: bool = True) -> None:
    """
    Configure logging for OmniSource.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to use JSON format (True) or text format (False)
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create formatter
    formatter: logging.Formatter
    if json_format:
        formatter = OmniSourceJSONFormatter(fmt="%(timestamp)s %(level)s %(logger)s %(message)s")
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set levels for noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class StructuredLogger:
    """A logger that supports structured logging with extra fields."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _log(
        self, level: int, message: str, extra: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        """Log a message with extra fields."""
        extra_fields = extra or {}
        extra_fields.update(kwargs)

        if extra_fields:
            self._logger.log(level, message, extra=extra_fields)
        else:
            self._logger.log(level, message)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, **kwargs)

    def exception(self, message: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, **kwargs)
        # Note: exception() is a special case that includes traceback
        # We need to handle this differently
        self._logger.exception(message, extra=kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, message, **kwargs)


def get_structured_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger with the given name.

    Args:
        name: Logger name

    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(get_logger(name))
