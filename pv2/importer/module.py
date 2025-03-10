# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import re
import shutil
import datetime
from pv2.util import gitutil, generic
from pv2.util import error as err
from . import Import

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
            source_git_url_path: str,
            source_git_org_path: str,
            git_url_path: str,
            release: str,
            branch: str,
            source_git_protocol: str = 'https',
            dest_branch: str = '',
            distprefix: str = 'el',
            git_user: str = 'git',
            org: str = 'modules'
    ):
        """
        Init the class
        """
        #if not HAS_GI:
        #    raise err.GenericError('This class cannot be loaded due to missing modules.')

        self.__module = module
        self.__release = release
        # pylint: disable=line-too-long
        self.__source_git_url = f'{source_git_protocol}://{source_git_url_path}/{source_git_org_path}/{module}.git'
        self.__git_url = f'ssh://{git_user}@{git_url_path}/{org}/{module}.git'
        self.__dist_prefix = distprefix
        self.__dist_tag = f'.{distprefix}{release}'
        self.__branch = branch
        self.__dest_branch = branch
        self.__current_time = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')

        if len(dest_branch) > 0:
            self.__dest_branch = dest_branch

        if "stream" not in self.__branch:
            raise err.ConfigurationError('Source branch does not contain stream')

        self.__stream_name = self.get_module_stream_name(branch)

    def module_import(self):
        """
        Actually perform the import.
        """
        check_source_repo = gitutil.lsremote(self.source_git_url)
        check_dest_repo = gitutil.lsremote(self.dest_git_url)
        source_git_repo_path = f'/var/tmp/{self.module_name}-source'
        dest_git_repo_path = f'/var/tmp/{self.module_name}'
        modulemd_file = f'{source_git_repo_path}/{self.module_name}.yaml'
        metadata_file = f'{dest_git_repo_path}/.{self.module_name}.metadata'
        source_branch = self.source_branch
        dest_branch = self.dest_branch
        _dist_tag = self.dist_tag
        stream_name = self.stream_name
        repo_tags = []

        # If the upstream repo doesn't report anything, exit.
        if not check_source_repo:
            raise err.GitInitError('Upstream git repo does not exist')

        dest_branch = f'{dest_branch}-stream-{stream_name}'
        module_version = self.get_module_stream_os(self.release, source_branch, self.datestamp)
        nsvc = f'{self.module_name}-{stream_name}-{module_version}.deadbeef'
        import_tag = generic.safe_encoding(
                f'imports/{dest_branch}/{nsvc}'
        )
        commit_msg = f'import {nsvc}'

        print(f'Cloning upstream: {self.module_name}')
        source_repo = gitutil.clone(
                git_url_path=self.source_git_url,
                repo_name=self.module_name,
                to_path=source_git_repo_path,
                branch=source_branch
        )

        if check_dest_repo:
            ref_check = f'refs/heads/{dest_branch}' in check_dest_repo
            print(f'Cloning: {self.module_name}')
            if ref_check:
                dest_repo = gitutil.clone(
                        git_url_path=self.dest_git_url,
                        repo_name=self.module_name,
                        to_path=dest_git_repo_path,
                        branch=dest_branch
                )
            else:
                dest_repo = gitutil.clone(
                        git_url_path=self.dest_git_url,
                        repo_name=self.module_name,
                        to_path=dest_git_repo_path,
                        branch=None
                )
                gitutil.checkout(dest_repo, branch=dest_branch, orphan=True)
            self.remove_everything(dest_repo.working_dir)
            for tag_name in dest_repo.tags:
                repo_tags.append(tag_name.name)
        else:
            print('Repo may not exist or is private. Try to import anyway.')
            dest_repo = gitutil.init(
                    git_url_path=self.dest_git_url,
                    repo_name=self.module_name,
                    to_path=dest_git_repo_path,
                    branch=dest_branch
            )

        # We'd normally look for similar tags. But the date time is always
        # going to change, so we're skipping that part.

        if not os.path.exists(f'{dest_git_repo_path}/SOURCES'):
            try:
                os.makedirs(f'{dest_git_repo_path}/SOURCES')
            except Exception as exc:
                raise err.GenericError(f'Directory could not be created: {exc}')

        # We eventually want to do it this way.
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

        with open(modulemd_file, 'r') as module_yaml:
            content = module_yaml.read()
            content_new = re.sub(r'ref:\s+(.*)', f'ref: {dest_branch}', content)
            module_yaml.close()

        # Write to the root
        with open(f'{dest_git_repo_path}/{self.module_name}.yaml', 'w') as module_yaml:
            module_yaml.write(content_new)
            module_yaml.close()

        # Write to the sources. It needs to be the original content.
        shutil.copy(modulemd_file, f'{dest_git_repo_path}/SOURCES/modulemd.src.txt')
        #with open(f'{dest_git_repo_path}/SOURCES/modulemd.src.txt', 'w') as module_yaml:
        #    module_yaml.write(content_new)
        #    module_yaml.close()

        self.generate_metadata(dest_git_repo_path, self.module_name, {})
        gitutil.add_all(dest_repo)
        verify = dest_repo.is_dirty()
        if verify:
            gitutil.commit(dest_repo, commit_msg)
            ref = gitutil.tag(dest_repo, import_tag, commit_msg)
            gitutil.push(dest_repo, ref=ref)
            self.perform_cleanup([source_git_repo_path, dest_git_repo_path])
            return True
        print('Nothing to push')
        self.perform_cleanup([source_git_repo_path, dest_git_repo_path])
        return False

    @property
    def module_name(self):
        """
        Returns the module name
        """
        return self.__module

    @property
    def source_branch(self):
        """
        Returns the starting branch
        """
        return self.__branch

    @property
    def dest_branch(self):
        """
        Returns the starting branch
        """
        return self.__dest_branch

    @property
    def source_git_url(self):
        """
        Returns the source git url
        """
        return self.__source_git_url

    @property
    def dest_git_url(self):
        """
        Returns the destination git url
        """
        return self.__git_url

    @property
    def dist_tag(self):
        """
        Returns the dist tag
        """
        return self.__dist_tag

    @property
    def datestamp(self):
        """
        Returns a date time stamp
        """
        return self.__current_time

    @property
    def stream_name(self):
        """
        Returns the stream name
        """
        return self.__stream_name

    @property
    def release(self):
        """
        Returns the release
        """
        return self.__release
