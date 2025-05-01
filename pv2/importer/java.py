# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import sys
import shutil
from functools import cached_property
from pv2.util import gitutil, fileutil
from pv2.util import error as err
from pv2.util import log as pvlog
from . import Import
from . import GitHandler

__all__ = ['JavaPortableImport']

# pylint: disable=line-too-long,too-many-arguments,too-many-positional-arguments,too-many-statements
# pylint: disable=too-many-locals,arguments-differ,too-many-branches,broad-exception-caught

class JavaPortableImport(Import):
    """
    Does some mangling for java portable packages
    """
    def __init__(
            self,
            package: str,
            source_git_host: str,
            source_branch: str,
            source_git_user: str = 'git',
            source_org: str = 'rpms',
            source_git_protocol: str = 'ssh'
    ):
        """
        Init the class.
        """
        super().__init__(
                _package=package,
                _source_git_protocol=source_git_protocol,
                _source_git_user=source_git_user,
                _source_git_host=source_git_host,
                _source_org=source_org,
                _source_branch=source_branch,
                _dest_git_protocol=source_git_protocol,
                _dest_git_user=source_git_user,
                _dest_git_host=source_git_host,
                _dest_org=source_org,
                _dest_branch=source_branch,
        )
        self.git = GitHandler(self)
        self.__rpm_name = package

    def __copy_java_elements(self, source, dest):
        """
        Copy the necessary elements of java
        """
        pvlog.logger.info('Copying metadata')
        shutil.copy2(f'{source}/.{self.java_name}.metadata',
                     f'{dest}/.{self.java_name_portable}.metadata')
        pvlog.logger.info('Copying SOURCE tree')
        shutil.rmtree(f'{dest}/SOURCES')
        shutil.copytree(f'{source}/SOURCES', f'{dest}/SOURCES')
        pvlog.logger.info('Copying portable spec file')
        shutil.copy2(f'{dest}/SOURCES/{self.java_name_portable}.specfile',
                     f'{dest}/SPECS/{self.java_name_portable}.spec')

    def pkg_import(self):
        """
        Do the import
        """
        fault = 0
        result_dict = {}
        try:
            _source, _source_tag, _spec = self.git.clone_source()
            _dest = self.git.clone_dest()
            _dist = self.dist_tag

            self.remove_everything(_dest.working_dir)
            self.__copy_java_elements(_source.working_dir, _dest.working_dir)
            self.generate_filesum(_dest.working_dir, self.java_name_portable,
                                  "Direct Java Portable Translation")
            _dest_spec = self.find_spec_file(_dest.working_dir)

            # Get the NEVRA and make a new tag
            pvlog.logger.info('Getting package information')
            evr_dict = self.get_evr_dict(_dest_spec, _dist)
            evr = "{version}-{release}".format(**evr_dict)
            nvr = f"{self.java_name_portable}-{evr}"
            msg = f'import {nvr} from {_source_tag.name}'
            pvlog.logger.info('Importing: %s', nvr)
            commit_res, commit_hash, commit_ref = self.git.commit_and_tag(_dest, msg, nvr, False)
            if commit_res:
                self.git.push_changes(_dest, commit_ref)

            result_dict = self.set_import_metadata(
                    commit_hash,
                    evr_dict,
                    'Direct Java Portable Translation'
            )
        except (err.ConfigurationError, err.FileNotFound,
                err.TooManyFilesError, err.NotAppliedError,
                err.PatchConfigTypeError, err.PatchConfigValueError,
                err.GitInitError) as exc:
            pvlog.logger.error('%s', exc)
            fault = exc.fault_code
        except Exception as exc:
            pvlog.logger.error('An unexpected error occurred.')
            pvlog.logger.exception('%s', exc)
            fault = 2
        else:
            pvlog.logger.info('Completed')
        finally:
            self.perform_cleanup([self.source_clone_path, self.dest_clone_path])

        if fault > 0:
            sys.exit(fault)

        # return data
        return result_dict

    @cached_property
    def java_git_url(self) -> str:
        """
        Returns the source git url for java
        """
        if not all([self._source_git_protocol, self._source_git_host, self._source_org, self._package]):
            raise ValueError("Cannot compute source_git_url - Missing values")
        return self._build_git_url(
                protocol=self._source_git_protocol,
                user=self._source_git_user,
                host=self._source_git_host,
                org=self._source_org,
                package=self._package
        )

    @cached_property
    def portable_git_url(self) -> str:
        """
        Returns the dest git url for java portable
        """
        if not all([self._source_git_protocol, self._source_git_host, self._source_org, self._package]):
            raise ValueError("Cannot compute source_git_url - Missing values")
        return self._build_git_url(
                protocol=self._source_git_protocol,
                user=self._source_git_user,
                host=self._source_git_host,
                org=self._source_org,
                package=f'{self._package}-portable'
        )

    @property
    def rpm_name(self):
        """
        Returns the name of the java we're working with
        """
        return self.__rpm_name

    @property
    def rpm_name_replace(self):
        """
        Returns the name of the java we're working with
        """
        return self.__rpm_name.replace('+', 'plus')

    @property
    def java_name(self):
        """
        Returns the name of the java we're working with
        """
        return self._package

    @property
    def java_name_portable(self):
        """
        Returns the name of the java we're working with
        """
        return self._package + '-portable'
