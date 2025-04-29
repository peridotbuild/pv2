# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Models for returners
"""

from dataclasses import dataclass

@dataclass
class ImportMetadata:
    """
    Metadata on imports
    """
    branch_commits: dict
    branch_versions: dict
    package_checksum: str
