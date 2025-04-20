#!/usr/bin/python3
# This is called to import a module YAML. Currently only needed for Rocky Linux
# 8 and 9.

import argparse
import pv2.importer as importutil

parser = argparse.ArgumentParser(description="Importer")

parser.add_argument('--module', type=str, required=True)
parser.add_argument('--source-githost', type=str, required=True)
parser.add_argument('--source-gitorg', type=str, required=True)
parser.add_argument('--branch', type=str, required=True)
parser.add_argument('--dest-githost', type=str, required=True)
parser.add_argument('--dest-gitorg', type=str, required=False, default='modules')
parser.add_argument('--dest-branch', type=str, required=False, default='')
parser.add_argument('--release', type=str, required=False, default='')
results = parser.parse_args()

def main():
    """
    Run the import
    """
    classy = importutil.ModuleImport(
            results.module,
            source_git_host=results.source_githost,
            source_org=results.source_gitorg,
            dest_git_host=results.dest_githost,
            dest_org=results.dest_gitorg,
            release=results.release,
            branch=results.branch,
            dest_branch=results.dest_branch,
    )

    classy.module_import()

if __name__ == '__main__':
    main()
