# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import sys
import re
import shutil
import copy
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path
from pv2.util import fileutil, rpmutil, processor, generic, decorators
from pv2.util import gitutil
from pv2.util import error as err
from pv2.util import constants as const
from pv2.util import uploader as upload
from pv2.util import log as pvlog
from .models import ImportMetadata

__all__ = ['Import', 'GitHandler']

# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=line-too-long

@dataclass
class Import:
    """
    Import an SRPM
    """
    _package: Optional[str] = None
    _release: Optional[str] = None
    _preconv_names: Optional[bool] = False
    _distprefix: str = 'el'
    _distcustom: Optional[str] = None
    _alternate_spec_name: Optional[str] = None
    _source_git_protocol: Optional[str] = 'https'
    _source_git_user: Optional[str] = 'git'
    _source_git_host: Optional[str] = None
    _source_org: Optional[str] = None
    _source_branch: Optional[str] = None
    _dest_git_protocol: Optional[str] = 'ssh'
    _dest_git_host: Optional[str] = None
    _dest_git_user: Optional[str] = 'git'
    _dest_org: Optional[str] = 'rpms'
    _dest_branch: Optional[str] = None
    _overwrite_tags: Optional[bool] = False

    _dest_lookaside: Optional[str] = '/var/www/html/sources'
    _upstream_lookaside: Optional[str] = None
    _aws_access_key_id: Optional[str] = None
    _aws_access_key: Optional[str]= None
    _aws_bucket: Optional[str]= None
    _aws_region: Optional[str]= None
    _aws_use_ssl: Optional[bool] = False
    _skip_lookaside: Optional[bool] = False
    _s3_upload: Optional[bool] = False

    _branch_commits: dict = field(default_factory=dict)
    _branch_versions: dict = field(default_factory=dict)
    _package_checksum: Optional[str] = 'Unknown'

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
    def copy_everything(source_path, dest_path):
        """
        Copies everything from the source (except for .git) over to the new
        repo.
        """
        try:
            shutil.copytree(
                    source_path,
                    dest_path,
                    ignore=shutil.ignore_patterns('.git'),
                    dirs_exist_ok=True)
        except shutil.Error as exc:
            pvlog.logger.error('There was an issue with copying the data...')
            for src, dst, msg in exc.args[0]:
                pvlog.logger.error('%s -> %s: %s', src, dst, msg)
            raise err.FileOperationError('File operation error')

    @staticmethod
    def find_spec_file(local_repo_path):
        """
        Identifies the spec file in the repo. In the event there's two spec
        files, we will error out. Only one spec file is allowed per
        repo/package.
        """
        file_list = fileutil.filter_files(
                local_repo_path,
                '*.spec'
        )

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
    @decorators.clean_returned_dict(defaults={"epoch": "0"})
    def get_evr_dict(spec_file, dist) -> dict:
        """
        Gets an EVR, returns as a dict
        """
        if isinstance(spec_file, dict):
            _epoch = spec_file['epoch']
            _version = spec_file['version']
            _release = spec_file['release']
        else:
            _epoch, _version, _release = rpmutil.spec_evr(rpmutil.spec_parse(spec_file, dist=dist))
        return {"epoch": _epoch, "version": _version, "release": _release}

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
    def upload_to_s3(
            repo_path,
            file_dict: dict,
            bucket, aws_key_id: str, aws_secret_key: str, use_ssl = bool, region = str,
            overwrite: bool = False):
        """
        Upload an object to s3
        """
        pvlog.logger.info('Pushing sources to S3...')
        for name, sha in file_dict.items():
            source_path = f'{repo_path}/{name}'
            dest_name = sha
            exists = upload.file_exists_s3(bucket, dest_name, aws_key_id,
                                           aws_secret_key, use_ssl, region)

            if exists:
                pvlog.logger.warning('File %s already exists in the bucket.',
                                     dest_name)
                if overwrite:
                    pvlog.logger.warning('Overwriting the file %s...', dest_name)
                    upload.upload_to_s3(source_path, bucket, aws_key_id,
                                        aws_secret_key, use_ssl, region, dest_name=dest_name)
                else:
                    pvlog.logger.warning('Skipping upload of %s', dest_name)
            else:
                pvlog.logger.warning('Uploading %s...', dest_name)
                upload.upload_to_s3(source_path, bucket, aws_key_id,
                                    aws_secret_key, use_ssl, region, dest_name=dest_name)

    @staticmethod
    def skip_local_import_lookaside(repo_path: str, file_dict: dict):
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
    def parse_git_tag(git_tag):
        """
        Parses a git tag and returns a tuple
        """
        pattern = re.compile(r'^(?P<import>imports\/\w+\/)?(?P<name>\w+)-(?P<version>[\w~%.+]+)-(?P<release>\w+)(?P<dist>\.\w+)')
        check = pattern.match(git_tag)
        if not check:
            return None
        return check.groups()

    @staticmethod
    def perform_cleanup(list_of_dirs: list):
        """
        Clean up whatever is thrown at us
        """
        for directory in list_of_dirs:
            try:
                shutil.rmtree(directory)
            except FileNotFoundError:
                pvlog.logger.warning('The directory %s was not found, this is simply a warning', directory)
            except Exception as exc:
                raise err.FileNotFound(f'{directory} could not be deleted: {exc}')

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

    def set_import_metadata(
            self,
            commit_hash,
            evr_dict,
            checksum) -> ImportMetadata:
        """
        Import metadata for the end of the import
        """
        self._branch_commits = {self.dest_branch: commit_hash}
        self._branch_versions = {self.dest_branch: evr_dict}
        self._package_checksum = checksum

        meta = ImportMetadata(
                branch_commits=self._branch_commits,
                branch_versions=self._branch_versions,
                package_checksum=self._package_checksum,
        )
        return asdict(meta)

    def pkg_import(self):
        """
        This function is used elsewhere
        """
        raise NotImplementedError("Imports can only be performed in subclasses")

    # Properties
    @property
    def alternate_spec_name(self):
        """
        Returns the actual name of the spec file if it's not the package name.
        """
        return self._alternate_spec_name

    @property
    def source_git_host(self):
        """
        Returns the git host
        """
        return self._source_git_host

    @property
    def source_git_user(self):
        """
        Returns the git user
        """
        return self._source_git_user

    @property
    def source_git_protocol(self):
        """
        Returns the git protocol
        """
        return self._source_git_protocol

    @property
    def source_org(self):
        """
        Returns the git host
        """
        return self._source_org

    @property
    def source_branch(self):
        """
        Returns the starting branch
        """
        return self._source_branch

    @property
    def package(self):
        """
        Returns the name of the RPM we're working with
        """
        return self._package

    @property
    def release_ver(self):
        """
        Returns the release version of this import
        """
        return self._release

    @property
    def dest_git_host(self):
        """
        Returns the git host
        """
        return self._dest_git_host

    @property
    def dest_git_user(self):
        """
        Returns the git user
        """
        return self._dest_git_user

    @property
    def dest_git_protocol(self):
        """
        Returns the git protocol
        """
        return self._dest_git_protocol

    @property
    def dest_org(self):
        """
        Returns the git host
        """
        return self._dest_org

    @property
    def dest_branch(self) -> str:
        """
        Returns the starting branch
        """
        return self._dest_branch

    @property
    def dest_lookaside(self):
        """
        Returns destination local lookaside
        """
        return self._dest_lookaside

    @property
    def upstream_lookaside(self):
        """
        Returns upstream lookaside
        """
        return self._upstream_lookaside

    @property
    def upstream_lookaside_url(self):
        """
        Returns upstream lookaside
        """
        return self.get_lookaside_template_path(self._upstream_lookaside)

    @property
    def skip_lookaside(self):
        """
        Skip lookaside
        """
        return self._skip_lookaside

    @property
    def overwrite_tags(self):
        """
        Skip duplicate tags
        """
        return self._overwrite_tags

    @property
    def s3_upload(self):
        """
        S3 upload
        """
        return self._s3_upload

    @property
    def aws_access_key_id(self):
        """
        aws
        """
        return self._aws_access_key_id

    @property
    def aws_access_key(self):
        """
        aws
        """
        return self._aws_access_key

    @property
    def aws_bucket(self):
        """
        aws
        """
        return self._aws_bucket

    @property
    def aws_region(self):
        """
        aws
        """
        return self._aws_region

    @property
    def aws_use_ssl(self):
        """
        aws
        """
        return self._aws_use_ssl

    @property
    def branch_commits(self):
        """
        Branch commits
        """
        return self._branch_commits

    @property
    def branch_versions(self):
        """
        Branch versions
        """
        return self._branch_versions

    @property
    def package_checksum(self):
        """
        Branch versions
        """
        return self._package_checksum

    @property
    def distcustom(self):
        """
        Returns the custom dist tag
        """
        return self._distcustom

    @property
    def distprefix(self):
        """
        Returns the dist_prefix, which is normally "el"
        """
        return self._distprefix

    @property
    def dist_tag(self):
        """
        Returns the dist tag
        """
        return f'.{self._distprefix}{self._release}'

    @property
    def source_clone_path(self):
        """
        Returns the source clone path
        """
        return f'/var/tmp/{self._package}-source'

    @property
    def dest_clone_path(self):
        """
        Returns the destination clone path
        """
        return f'/var/tmp/{self._package}-dest'

    @property
    def metadata_file(self):
        """
        Returns a metadata file path
        """
        return f'{self.source_clone_path}/.{self.package}.metadata'

    @property
    def sources_file(self):
        """
        Returns a sources metadata file path
        """
        return f'{self.source_clone_path}/sources'

    @property
    def preconv_names(self):
        """
        Returns if names are being preconverted
        """
        return self._preconv_names

class GitHandler:
    """
    Git Handler class, specifically for handling repeatable actions among all
    importer modules.
    """
