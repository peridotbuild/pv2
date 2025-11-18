#!/usr/bin/python3
# Performs srpmproc imports. Replaces the old golang written binary.

import argparse
from pv2.srpmproc.rpm import RpmImport as srpmproc
from pv2.srpmproc.module import ModuleImport as srpmproc_module

parser = argparse.ArgumentParser(description='Srpmproc Utility')
subparser = parser.add_subparsers(dest='cmd')
subparser.required = True

rpm_parser = subparser.add_parser('rpm')
module_parser = subparser.add_parser('module')

# rpm basics
rpm_parser.add_argument('--name', type=str, required=True)
rpm_parser.add_argument('--release', type=str, required=True)

# module basics
module_parser.add_argument('--module', type=str, required=True)
module_parser.add_argument('--stream', type=str, required=True)
module_parser.add_argument('--release', type=str, required=True)

# Source
rpm_parser.add_argument('--source-git-protocol', type=str, required=False, default='https')
rpm_parser.add_argument('--source-git-user', type=str, required=False, default='git')
rpm_parser.add_argument('--source-git-host', type=str, required=True)
rpm_parser.add_argument('--source-git-org', type=str, required=True)
rpm_parser.add_argument('--source-branch', type=str, required=False)
rpm_parser.add_argument('--source-branch-prefix', type=str, required=False,
                        default='c')
rpm_parser.add_argument('--source-branch-suffix', type=str, required=False,
                        default='')

module_parser.add_argument('--source-git-protocol', type=str, required=False, default='https')
module_parser.add_argument('--source-git-user', type=str, required=False, default='git')
module_parser.add_argument('--source-git-host', type=str, required=True)
module_parser.add_argument('--source-git-org', type=str, required=True)
module_parser.add_argument('--source-branch', type=str, required=False)
module_parser.add_argument('--source-branch-prefix', type=str, required=False,
                        default='c')
module_parser.add_argument('--source-branch-suffix', type=str, required=False,
                        default='')

# Destination
rpm_parser.add_argument('--dest-git-protocol', type=str, required=False, default='ssh')
rpm_parser.add_argument('--dest-git-user', type=str, required=False, default='git')
rpm_parser.add_argument('--dest-git-host', type=str, required=True)
rpm_parser.add_argument('--dest-git-org', type=str, required=False, default='rpms')
rpm_parser.add_argument('--dest-branch', type=str, required=False)
rpm_parser.add_argument('--dest-branch-prefix', type=str, required=False,
                        default='r')
rpm_parser.add_argument('--dest-branch-suffix', type=str, required=False,
                        default='')
rpm_parser.add_argument('--dest-patch-org', type=str, required=False,
                        default='patch')

module_parser.add_argument('--dest-git-protocol', type=str, required=False, default='ssh')
module_parser.add_argument('--dest-git-user', type=str, required=False, default='git')
module_parser.add_argument('--dest-git-host', type=str, required=True)
module_parser.add_argument('--dest-git-org', type=str, required=False, default='modules')
module_parser.add_argument('--dest-rpm-org', type=str, required=False, default='rpms')
module_parser.add_argument('--dest-branch', type=str, required=False)
module_parser.add_argument('--dest-branch-prefix', type=str, required=False,
                        default='r')
module_parser.add_argument('--dest-branch-suffix', type=str, required=False,
                        default='')

# Metadata
rpm_parser.add_argument('--distprefix', type=str, required=False, default='el')
rpm_parser.add_argument('--distcustom', type=str, required=False, default=None)
rpm_parser.add_argument('--overwrite-tag', action='store_true')
module_parser.add_argument('--overwrite-tag', action='store_true')
rpm_parser.add_argument('--skip-sources', action='store_false')
rpm_parser.add_argument('--preconv-names', action='store_true', help='Convert + to plus first')

# AWS
rpm_parser.add_argument('--aws-access-key-id', type=str, required=False, default=None)
rpm_parser.add_argument('--aws-access-key', type=str, required=False, default=None)
rpm_parser.add_argument('--aws-bucket', type=str, required=False, default=None)
rpm_parser.add_argument('--aws-use-ssl', action='store_true')
rpm_parser.add_argument('--aws-region', type=str, required=False, default=None)


results = parser.parse_args()
command = parser.parse_args().cmd

def main():
    """
    Run the main program
    """
    returned = None
    if command == 'rpm':
        classy = srpmproc(
                package=results.name,
                release=results.release,
                source_git_protocol=results.source_git_protocol,
                source_git_user=results.source_git_user,
                source_git_host=results.source_git_host,
                source_org=results.source_git_org,
                source_branch=results.source_branch,
                source_branch_prefix=results.source_branch_prefix,
                source_branch_suffix=results.source_branch_suffix,
                dest_git_protocol=results.dest_git_protocol,
                dest_git_user=results.dest_git_user,
                dest_git_host=results.dest_git_host,
                dest_org=results.dest_git_org,
                dest_branch=results.dest_branch,
                dest_branch_prefix=results.dest_branch_prefix,
                dest_branch_suffix=results.dest_branch_suffix,
                patch_org=results.dest_patch_org,
                distprefix=results.distprefix,
                distcustom=results.distcustom,
                aws_access_key_id=results.aws_access_key_id,
                aws_access_key=results.aws_access_key,
                aws_bucket=results.aws_bucket,
                aws_use_ssl=results.aws_use_ssl,
                overwrite_tags=results.overwrite_tag,
                skip_sources=results.skip_sources,
                preconv_names=results.preconv_names,
        )
        returned = classy.pkg_import()
    elif command == 'module':
        classy = srpmproc_module(
                module=results.module,
                stream=results.stream,
                release=results.release,
                source_git_protocol=results.source_git_protocol,
                source_git_user=results.source_git_user,
                source_git_host=results.source_git_host,
                source_org=results.source_git_org,
                source_branch=results.source_branch,
                source_branch_prefix=results.source_branch_prefix,
                source_branch_suffix=results.source_branch_suffix,
                dest_git_protocol=results.dest_git_protocol,
                dest_git_user=results.dest_git_user,
                dest_git_host=results.dest_git_host,
                dest_org=results.dest_git_org,
                rpm_org=results.dest_rpm_org,
                dest_branch=results.dest_branch,
                dest_branch_prefix=results.dest_branch_prefix,
                dest_branch_suffix=results.dest_branch_suffix,
                overwrite_tags=results.overwrite_tag,
        )
        returned = classy.pkg_import()

    else:
        print('Unknown command')

    print(returned)

if __name__ == '__main__':
    main()
