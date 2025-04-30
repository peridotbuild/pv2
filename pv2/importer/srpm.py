# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import sys
import re
from functools import cached_property
from pv2.util import gitutil, fileutil, generic
from pv2.util import error as err
from pv2.util import log as pvlog
from . import Import
from . import GitHandler

__all__ = ['SrpmImport']

# pylint: disable=too-many-instance-attributes,line-too-long,broad-exception-caught
# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
class SrpmImport(Import):
    """
    Import class for importing rpms to a git service

    Note that this imports *as is*. This means you cannot control which branch
    nor the release tag that shows up.
    """
    def __init__(
            self,
            dest_git_host: str,
            srpm_path: str,
            release=None,
            dest_branch: str = '',
            distprefix: str = 'el',
            distcustom=None,
            dest_git_user: str = 'git',
            dest_org: str = 'rpms',
            dest_git_protocol: str = 'ssh',
            preconv_names: bool = False,
            dest_lookaside: str = '/var/www/html/sources',
            verify_signature: bool = False,
            aws_access_key_id=None,
            aws_access_key=None,
            aws_bucket=None,
            aws_region=None,
            aws_use_ssl: bool = False,
            skip_lookaside: bool = False,
            overwrite_tags: bool = False,
            s3_upload: bool = False
    ):
        """
        Init the class.

        Set the org to something else if needed. Note that if you are using
        subgroups, do not start with a leading slash (e.g. some_group/rpms)
        """
        super().__init__(
                _release=release,
                _preconv_names=preconv_names,
                _distprefix=distprefix,
                _distcustom=distcustom,
                _dest_git_host=dest_git_host,
                _dest_git_user=dest_git_user,
                _dest_org=dest_org,
                _dest_branch=dest_branch,
                _dest_git_protocol=dest_git_protocol,
                _dest_lookaside=dest_lookaside,
                _aws_access_key_id=aws_access_key_id,
                _aws_access_key=aws_access_key,
                _aws_bucket=aws_bucket,
                _aws_region=aws_region,
                _aws_use_ssl=aws_use_ssl,
                _skip_lookaside=skip_lookaside,
                _s3_upload=s3_upload,
                _overwrite_tags=overwrite_tags,
        )
        file_name_search_srpm_res = re.search(r'.*?\.src\.rpm$',
                                              srpm_path, re.IGNORECASE)

        if not file_name_search_srpm_res:
            raise err.RpmInfoError('This is not a source package')

        self.__srpm_path = srpm_path
        self.__srpm_hash = fileutil.get_checksum(srpm_path)
        self.__srpm_metadata = self.get_srpm_metadata(srpm_path,
                                                      verify_signature)

        self._rpm_name = self.__srpm_metadata['name']
        self._package = self.__srpm_metadata['name']
        if preconv_names:
            self._package = self._package.replace('+', 'plus')

        if not release:
            self._release = self.__get_srpm_release_version

            if not self._release:
                raise err.RpmInfoError(f'The dist tag does not conform to .{self.distprefix}X')

        if distcustom:
            self.override_dist_tag(f'.{distcustom}')

        self.git = GitHandler(self)

    def __get_srpm_release_version(self):
        """
        Gets the release version from the srpm
        """
        regex = fr'.{self.distprefix}(\d+)'
        dist_tag = self.__srpm_metadata['release']
        regex_search = re.search(regex, dist_tag)
        if regex_search:
            return regex_search.group(1)

        return None

    # duplicated between here and git.py for now
    def __upload_artifacts(self, sources):
        """
        Uploads artifacts
        """
        if not self.skip_lookaside:
            if self.s3_upload:
                # I don't want to blatantly blow up here yet.
                if not self.aws_region or not self.aws_access_key_id or not self.aws_access_key:
                    pvlog.logger.warning('WARNING: Access key, ID, nor region were provided. We will try to guess these values.')
                if not self.aws_bucket:
                    pvlog.logger.warning('WARNING: No bucket was provided. Skipping upload.')
                else:
                    self.upload_to_s3(
                            self.dest_clone_path,
                            sources,
                            self.aws_bucket,
                            self.aws_access_key_id,
                            self.aws_access_key,
                            self.aws_use_ssl,
                            self.aws_region,
                    )
                # this is a quick cleanup op, will likely change the name
                # later.
                self.skip_local_import_lookaside(self.dest_clone_path, sources)
            else:
                self.import_lookaside(self.dest_clone_path, self.rpm_name,
                                      self.dest_branch,
                                      sources, self.dest_lookaside)
        else:
            self.skip_local_import_lookaside(self.dest_clone_path, sources)

    def pkg_import(self):
        """
        Actually perform the import

        If skip_lookaside is True, source files will just be deleted rather
        than uploaded to lookaside.
        """
        fault = 0
        result_dict = {}
        try:
            _dest = self.git.clone_dest()
            _dist = self.dist_tag

            self.remove_everything(_dest.working_dir)
            self.unpack_srpm(self.srpm_path, _dest.working_dir)

            evr_dict = self.get_evr_dict(self.__srpm_metadata, _dist)
            evr = "{version}-{release}".format(**evr_dict)
            nvr = f"{self.rpm_name}-{evr}"

            _lookasides = self.get_dict_of_lookaside_files(_dest.working_dir)
            self.generate_metadata(_dest.working_dir, self.rpm_name, _lookasides)
            self.generate_filesum(_dest.working_dir, self.rpm_name, "Direct Git Import")
            self.__upload_artifacts(_lookasides)

            msg = f'import {nvr}'
            pvlog.logger.info('Importing: %s', nvr)
            commit_res, commit_hash, commit_ref = self.git.commit_and_tag(_dest, msg, nvr, False)

            if commit_res:
                self.git.push_changes(_dest, commit_ref)

            result_dict = self.set_import_metadata(
                    commit_hash,
                    evr_dict,
                    self.srpm_hash
            )
        except (err.GitInitError, err.GitCommitError, err.ConfigurationError,
                err.MissingValueError) as exc:
            pvlog.logger.error('%s', exc)
            fault = exc.fault_code
        except Exception as exc:
            pvlog.logger.error('An unexpected error occurred.')
            pvlog.logger.exception('%s', exc)
            fault = 2
        else:
            pvlog.logger.info('Completed')
        finally:
            pvlog.logger.info('Cleaning up')
            self.perform_cleanup([self.source_clone_path, self.dest_clone_path])
        if fault > 0:
            sys.exit(fault)

        return result_dict

    @cached_property
    def dest_branch(self) -> str:
        """
        Returns the destination branch. Determines if it should go to a modular
        branch too.
        """
        branch = self._dest_branch or f'c{self.release_ver}'

        label = self.__srpm_metadata.get("modularitylabel", "")
        if label:
            try:
                stream_version = label.split(":")[1]
                branch = f'{branch}-stream-{stream_version}'
                pvlog.logger.info('Appears to be a module package, using branch name: %s', branch)
            except IndexError:
                pvlog.logger.warning("Modularity label is deformed: %s", label)

        return branch

    @property
    def srpm_path(self):
        """
        Returns srpm_path
        """
        return self.__srpm_path

    @property
    def srpm_hash(self):
        """
        Returns the sha256sum of an unpacked srpm
        """
        return self.__srpm_hash

    @property
    def rpm_name(self):
        """
        Returns name of srpm
        """
        return self.__srpm_metadata['name']

    @property
    def rpm_name_replace(self):
        """
        Returns name of srpm
        """
        new_name = self.__srpm_metadata['name'].replace('+', 'plus')
        return new_name

    @property
    def rpm_version(self):
        """
        Returns version of srpm
        """
        return self.__srpm_metadata['version']

    @property
    def rpm_release(self):
        """
        Returns release of srpm
        """
        # Remove ~bootstrap
        final_string = self.__srpm_metadata['release'].replace('~bootstrap', '')
        return final_string

    @property
    def part_of_module(self):
        """
        Returns if part of module
        """
        regex = r'.+\.module\+'
        dist_tag = self.__srpm_metadata['release']
        regex_search = re.search(regex, dist_tag)
        if regex_search:
            return True

        return False
