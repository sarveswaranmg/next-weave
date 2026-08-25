"""Logging configuration"""
import logging
import sys
from neurowave_engine.core.config import settings

def setup_logging():
    """Configure application logging"""
    logger = logging.getLogger()
    logger.setLevel(settings.log_level)

    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(settings.log_level)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


logger = setup_logging()
