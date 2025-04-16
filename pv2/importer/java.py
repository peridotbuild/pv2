# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import shutil
from pv2.util import gitutil, fileutil
from pv2.util import error as err
from pv2.util import log as pvlog
from . import Import

__all__ = ['JavaPortableImport']
# todo: add in logging and replace print with log

class JavaPortableImport(Import):
    """
    Does some mangling for java portable packages
    """
    # pylint: disable=too-many-arguments
    def __init__(
            self,
            pkg_name: str,
            git_url_path: str,
            branch: str,
            git_user: str = 'git',
            org: str = 'rpms',
    ):
        """
        Init the class.
        """
        java_package_name = pkg_name
        java_git_url = f'ssh://{git_user}@{git_url_path}/{org}/{java_package_name}.git'
        portable_git_url = f'ssh://{git_user}@{git_url_path}/{org}/{java_package_name}-portable.git'
        self.__java_git_url = java_git_url
        self.__portable_git_url = portable_git_url
        self.__branch = branch
        self.__java_name = pkg_name

    def pkg_import(self):
        """
        Do the import
        """
        fileutil.mkdir('/var/tmp/java')
        check_repo = gitutil.lsremote(self.java_git_url)
        portable_check_repo = gitutil.lsremote(self.portable_git_url)
        java_git_repo_path = f'/var/tmp/java/{self.java_name}'
        portable_git_repo_path = f'/var/tmp/java/{self.java_name_portable}'
        branch = self.branch
        repo_tags = []
        if check_repo:
            # check for specific ref name
            ref_check = f'refs/heads/{branch}' in check_repo
            pvlog.logger.info('Cloning: %s', self.java_name)
            if ref_check:
                java_repo = gitutil.clone(
                        git_url_path=self.java_git_url,
                        repo_name=self.java_name,
                        to_path=java_git_repo_path,
                        branch=branch,
                        single_branch=True
                )
            else:
                raise err.GitCommitError('Invalid branch or information in general')
        else:
            raise err.GitCommitError('This repository does not exist.')

        if portable_check_repo:
            # check for specific ref name
            ref_check = f'refs/heads/{branch}' in check_repo
            # if our check is correct, clone it. if not, clone normally and
            # orphan.
            pvlog.logger.info('Cloning: %s', self.java_name_portable)
            if ref_check:
                portable_repo = gitutil.clone(
                        git_url_path=self.__portable_git_url,
                        repo_name=f'{self.java_name_portable}',
                        to_path=portable_git_repo_path,
                        branch=branch,
                        single_branch=True
                )
            else:
                portable_repo = gitutil.clone(
                        git_url_path=self.__portable_git_url,
                        repo_name=f'{self.java_name_portable}',
                        to_path=portable_git_repo_path,
                        branch=None
                )
                gitutil.checkout(portable_repo, branch=branch, orphan=True)
            for tag_name in portable_repo.tags:
                repo_tags.append(tag_name.name)
        else:
            pvlog.logger.warning('Repo may not exist or is private. Try to import anyway.')
            portable_repo = gitutil.init(
                    git_url_path=self.portable_git_url,
                    repo_name=f'{self.java_name_portable}',
                    to_path=portable_git_repo_path,
                    branch=branch
            )

        # Get tag
        java_current_tag = java_repo.git.describe()
        portable_tag = java_current_tag.replace('openjdk', 'openjdk-portable')
        portable_msg = f'importing from {java_current_tag}'

        if portable_tag in repo_tags:
            self.perform_cleanup(['/var/tmp/java'])
            raise err.GitCommitError(f'Git tag already exists: {portable_tag}')

        pvlog.logger.info('Copying metadata')
        shutil.copy2(f'{java_git_repo_path}/.{self.java_name}.metadata', f'{portable_git_repo_path}/.{self.java_name}-portable.metadata')
        pvlog.logger.info('Copying SOURCE tree')
        shutil.rmtree(f'{portable_git_repo_path}/SOURCES')
        shutil.copytree(f'{java_git_repo_path}/SOURCES', f'{portable_git_repo_path}/SOURCES')
        pvlog.logger.info('Copying portable spec file')
        shutil.copy2(f'{portable_git_repo_path}/SOURCES/{self.java_name}-portable.specfile', f'{portable_git_repo_path}/SPECS/{self.java_name}-portable.spec')
        pvlog.logger.info(f'Committing {portable_tag}')

        # Temporary hack like with git.
        dest_gitignore_file = f'{portable_git_repo_path}/.gitignore'
        if os.path.exists(dest_gitignore_file):
            os.remove(dest_gitignore_file)

        gitutil.add_all(portable_repo)
        verify = portable_repo.is_dirty()
        if verify:
            gitutil.commit(portable_repo, portable_msg)
            ref = gitutil.tag(portable_repo, portable_tag, portable_msg)
            gitutil.push(portable_repo, ref=ref)
            self.perform_cleanup(['/var/tmp/java'])
            return True

        pvlog.logger.info('Nothing to push')
        self.perform_cleanup(['/var/tmp/java'])
        return False

    @property
    def java_name(self):
        """
        Returns the name of the java we're working with
        """
        return self.__java_name

    @property
    def java_name_portable(self):
        """
        Returns the name of the java we're working with
        """
        return self.__java_name + '-portable'

    @property
    def branch(self):
        """
        Returns the branch
        """
        return self.__branch

    @property
    def java_git_url(self):
        """
        Returns the java git URL
        """
        return self.__java_git_url

    @property
    def portable_git_url(self):
        """
        Returns the portable java git URL
        """
        return self.__portable_git_url
