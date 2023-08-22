#!/usr/bin/python3
# This is called to do imports, whether from an RPM or a git repo (e.g. CentOS
# stream gitlab)

import argparse
import pv2.importer as importutil

parser = argparse.ArgumentParser(description="Importer Utility")
subparser = parser.add_subparsers(dest='cmd')
subparser.required = True

rpm_parser = subparser.add_parser('rpm')
git_parser = subparser.add_parser('git')

rpm_parser.add_argument('--gituser', type=str, required=False, default='git')
rpm_parser.add_argument('--giturl', type=str, required=True)
rpm_parser.add_argument('--branch', type=str, required=True)
rpm_parser.add_argument('--srpm', type=str, required=True)
rpm_parser.add_argument('--release', type=str, required=False, default='')
rpm_parser.add_argument('--gitorg', type=str, required=False, default='rpms')
rpm_parser.add_argument('--distprefix', type=str, required=False, default='el')
rpm_parser.add_argument('--dest-lookaside', type=str, required=False, default='/var/www/html/sources')
rpm_parser.add_argument('--verify-signature', action='store_true')
rpm_parser.add_argument('--skip-lookaside-upload',
                        action='store_true',
                        help='Set this flag to skip uploading to /var/www/html/sources esque lookaside')

git_parser.add_argument('--name', type=str, required=True)
git_parser.add_argument('--source-gituser', type=str, required=False, default='git')
git_parser.add_argument('--source-giturl', type=str, required=True)
git_parser.add_argument('--source-gitorg', type=str, required=True)
git_parser.add_argument('--gituser', type=str, required=False, default='git')
git_parser.add_argument('--branch', type=str, required=True)
git_parser.add_argument('--giturl', type=str, required=True)
git_parser.add_argument('--gitorg', type=str, required=False, default='rpms')
git_parser.add_argument('--dest-branch', type=str, required=False, default='')
git_parser.add_argument('--release', type=str, required=False, default='')
git_parser.add_argument('--distprefix', type=str, required=False, default='el')
rpm_parser.add_argument('--dest-lookaside', type=str, required=False, default='/var/www/html/sources')
git_parser.add_argument('--upstream-lookaside',
                        choices=('rocky8', 'rocky', 'centos', 'stream', 'fedora'),
                        required=True)
git_parser.add_argument('--alternate-spec-name',
                        type=str, required=False,
                        default='',
                        help='ex: if kernel-rt, use kernel. only use if built-in finder is failing')
git_parser.add_argument('--skip-lookaside-upload',
                        action='store_true',
                        help='Set this flag to skip uploading to /var/www/html/sources esque lookaside')

results = parser.parse_args()
command = parser.parse_args().cmd

def main():
    if command == 'rpm':
        classy = importutil.SrpmImport(
                git_url_path=results.giturl,
                srpm_path=results.srpm,
                release=results.release,
                branch=results.branch,
                distprefix=results.distprefix,
                git_user=results.gituser,
                org=results.gitorg,
                dest_lookaside=results.dest_lookaside,
                verify_signature=results.verify_signature,
        )
        classy.pkg_import(skip_lookaside=results.skip_lookaside_upload)
    elif command == 'git':
        classy = importutil.GitImport(
                package=results.name,
                source_git_user=results.source_gituser,
                source_git_url_path=results.source_giturl,
                source_git_org_path=results.source_gitorg,
                git_user=results.gituser,
                git_url_path=results.giturl,
                org=results.gitorg,
                release=results.release,
                branch=results.branch,
                dest_branch=results.dest_branch,
                upstream_lookaside=results.upstream_lookaside,
                distprefix=results.distprefix,
                alternate_spec_name=results.alternate_spec_name,
                dest_lookaside=results.dest_lookaside,
        )
        classy.pkg_import(skip_lookaside=results.skip_lookaside_upload)
    else:
        print('Unknown command')

if __name__ == '__main__':
    main()
