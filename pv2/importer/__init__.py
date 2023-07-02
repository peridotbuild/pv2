# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@rockylinux.org>
"""
Importer module

This assists packagers by taking input as srpm or git location, importing and
tagging it as appropriate.
"""

from .operation import Import, SrpmImport
