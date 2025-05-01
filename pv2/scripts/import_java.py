#!/usr/bin/python3
# This takes a java import and creates a portable import. Portables are
# required to build the actual java package. We ensure that every release has
# its own portable.

import argparse
import pv2.importer as importutil

parser = argparse.ArgumentParser(description="Java Portable Importer")

parser.add_argument('--name', type=str, required=True)
parser.add_argument('--githost', type=str, required=True)
parser.add_argument('--gitorg', type=str, required=False, default='rpms')
parser.add_argument('--gituser', type=str, required=False, default='git')
parser.add_argument('--branch', type=str, required=False, default='')
parser.add_argument('--overwrite-tag', action='store_true')
results = parser.parse_args()

def main():
    """
    Run the import
    """
    classy = importutil.JavaPortableImport(
            package=results.name,
            source_git_host=results.githost,
            source_org=results.gitorg,
            source_branch=results.branch,
            source_git_user=results.gituser,
    )

    classy.pkg_import()

if __name__ == '__main__':
    main()
