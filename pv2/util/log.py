# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Log functionality
"""

import sys
import logging

# pylint: disable=too-few-public-methods
class StdErrFilter(logging.Filter):
    """
    Filter stderr messages
    """
    def filter(self, record):
        return record.levelno in (logging.ERROR,
                                  logging.WARNING,
                                  logging.CRITICAL)

class StdOutFilter(logging.Filter):
    """
    Filter stdout messages
    """
    def filter(self, record):
        return record.levelno in (logging.DEBUG, logging.INFO)

logger = logging.getLogger("pv2 utility")

if not logger.hasHandlers():
    formatter = logging.Formatter(
            '%(asctime)s :: %(name)s :: %(message)s',
            '%Y-%m-%d %H:%M:%S'
    )

    logger.setLevel(logging.DEBUG)
    handler_out = logging.StreamHandler(sys.stdout)
    handler_out.setLevel(logging.DEBUG)
    handler_out.setFormatter(formatter)
    handler_out.addFilter(StdOutFilter())
    logger.addHandler(handler_out)

    handler_err = logging.StreamHandler(sys.stderr)
    handler_err.setLevel(logging.WARNING)
    handler_err.setFormatter(formatter)
    handler_err.addFilter(StdErrFilter())
    logger.addHandler(handler_err)
