# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import sys
import re
import shutil
from functools import cached_property
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

# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-instance-attributes
# pylint: disable=line-too-long,too-many-public-methods,broad-exception-caught

@dataclass
class Import:
    """
    Import an SRPM
    """
    _package: Optional[str] = None
    _release: Optional[str] = None
    _distprefix: str = 'el'
    _distcustom: Optional[str] = None
    _dist_tag_override: Optional[str] = field(default=None, init=False)
    _preconv_names: Optional[bool] = False
    _alternate_spec_name: Optional[str] = None
    _source_git_protocol: Optional[str] = 'https'
    _source_git_user: Optional[str] = 'git'
    _source_git_host: Optional[str] = None
    _source_org: Optional[str] = None
    _source_branch: Optional[str] = None
    _source_branch_prefix: Optional[str] = 'c'
    _source_branch_suffix: Optional[str] = ''
    _dest_git_protocol: Optional[str] = 'ssh'
    _dest_git_host: Optional[str] = None
    _dest_git_user: Optional[str] = 'git'
    _dest_org: Optional[str] = 'rpms'
    _dest_branch: Optional[str] = None
    _dest_branch_prefix: Optional[str] = 'r'
    _dest_branch_suffix: Optional[str] = ''
    _patch_org: str = 'patch'
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
    _local_path: Optional[str] = None

    _branch_commits: dict = field(default_factory=dict)
    _branch_versions: dict = field(default_factory=dict)
    _package_checksum: Optional[str] = 'Unknown'

    _side_commit_hash: Optional[str] = ''
    _side_package_version: Optional[str] = ''

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
    def module_yaml_exists(local_repo_path, module_name):
        """
        Does this module yaml exist?
        """
        yaml_file = Path(local_repo_path) / f"{module_name}.yaml"
        modulemd_src = Path(local_repo_path) / "SOURCES" / "modulemd.src.txt"
        if not yaml_file.exists():
            pvlog.logger.warning("YAML doesn't exist, checking for modulemd.src")
            if not modulemd_src.exists():
                raise err.GitCheckoutError('module yaml does not exist')
            return f'SOURCES/{modulemd_src.name}'
        return yaml_file.name

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
        if not bucket:
            pvlog.logger.warning('No bucket was provided. Upload will be skipped.')
            return
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
        pattern = re.compile(r'^(?P<import>imports\/[\w-]+\/)?(?P<name>[\w\.-]+)-(?P<version>[\w~%.+]+)-(?P<release>[\w.]+?)(?P<dist>\.\w+)(?:\.\d+(?:\.\d+)*)?$')
        check = pattern.match(git_tag)
        if not check:
            return None
        return check.groups()

    @staticmethod
    def parse_module_git_tag(git_tag):
        """
        Parses a git tag and returns a tuple (modules)
        """
        pattern = re.compile(r'^(?P<import>imports\/[\w\.-]+\/)?(?P<name>[\w\.-]+)-(?P<version>[\w~%.+]+)-(?P<release>[\w.]+?)(?P<dist>\.module[\+_]el\d(?:\.\d+\.\w+)?\+\w+\+\w+)(?:\.\d+(?:\.\d+)*)?')
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
                pvlog.logger.warning('The directory %s was not found (this may be ok)', directory)
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
    def get_module_regex_groups(source_branch):
        """
        Returns a branch name for modules
        """
        regex = r'^([\w\.-]+)-stream-([\w\.-]+)'
        regex_search = re.search(regex, source_branch)
        return regex_search

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

    @staticmethod
    def split_nsvc_from_tag(tag) -> dict:
        """
        Splits NSVC from a tag
        """
        regex = r'.*/.*/([\w-]+)-([\w\.]+)-(\d+)\.(\w+)'
        regex_search = re.search(regex, tag)
        split = {
                'module': regex_search.group(1),
                'stream': regex_search.group(2),
                'version': regex_search.group(3),
                'context': regex_search.group(4)
        }
        return split

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

    def build_git_url(
            self,
            protocol: str,
            user: Optional[str],
            host: str,
            org: str,
            package: str
            ):
        """
        Builds a git url for the cached props
        """
        if protocol == "ssh":
            return f"ssh://{user}@{host}/{org}/{package}.git"
        return f"{protocol}://{host}/{org}/{package}.git"

    def get_metafile(self):
        """
        Gets which metadata file we're going to use
        """
        metafile_to_use = None
        if os.path.exists(self.metadata_file):
            no_metadata_list = ['stream', 'fedora']
            if any(ignore in self.upstream_lookaside for ignore in no_metadata_list):
                # pylint: disable=line-too-long
                raise err.ConfigurationError(f'metadata files are not supported with {self.upstream_lookaside}')
            metafile_to_use = self.metadata_file
        elif os.path.exists(self.sources_file):
            no_sources_list = ['rocky', 'centos']
            if any(ignore in self.upstream_lookaside for ignore in no_sources_list):
                # pylint: disable=line-too-long
                raise err.ConfigurationError(f'sources files are not supported with {self.upstream_lookaside}')
            metafile_to_use = self.sources_file
        else:
            # There isn't a reason to make a blank file right now.
            pvlog.logger.warning('WARNING: There was no sources or metadata found.')
            with open(self.metadata_file, 'w+') as metadata_handle:
                pass

        if not metafile_to_use:
            pvlog.logger.warning('Source: There was no metadata file found. Import may not work correctly.')
        return metafile_to_use

    # Properties
    @property
    def alternate_spec_name(self):
        """
        Returns the actual name of the spec file if it's not the package name.
        """
        return self._alternate_spec_name

    @cached_property
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
    def source_branch_prefix(self):
        """
        Returns the source branch prefix
        """
        return self._source_branch_prefix

    @property
    def source_branch_suffix(self):
        """
        Returns the source branch suffix
        """
        return self._source_branch_suffix

    @cached_property
    def source_git_url(self) -> str:
        """
        Returns the source git url
        """
        if not all([self._source_git_protocol, self._source_git_host, self._source_org, self._package]):
            raise ValueError("Cannot compute source_git_url - Missing values")
        return self.build_git_url(
                protocol=self._source_git_protocol,
                user=self._source_git_user,
                host=self._source_git_host,
                org=self._source_org,
                package=self._package
        )

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

    @cached_property
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
        Returns the git dest org
        """
        return self._dest_org

    @property
    def dest_branch(self) -> str:
        """
        Returns the starting branch
        """
        return self._dest_branch

    @property
    def dest_branch_prefix(self):
        """
        Returns the dest branch prefix
        """
        return self._dest_branch_prefix

    @property
    def dest_branch_suffix(self):
        """
        Returns the dest branch suffix
        """
        return self._dest_branch_suffix

    @property
    def dest_lookaside(self):
        """
        Returns destination local lookaside
        """
        return self._dest_lookaside

    @cached_property
    def dest_git_url(self) -> str:
        """
        Returns the dest git url
        """
        if not all([self._dest_git_protocol, self._dest_git_host, self._dest_org, self._package]):
            raise ValueError("Cannot compute dest_git_url - Missing values")
        return self.build_git_url(
                protocol=self._dest_git_protocol,
                user=self._dest_git_user,
                host=self._dest_git_host,
                org=self._dest_org,
                package=self._package
        )

    @cached_property
    def dest_patch_git_url(self):
        """
        Returns the destination git url
        """
        if not all([self._dest_git_protocol, self._dest_git_host, self._patch_org, self._package]):
            raise ValueError("Cannot compute dest_git_url - Missing values")
        return self.build_git_url(
                protocol=self._dest_git_protocol,
                user=self._dest_git_user,
                host=self._dest_git_host,
                org=self._patch_org,
                package=self._package
        )

    @property
    def patch_org(self):
        """
        Returns the git patch org
        """
        return self._patch_org

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

    ##########################################################################
    # dist specific stuff

    @cached_property
    def default_dist_tag(self) -> str:
        """
        Default dist tag
        """
        return f".{self._distprefix}{self._release}"

    @property
    def dist_tag(self) -> str:
        """
        Returns the dist tag
        """
        return self._dist_tag_override or self.default_dist_tag

    def override_dist_tag(self, new_tag: str):
        """
        Resets the dist tag
        """
        self._dist_tag_override = new_tag

    # End dist
    ##########################################################################
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
    def dest_patch_clone_path(self):
        """
        Returns the destination clone path
        """
        return f'/var/tmp/{self._package}-patch'

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

    @property
    def local_path(self):
        """
        Returns local path upload
        """
        return self._local_path

    ##########################################################################
    # Sideport properties
    @property
    def side_commit_hash(self):
        """
        Returns sideport commit hash
        """
        return self._side_commit_hash

    @property
    def side_package_version(self):
        """
        Returns sideport package version
        """
        return self._side_package_version
    # End Sideport
    ##########################################################################

class GitHandler:
    """
    Git Handler class, specifically for handling repeatable actions among all
    importer modules.
    """
    def __init__(self, context):
        """
        Init the git handler
        """
        self.ctx = context

    def __getattr__(self, name):
        """
        Get attributes from context
        """
        return getattr(self.ctx, name)

    # all shareable functions
    def clone_source(self):
        """
        Clone source repo

        Check for a spec file and metadata file. Die early if spec isn't found
        at least. Warn if there's no metadata.
        """
        pvlog.logger.info('Checking if source repo exists: %s', self.rpm_name)
        try:
            check_source_repo = gitutil.lsremote(self.source_git_url)
        except err.GitInitError:
            pvlog.logger.exception(
                    'Git repo for %s does not exist at the source',
                    self.rpm_name)
            sys.exit(2)
        except Exception as exc:
            pvlog.logger.warning('An unexpected issue occurred: %s', exc)
            sys.exit(2)

        pvlog.logger.info('Checking if source branch exists: %s',
                          self.source_branch)
        try:
            gitutil.ref_check(check_source_repo, self.source_branch)
        except err.GitCheckoutError as exc:
            pvlog.logger.error('Branch does not exist: %s', exc)
            sys.exit(2)

        pvlog.logger.info('Cloning upstream: %s (%s)', self.rpm_name, self.source_branch)
        source_repo = gitutil.clone(
                git_url_path=self.source_git_url,
                repo_name=self.rpm_name_replace,
                to_path=self.source_clone_path,
                branch=self.source_branch,
                single_branch=True
        )
        spec_file = self.find_spec_file(self.source_clone_path)
        current_source_tag = gitutil.get_current_tag(source_repo)
        if not current_source_tag:
            pvlog.logger.warning('No tag found')
        else:
            pvlog.logger.info('Tag: %s', str(current_source_tag))

        return source_repo, current_source_tag, spec_file

    def clone_dest(self):
        """
        Clone destination repo.

        If it doesn't exist, we'll just prime ourselves for a new one.

        Return git obj.
        """
        pvlog.logger.info('Checking if destination repo exists: %s', self.rpm_name)

        new_repo = False
        try:
            check_dest_repo = gitutil.lsremote(self.dest_git_url)
        except err.GitInitError:
            pvlog.logger.warning('Repo may not exist or is private... Try to import anyway.')
            new_repo = True
        except Exception as exc:
            pvlog.logger.error('An unexpected issue occurred: %s', exc)
            sys.exit(2)

        if not new_repo:
            pvlog.logger.info('Checking if destination branch exists: %s',
                              self.dest_branch)

            ref_check = f'refs/heads/{self.dest_branch}' in check_dest_repo
            pvlog.logger.info('Cloning downstream: %s (%s)', self.rpm_name, self.dest_branch)
            if ref_check:
                dest_repo = gitutil.clone(
                        git_url_path=self.dest_git_url,
                        repo_name=self.rpm_name_replace,
                        to_path=self.dest_clone_path,
                        branch=self.dest_branch,
                        single_branch=True
                )
            else:
                dest_repo = gitutil.clone(
                        git_url_path=self.dest_git_url,
                        repo_name=self.rpm_name_replace,
                        to_path=self.dest_clone_path,
                        branch=None
                )
                gitutil.checkout(dest_repo, branch=self.dest_branch, orphan=True)
        else:
            dest_repo = gitutil.init(
                    git_url_path=self.dest_git_url,
                    repo_name=self.rpm_name_replace,
                    to_path=self.dest_clone_path,
                    branch=self.dest_branch
            )
        return dest_repo

    def clone_patch_repo(self):
        """
        Clones the patch repo

        Patch repos start at the main branch.

        * main.yml - Applies to all branches
        * branch_name.yml - Applies to destination branch
        * package.yml - Applies to destination branch, but only in applicable
                        branch if former does not exist in main
        """
        pvlog.logger.info('Checking if patch repo exists: %s', self.rpm_name)

        try:
            check_patch_repo = gitutil.lsremote(self.dest_patch_git_url)
        except err.GitInitError:
            pvlog.logger.error('No patch repo found, skipping')
            return None, False, False
        except Exception as exc:
            pvlog.logger.warning('An unexpected issue occurred: %s', exc)
            sys.exit(2)

        main_ref_check = 'refs/heads/main' in check_patch_repo
        branch_ref_check = f'refs/main/{self.dest_branch}' in check_patch_repo

        if main_ref_check:
            dest_patch_repo = gitutil.clone(
                    git_url_path=self.dest_patch_git_url,
                    repo_name=self.rpm_name_replace,
                    to_path=self.dest_patch_clone_path,
                    branch='main'
            )
        elif branch_ref_check:
            dest_patch_repo = gitutil.clone(
                    git_url_path=self.dest_patch_git_url,
                    repo_name=self.rpm_name_replace,
                    to_path=self.dest_patch_clone_path,
                    branch=self.dest_branch
            )
        else:
            return None, False, False

        return dest_patch_repo, main_ref_check, branch_ref_check

    def clone_source_module(self):
        """
        Clone source repo for modules
        """
        pvlog.logger.info('Checking if source repo exists: %s', self.module_name)
        try:
            check_source_repo = gitutil.lsremote(self.source_git_url)
        except err.GitInitError:
            pvlog.logger.exception(
                    'Git repo for %s does not exist at the source',
                    self.module_name)
            sys.exit(2)
        except Exception as exc:
            pvlog.logger.warning('An unexpected issue occurred: %s', exc)
            sys.exit(2)

        pvlog.logger.info('Checking if source branch exists: %s',
                          self.source_branch)
        try:
            gitutil.ref_check(check_source_repo, self.source_branch)
        except err.GitCheckoutError as exc:
            pvlog.logger.error('Branch does not exist: %s', exc)
            sys.exit(2)

        pvlog.logger.info('Cloning upstream: %s (%s)', self.module_name, self.source_branch)
        source_repo = gitutil.clone(
                git_url_path=self.source_git_url,
                repo_name=self.module_name,
                to_path=self.source_clone_path,
                branch=self.source_branch,
                single_branch=True
        )
        module_yaml = self.module_yaml_exists(self.source_clone_path, self.module_name)
        current_source_tag = gitutil.get_current_tag(source_repo)
        if not current_source_tag:
            raise err.GitCheckoutError('No tag found.')

        pvlog.logger.info('Tag: %s', str(current_source_tag))

        if not module_yaml:
            raise err.GitCheckoutError('No YAML was found. This import will fail.')

        return source_repo, current_source_tag, module_yaml

    def commit_and_tag(self, repo, commit_msg: str, nevra: str, patched: bool, force: bool = False):
        """
        Commits and tags changes. Returns none if there's nothing to do.
        """
        # This is a temporary hack. There are cases that the .gitignore that's
        # provided by upstream errorneouly keeps out certain sources, despite
        # the fact that they were pushed before. We're killing off any
        # .gitignore we find in the root.
        dest_gitignore_file = f'{self.dest_clone_path}/.gitignore'
        if os.path.exists(dest_gitignore_file):
            os.remove(dest_gitignore_file)

        tag = generic.safe_encoding(f'imports/{self.dest_branch}/{nevra}')
        if patched:
            tag = generic.safe_encoding(f'patched/{self.dest_branch}/{nevra}')
            commit_msg += ' (patched by pv2)'

        if tag in repo.tags:
            pvlog.logger.warning('!! Tag already exists !!')
            if not self.overwrite_tags:
                return False, str(repo.head.commit), None
            # pvlog.logger.warning('Overwriting tag...')
            # raise err.GitApplyError('Overwriting is not supported yet')

        pvlog.logger.info('Attempting to commit and tag...')
        gitutil.add_all(repo)
        verify = repo.is_dirty()
        if verify:
            gitutil.commit(repo, commit_msg)
            if self.overwrite_tags:
                pvlog.logger.warning('!! Tag will be overwritten !!')
            ref = gitutil.tag(repo, tag, commit_msg, force)
            pvlog.logger.info('Tag: %s', tag)
            return True, str(repo.head.commit), ref
        pvlog.logger.info('No changes found.')
        return False, str(repo.head.commit), None

    def push_changes(self, repo, ref, force: bool = False):
        """
        Pushes all changes to destination
        """
        pvlog.logger.info('Pushing to downstream repo')
        gitutil.push(repo, ref, force)
