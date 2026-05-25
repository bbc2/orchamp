"""
Logging configuration for the web application.
"""

import logging
import sys

LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",  # cyan
    logging.INFO: "\033[32m",  # green
    logging.WARNING: "\033[33m",  # yellow
    logging.ERROR: "\033[31m",  # red
    logging.CRITICAL: "\033[1;31m",  # bold red
}
RESET = "\033[0m"
DIM = "\033[2m"


class ColoredFormatter(logging.Formatter):
    def __init__(self, use_color: bool) -> None:
        super().__init__()
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        name = record.name
        message = record.getMessage()

        if self._use_color:
            color = LEVEL_COLORS.get(record.levelno, "")
            levelname = f"{color}{levelname}{RESET}"
            name = f"{DIM}{name}{RESET}"

        result = f"{levelname} {name}: {message}"

        if record.exc_info:
            result += f"\n{self.formatException(record.exc_info)}"

        return result


def configure_logging(log_level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(ColoredFormatter(use_color=sys.stdout.isatty()))
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Configure first-party loggers with the specified level
    for logger_name in ["orchamp", "orchamp_web", "orchamp_get"]:
        logging.getLogger(logger_name).setLevel(log_level)

    # Configure uvicorn loggers explicitly, except their level.
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.propagate = False
