"""Structured logging setup with request-id correlation context."""

import contextvars
import logging
import sys

# Context variable holding the correlation ID for the active request
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="system")


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the current request_id into the log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def setup_logging(log_level: str = "INFO") -> None:
    """Configure root logger with structured formatting and request ID injection."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | [%(request_id)s] | %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    root_logger.addHandler(handler)

    # Set specific third-party loggers to a reasonable level
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger instance with the given module name."""
    return logging.getLogger(name)
