# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

#import os
#import re
#import shutil
#import string
#import datetime
#from pv2.util import gitutil, fileutil, rpmutil, processor, generic
#from pv2.util import error as err
#from pv2.util import constants as const
#from pv2.util import uploader as upload
from . import Import

__all__ = ['SourceCodeImport']
# todo: add in logging and replace print with log

class SourceCodeImport(Import):
    """
    Grabs source code of a package and imports it to a separate org/repo for
    code only.
    """
    # pylint: disable=too-many-arguments
    def __init__(
            self,
            pkg_name: str,
            git_url_path: str,
            branch: str,
            git_user: str = 'git',
            org: str = 'src',
    ):
        print()
