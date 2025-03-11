"""
Parses repo metadata to get information. May be useful for getting general info
about a project's repository, like for generating a summary.
"""

#import os
#import createrepo_c as cr
from pv2.util import log as pvlog

__all__ = []

def _warning_cb(warning_type, message):
    pvlog.logger.warning("WARNING: %s", message)
    return True
