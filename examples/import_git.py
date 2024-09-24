#!/usr/bin/python3

import argparse
import pv2.importer as importutil

parser = argparse.ArgumentParser(description="Importer")

parser.add_argument('--srpm', type=str, required=True)
parser.add_argument('--source-giturl', type=str, required=True)
parser.add_argument('--source-gitorg', type=str, required=True)
parser.add_argument('--branch', type=str, required=True)
parser.add_argument('--giturl', type=str, required=True)
parser.add_argument('--gitorg', type=str, required=False, default='rpms')
parser.add_argument('--dest-branch', type=str, required=False, default='')
parser.add_argument('--release', type=str, required=False, default='')
parser.add_argument('--distprefix', type=str, required=False, default='el')
parser.add_argument('--distcustom', type=str, required=False, default='')
parser.add_argument('--upstream-lookaside', type=str, required=True)
parser.add_argument('--alternate-spec-name', type=str, required=False, default='', help='e.g. if kernel-rt, use kernel')
results = parser.parse_args()
classy = importutil.GitImport(
        results.srpm,
        source_git_url_path=results.source_giturl,
        source_git_org_path=results.source_gitorg,
        git_url_path=results.giturl,
        org=results.gitorg,
        release=results.release,
        branch=results.branch,
        dest_branch=results.dest_branch,
        upstream_lookaside=results.upstream_lookaside,
        distprefix=results.distprefix,
        distcustom=results.distcustom,
        alternate_spec_name=results.alternate_spec_name
)

classy.pkg_import()
