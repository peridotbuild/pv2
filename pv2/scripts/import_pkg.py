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

rpm_parser.add_argument('--dest-gituser', type=str, required=False, default='git')
rpm_parser.add_argument('--dest-githost', type=str, required=True)
rpm_parser.add_argument('--dest-branch', type=str, required=True)
rpm_parser.add_argument('--srpm', type=str, required=True)
rpm_parser.add_argument('--release', type=str, required=False, default='')
rpm_parser.add_argument('--preconv-names', action='store_true', help='Convert + to plus first')
rpm_parser.add_argument('--dest-gitorg', type=str, required=False, default='rpms')
rpm_parser.add_argument('--distprefix', type=str, required=False, default='el')
rpm_parser.add_argument('--distcustom', type=str, required=False)
rpm_parser.add_argument('--dest-lookaside', type=str, required=False, default='/var/www/html/sources')
rpm_parser.add_argument('--no-verify-signature', action='store_true')
rpm_parser.add_argument('--skip-lookaside-upload',
                        action='store_true',
                        help='Set this flag to skip uploading to /var/www/html/sources esque lookaside')
rpm_parser.add_argument('--upload-to-s3', action='store_true')
rpm_parser.add_argument('--aws-access-key-id', type=str, required=False, default=None)
rpm_parser.add_argument('--aws-access-key', type=str, required=False, default=None)
rpm_parser.add_argument('--aws-bucket', type=str, required=False, default=None)
rpm_parser.add_argument('--aws-use-ssl', type=str, required=False, default=False)
rpm_parser.add_argument('--aws-region', type=str, required=False, default=None)

git_parser.add_argument('--name', type=str, required=True)
git_parser.add_argument('--source-gituser', type=str, required=False, default='git')
git_parser.add_argument('--source-githost', type=str, required=True)
git_parser.add_argument('--source-gitorg', type=str, required=True)
git_parser.add_argument('--source-branch', type=str, required=True)
git_parser.add_argument('--dest-gituser', type=str, required=False, default='git')
git_parser.add_argument('--dest-githost', type=str, required=True)
git_parser.add_argument('--dest-gitorg', type=str, required=False, default='rpms')
git_parser.add_argument('--dest-branch', type=str, required=False, default='')
git_parser.add_argument('--release', type=str, required=False, default='')
git_parser.add_argument('--preconv-names', action='store_true', help='Convert + to plus first')
git_parser.add_argument('--distprefix', type=str, required=False, default='el')
git_parser.add_argument('--distcustom', type=str, required=False)
git_parser.add_argument('--dest-lookaside', type=str, required=False, default='/var/www/html/sources')
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
git_parser.add_argument('--upload-to-s3', action='store_true')
git_parser.add_argument('--aws-access-key-id', type=str, required=False, default=None)
git_parser.add_argument('--aws-access-key', type=str, required=False, default=None)
git_parser.add_argument('--aws-bucket', type=str, required=False, default=None)
git_parser.add_argument('--aws-use-ssl', type=str, required=False, default=False)
git_parser.add_argument('--aws-region', type=str, required=False, default=None)

results = parser.parse_args()
command = parser.parse_args().cmd

def main():
    """
    Run the main program. Callable via poetry or __main__
    """
    if command == 'rpm':
        classy = importutil.SrpmImport(
                dest_git_host=results.dest_githost,
                srpm_path=results.srpm,
                release=results.release,
                preconv_names=results.preconv_names,
                dest_branch=results.dest_branch,
                distprefix=results.distprefix,
                distcustom=results.distcustom,
                dest_git_user=results.dest_gituser,
                dest_org=results.dest_gitorg,
                dest_lookaside=results.dest_lookaside,
                verify_signature=results.no_verify_signature,
                aws_access_key_id=results.aws_access_key_id,
                aws_access_key=results.aws_access_key,
                aws_bucket=results.aws_bucket,
                aws_region=results.aws_region,
                aws_use_ssl=results.aws_use_ssl,
                skip_lookaside=results.skip_lookaside_upload,
                s3_upload=results.upload_to_s3,
        )
        classy.pkg_import()
    elif command == 'git':
        classy = importutil.GitImport(
                package=results.name,
                source_git_user=results.source_gituser,
                source_git_host=results.source_githost,
                source_org=results.source_gitorg,
                dest_git_user=results.dest_gituser,
                dest_git_host=results.dest_githost,
                dest_org=results.dest_gitorg,
                release=results.release,
                preconv_names=results.preconv_names,
                source_branch=results.source_branch,
                dest_branch=results.dest_branch,
                upstream_lookaside=results.upstream_lookaside,
                distprefix=results.distprefix,
                distcustom=results.distcustom,
                alternate_spec_name=results.alternate_spec_name,
                dest_lookaside=results.dest_lookaside,
                aws_access_key_id=results.aws_access_key_id,
                aws_access_key=results.aws_access_key,
                aws_bucket=results.aws_bucket,
                aws_region=results.aws_region,
                aws_use_ssl=results.aws_use_ssl,
                skip_lookaside=results.skip_lookaside_upload,
                s3_upload=results.upload_to_s3,
        )
        classy.pkg_import()
    else:
        print('Unknown command')

if __name__ == '__main__':
    main()
