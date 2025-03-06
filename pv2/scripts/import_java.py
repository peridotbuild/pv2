#!/usr/bin/python3
# This takes a java import and creates a portable import. Portables are
# required to build the actual java package. We ensure that every release has
# its own portable.

import argparse
import pv2.importer as importutil

parser = argparse.ArgumentParser(description="Java Portable Importer")

parser.add_argument('--name', type=str, required=True)
parser.add_argument('--giturl', type=str, required=True)
parser.add_argument('--gitorg', type=str, required=False, default='rpms')
parser.add_argument('--branch', type=str, required=False, default='')
results = parser.parse_args()

def main():
    """
    Run the import
    """
    classy = importutil.JavaPortableImport(
            results.name,
            git_url_path=results.giturl,
            org=results.gitorg,
            branch=results.branch,
    )

    classy.pkg_import()

if __name__ == '__main__':
    main()
