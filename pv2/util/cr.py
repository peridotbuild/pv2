"""
Parses repo metadata to get information. May be useful for getting general info
about a project's repository, like for generating a summary.
"""

#import os
#import createrepo_c as cr

__all__ = []

def _warning_cb(warning_type, message):
    print(f"WARNING: {message}")
    return True
