#!/usr/bin/python3
"""
Import a source RPM into a git forge using pv2
"""

import argparse
import pv2.importer as importutil

parser = argparse.ArgumentParser(description="Importer")

parser.add_argument('--giturl', type=str, required=True)
parser.add_argument('--branch', type=str, required=True)
parser.add_argument('--srpm', type=str, required=True)
parser.add_argument('--release', type=str, required=False, default='')
results = parser.parse_args()
# pylint: disable=line-too-long
classy = importutil.SrpmImport(git_url_path=results.giturl, srpm_path=results.srpm, branch=results.branch, release=results.release)
classy.pkg_import()
