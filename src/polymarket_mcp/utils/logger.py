from __future__ import annotations

import logging
import re

_SENSITIVE_KEYS = (
    "private_key",
    "api_key",
    "api_secret",
    "passphrase",
    "authorization",
)


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = str(record.getMessage())
        for key in _SENSITIVE_KEYS:
            pattern = rf"({key}\s*[=:]\s*)([^\s,;]+)"
            message = re.sub(pattern, r"\1***REDACTED***", message, flags=re.IGNORECASE)
        record.msg = message
        record.args = ()
        return True


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("polymarket_mcp")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        handler.addFilter(RedactionFilter())
        logger.addHandler(handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    already_redacted = any(isinstance(f, RedactionFilter) for f in logger.filters)
    if not already_redacted:
        logger.addFilter(RedactionFilter())
    return logger
