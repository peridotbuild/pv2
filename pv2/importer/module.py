# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import sys
import re
import shutil
import datetime
from functools import cached_property
from pv2.util import gitutil, generic
from pv2.util import error as err
from pv2.util import log as pvlog
from . import Import
from . import GitHandler

__all__ = ['ModuleImport']
# todo: add in logging and replace print with log

# pylint: disable=too-many-instance-attributes
class ModuleImport(Import):
    """
    Imports module repos
    """
    # This needs to clone whatever is there, find if there's a SOURCES
    # directory, if not make it. Make changes to the YAML to point to the
    # destination branch, copy it to SOURCES, make a metadata file.
    # pylint: disable=too-many-arguments
    def __init__(
            self,
            module: str,
            source_git_host: str,
            source_org: str,
            dest_git_host: str,
            release: str,
            source_branch: str,
            source_git_protocol: str = 'https',
            dest_branch: str = '',
            distprefix: str = 'el',
            distcustom=None,
            source_git_user: str = 'git',
            dest_git_user: str = 'git',
            dest_org: str = 'modules',
            dest_git_protocol: str = 'ssh',
            overwrite_tags: bool = False,
    ):
        """
        Init the class
        """
        #if not HAS_GI:
        #    raise err.GenericError('This class cannot be loaded due to missing modules.')
        super().__init__(
                _package=module,
                _release=release,
                _distprefix=distprefix,
                _distcustom=distcustom,
                _source_git_protocol=source_git_protocol,
                _source_git_user=source_git_user,
                _source_git_host=source_git_host,
                _source_org=source_org,
                _source_branch=source_branch,
                _dest_git_host=dest_git_host,
                _dest_git_user=dest_git_user,
                _dest_org=dest_org,
                _dest_branch=dest_branch,
                _dest_git_protocol=dest_git_protocol,
                _overwrite_tags=overwrite_tags,
        )
        self.__module = module
        self.__datestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')

        if dest_branch:
            self._dest_branch = dest_branch

        if "stream" not in source_branch:
            raise err.ConfigurationError('Source branch does not contain stream')

        stream_name = self.get_module_stream_name(source_branch)
        if "next" in stream_name:
            stream_name = f"rhel{release}"
        self._dest_branch = f'{self._dest_branch}-stream-{stream_name}'
        self.__stream_name = stream_name
        self.__module_version = self.get_module_stream_os(release, source_branch, self.__datestamp)
        self.__modulemd_file = f'{self.source_clone_path}/{self.module_name}.yaml'
        self.__context = 'deadbeef'
        self.git = GitHandler(self)

    def clone_source(self):
        """
        Clone source repo

        This overrides the default.
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
        current_source_tag = gitutil.get_current_tag(source_repo)
        if not current_source_tag:
            pvlog.logger.warning('No tag found')
        else:
            pvlog.logger.info('Tag: %s', str(current_source_tag))

        return source_repo, current_source_tag

    def __copy_data(self):
        """
        Copy module data
        """
        if not os.path.exists(f'{self.dest_clone_path}/SOURCES'):
            try:
                os.makedirs(f'{self.dest_clone_path}/SOURCES')
            except Exception as exc:

                raise err.GenericError(f'Directory could not be created: {exc}')
        #if Version(Modulemd.get_version()) < Version("2.11"):
        #    source_modulemd = Modulemd.ModuleStream.read_file(
        #            modulemd_file,
        #            True,
        #            self.module_name
        #    )
        #else:
        #    source_modulemd = Modulemd.read_packager_file(modulemd_file,
        #                                                  self.module_name,
        #                                                  stream_name)
        #components = source_modulemd.get_rpm_component_names()
        #for component in components:
        #    change = source_modulemd.get_rpm_component(component)
        #    change.set_ref(dest_branch)

        with open(self.modulemd_file, 'r') as module_yaml:
            content = module_yaml.read()
            content_new = re.sub(r'ref:\s+(.*)', f'ref: {self.dest_branch}', content)
            module_yaml.close()

        # Write to the root
        with open(f'{self.dest_clone_path}/{self.module_name}.yaml', 'w') as module_yaml:
            module_yaml.write(content_new)
            module_yaml.close()

        # Write to the sources. It needs to be the original content.
        shutil.copy(self.modulemd_file, f'{self.dest_clone_path}/SOURCES/modulemd.src.txt')
        #with open(f'{dest_git_repo_path}/SOURCES/modulemd.src.txt', 'w') as module_yaml:
        #    module_yaml.write(content_new)
        #    module_yaml.close()

    def module_import(self):
        """
        Actually perform the import.
        """
        fault = 0
        result_dict = {}
        try:
            _source, _source_tag = self.clone_source()
            _dest = self.git.clone_dest()

            self.remove_everything(_dest.working_dir)
            self.__copy_data()
            self.generate_metadata(_dest.working_dir, self.module_name, {})
            msg = f'import {self.nsvc}'
            pvlog.logger.info('Importing: %s', self.nsvc)
            commit_res, commit_hash, commit_ref = self.git.commit_and_tag(_dest, msg, self.nsvc, False, self.overwrite_tags)

            if commit_res:
                self.git.push_changes(_dest, commit_ref)

            result_dict = self.set_import_metadata(
                    commit_hash,
                    self.nsvc_dict,
                    f'Direct Git Import ({self.source_git_host})'
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

    @property
    def module_name(self):
        """
        Returns the module name
        """
        return self.__module

    # Otherwise source clone fails.
    @property
    def rpm_name(self):
        """
        Returns the module name
        """
        return self.__module

    @property
    def rpm_name_replace(self):
        """
        Returns the name of the RPM we're working with
        """
        return self.__module.replace('+', 'plus')

    @property
    def module_version(self):
        """
        Returns the module name
        """
        return self.__module_version

    @property
    def modulemd_file(self):
        """
        Returns the module name
        """
        return self.__modulemd_file

    @cached_property
    def datestamp(self):
        """
        Returns a date time stamp
        """
        return self.__datestamp

    @property
    def stream_name(self):
        """
        Returns the stream name
        """
        return self.__stream_name

    @property
    def context(self):
        """
        Returns the context
        """
        return self.__context

    @cached_property
    def nsvc(self):
        """
        Returns the NSVC
        """
        return f'{self.__module}-{self.__stream_name}-{self.__module_version}.{self.__context}'

    @cached_property
    def nsvc_dict(self):
        """
        Returns NSVC as a dict (without the name)
        """
        return {"stream": self.__stream_name, "version": self.__module_version, "context": self.__context}
