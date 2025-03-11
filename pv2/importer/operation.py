# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import re
import shutil
from pathlib import Path
from pv2.util import fileutil, rpmutil, processor, generic
from pv2.util import error as err
from pv2.util import constants as const
from pv2.util import uploader as upload
from pv2.util import log as pvlog

__all__ = ['Import']

class Import:
    """
    Import an SRPM
    """
    @staticmethod
    def remove_everything(local_repo_path):
        """
        Removes all files from a repo. This is on purpose to ensure that an
        import is "clean"

        Ignores .git and .gitignore
        """
        file_list = fileutil.filter_files_inverse(local_repo_path, lambda file: '.git' in file)
        for file in file_list:
            path = Path(file)
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)

    @staticmethod
    def find_spec_file(local_repo_path):
        """
        Identifies the spec file in the repo. In the event there's two spec
        files, we will error out. Only one spec file is allowed per
        repo/package.
        """
        file_list = fileutil.filter_files(
                local_repo_path,
                lambda file: file.endswith('.spec'))

        if len(file_list) > 1:
            raise err.ConfigurationError('This repo has more than one spec file.')

        if len(file_list) == 0:
            raise err.ConfigurationError('This repo has no spec files.')

        return file_list[0]

    @staticmethod
    def unpack_srpm(srpm_path, local_repo_path):
        """
        Unpacks an srpm to the local repo path
        """
        command_to_send = [
                'rpm',
                '-i',
                srpm_path,
                '--define',
                f"'%_topdir {local_repo_path}'"
        ]
        command_to_send = ' '.join(command_to_send)
        returned = processor.run_proc_no_output_shell(command_to_send)
        if returned.returncode != 0:
            rpmerr = returned.stderr
            raise err.RpmOpenError(f'This package could not be unpacked:\n\n{rpmerr}')

    @staticmethod
    def pack_srpm(srpm_dir, spec_file, dist_tag, release_ver):
        """
        Packs an srpm from available sources
        """
        if not os.path.exists('/usr/bin/rpmbuild'):
            raise err.FileNotFound('rpmbuild command is missing')

        command_to_send = [
                'rpmbuild',
                '-bs',
                f'{spec_file}',
                '--define',
                f"'dist {dist_tag}'",
                '--define',
                f"'_topdir {srpm_dir}'",
                '--define',
                f"'_sourcedir {srpm_dir}'",
                '--define',
                f"'rhel {release_ver}'"
        ]
        command_to_send = ' '.join(command_to_send)
        returned = processor.run_proc_no_output_shell(command_to_send)
        if returned.returncode != 0:
            rpmerr = returned.stderr
            raise err.RpmBuildError(f'There was error packing the rpm:\n\n{rpmerr}')
        wrote_regex = r'Wrote:\s+(.*\.rpm)'
        regex_search = re.search(wrote_regex, returned.stdout, re.MULTILINE)
        if regex_search:
            return regex_search.group(1)

        return None

    @staticmethod
    def generate_metadata(repo_path: str, repo_name: str, file_dict: dict):
        """
        Generates .repo.metadata file
        """
        with open(f'{repo_path}/.{repo_name}.metadata', 'w+', encoding='utf-8') as meta:
            for name, sha in file_dict.items():
                meta.write(f'{sha}  {name}\n')

            meta.close()

    @staticmethod
    def generate_filesum(repo_path: str, repo_name: str, srpm_hash: str):
        """
        Generates the file that has the original sha256sum of the package this
        came from.
        """
        with open(f'{repo_path}/.{repo_name}.checksum', 'w+', encoding='utf-8') as checksum:
            checksum.write(f'{srpm_hash}\n')
            checksum.close()

    @staticmethod
    def get_dict_of_lookaside_files(local_repo_path):
        """
        Returns a dict of files that are part of sources and are binary.
        """
        source_dict = {}
        if os.path.exists(f'{local_repo_path}/SOURCES'):
            for file in os.scandir(f'{local_repo_path}/SOURCES'):
                full_path = f'{local_repo_path}/SOURCES/{file.name}'
                magic = fileutil.get_magic_file(full_path)
                if magic.name == 'empty':
                    continue
                # PGP public keys have been in the lookaside before. We'll
                # just do it this way. It gets around weird gitignores and
                # weird srpmproc behavior.
                if 'PGP public' in magic.name:
                    # source_dict[f'SOURCES/{file.name}'] = fileutil.get_checksum(full_path)
                    # Going to allow PGP keys again.
                    continue
                # binary files should be brought to lookaside, but certificate
                # files in binary format don't have to be, it doesn't quite
                # make sense. this should get around that.
                if magic.encoding == 'binary' and 'Certificate,' not in magic.name:
                    source_dict[f'SOURCES/{file.name}'] = fileutil.get_checksum(full_path)

                # This is a list of possible file names that should be in
                # lookaside, even if their type ISN'T that.
                if full_path.endswith('.rpm'):
                    source_dict[f'SOURCES/{file.name}'] = fileutil.get_checksum(full_path)

        return source_dict

    @staticmethod
    def get_srpm_metadata(srpm_path, verify=False):
        """
        Gets the rpm metadata
        """
        hdr = rpmutil.get_rpm_header(file_name=srpm_path,
                                     verify_signature=verify)

        metadata = rpmutil.get_rpm_metadata_from_hdr(hdr)
        return metadata

    @staticmethod
    def import_lookaside(
            repo_path: str,
            repo_name: str,
            branch: str,
            file_dict: dict,
            dest_lookaside: str = '/var/www/html/sources'
    ):
        """
        Attempts to move the lookaside files if they don't exist to their
        hashed name.
        """
        dest_dir = f'{dest_lookaside}/{repo_name}/{branch}'
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir, 0o755)
        for name, sha in file_dict.items():
            source_path = f'{repo_path}/{name}'
            dest_path = f'{dest_dir}/{sha}'
            if os.path.exists(dest_path):
                pvlog.logger.info('%s already exists, skipping', dest_path)
                os.remove(source_path)
            else:
                pvlog.logger.info('Moving %s to %s', source_path, dest_path)
                shutil.move(src=source_path, dst=dest_path)
                if os.path.exists('/usr/sbin/restorecon'):
                    processor.run_proc_foreground_shell(f'/usr/sbin/restorecon {dest_path}')
    @staticmethod
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def upload_to_s3(repo_path, file_dict: dict, bucket, aws_key_id: str,
                     aws_secret_key: str, overwrite: bool = False):
        """
        Upload an object to s3
        """
        pvlog.logger.info('Pushing sources to S3...')
        for name, sha in file_dict.items():
            source_path = f'{repo_path}/{name}'
            dest_name = sha
            upload.upload_to_s3(source_path, bucket, aws_key_id,
                                aws_secret_key, dest_name=dest_name,
                                overwrite=overwrite)

    @staticmethod
    def skip_import_lookaside(repo_path: str, file_dict: dict):
        """
        Removes all files that are supposed to go to the lookaside. This is for
        cases where you may have sources in another location, you just want the
        metadata filled out appropriately.
        """
        for name, _ in file_dict.items():
            source_path = f'{repo_path}/{name}'
            os.remove(source_path)

    @staticmethod
    def get_lookaside_template_path(source):
        """
        Attempts to return the lookaside template
        """
        # This is an extremely hacky way to return the right value. In python
        # 3.10, match-case was introduced. However, we need to assume that
        # python 3.9 is the lowest used version for this module, so we need to
        # be inefficient until we no longer use EL9 as the base line.
        return {
                'rocky8': const.GitConstants.ROCKY8_LOOKASIDE_PATH,
                'rocky': const.GitConstants.ROCKY_LOOKASIDE_PATH,
                'centos': const.GitConstants.CENTOS_LOOKASIDE_PATH,
                'stream': const.GitConstants.STREAM_LOOKASIDE_PATH,
                'fedora': const.GitConstants.FEDORA_LOOKASIDE_PATH,
        }.get(source, None)

    @staticmethod
    def parse_metadata_file(metadata_file) -> dict:
        """
        Attempts to loop through the metadata file
        """
        file_dict = {}
        # pylint: disable=line-too-long
        line_pattern = re.compile(r'^(?P<hashtype>[^ ]+?) \((?P<file>[^ )]+?)\) = (?P<checksum>[^ ]+?)$')
        classic_pattern = re.compile(r'^(?P<checksum>[^ ]+?)\s+(?P<file>[^ ]+?)$')
        with open(metadata_file, encoding='UTF-8') as metafile:
            for line in metafile:
                strip = line.strip()
                if not strip:
                    continue

                line_check = line_pattern.match(strip)
                classic_check = classic_pattern.match(strip)
                if line_check is not None:
                    file_dict[line_check.group('file')] = {
                            'hashtype': line_check.group('hashtype'),
                            'checksum': line_check.group('checksum')
                    }
                elif classic_check is not None:
                    file_dict[classic_check.group('file')] = {
                            'hashtype': generic.hash_checker(classic_check.group('checksum')),
                            'checksum': classic_check.group('checksum')
                    }

        return file_dict

    @staticmethod
    def perform_cleanup(list_of_dirs: list):
        """
        Clean up whatever is thrown at us
        """
        for directory in list_of_dirs:
            try:
                shutil.rmtree(directory)
            except Exception as exc:
                raise err.FileNotFound(f'{directory} could not be deleted. Please check. {exc}')

    @staticmethod
    def get_module_stream_name(source_branch):
        """
        Returns a branch name for modules
        """
        branch_fix = re.sub(r'-rhel-\d+\.\d+\.\d+', '', source_branch)
        regex = r'stream-([a-zA-Z0-9_\.-]+)-([a-zA-Z0-9_\.]+)'
        regex_search = re.search(regex, branch_fix)
        return regex_search.group(2)

    @staticmethod
    def get_module_stream_os(release, source_branch, timestamp):
        """
        Returns a code of major, minor, micro version if applicable
        """
        if 'rhel' not in source_branch:
            return f'{release}'

        regex = r'rhel-([0-9]+)\.([0-9]+)\.([0-9]+)'
        regex_search = re.search(regex, source_branch)
        minor_version = regex_search.group(2)
        micro_version = regex_search.group(3)
        if len(regex_search.group(2)) == 1:
            minor_version = f'0{regex_search.group(2)}'

        if len(regex_search.group(3)) == 1:
            micro_version = f'0{regex_search.group(3)}'

        return f'{release}{minor_version}{micro_version}{timestamp}'
