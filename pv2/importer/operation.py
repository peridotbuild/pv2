# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@rockylinux.org>
"""
Importer accessories
"""

import os
import re
import shutil
from pv2.util import gitutil, fileutil, rpmutil, processor, generic
from pv2.util import error as err
from pv2.util import constants as const

__all__ = [
        'Import',
        'SrpmImport',
        'GitImport'
]
# todo: add in logging and replace print with log

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
            if os.path.isfile(file) or os.path.islink(file):
                os.remove(file)
            elif os.path.isdir(file):
                shutil.rmtree(file)

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
        processor.run_proc_no_output_shell(command_to_send)

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
                if magic.encoding == 'binary':
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
                print(f'{dest_path} already exists, skipping')
                os.remove(source_path)
            else:
                shutil.move(src=source_path, dst=dest_path)
                if os.path.exists('/usr/sbin/restorecon'):
                    processor.run_proc_foreground_shell(f'/usr/sbin/restorecon {dest_path}')

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

# pylint: disable=too-many-instance-attributes
class SrpmImport(Import):
    """
    Import class for importing rpms to a git service

    Note that this imports *as is*. This means you cannot control which branch
    nor the release tag that shows up.
    """
    # pylint: disable=too-many-arguments
    def __init__(
            self,
            git_url_path: str,
            srpm_path: str,
            release: str = '',
            branch: str = '',
            distprefix: str = 'el',
            git_user: str = 'git',
            org: str = 'rpms',
            dest_lookaside: str = '/var/www/html/sources',
            verify_signature: bool = False
    ):
        """
        Init the class.

        Set the org to something else if needed. Note that if you are using
        subgroups, do not start with a leading slash (e.g. some_group/rpms)
        """
        self.__srpm_path = srpm_path
        self.__srpm_hash = fileutil.get_checksum(srpm_path)
        self.__srpm_metadata = self.get_srpm_metadata(srpm_path,
                                                      verify_signature)
        self.__release = release
        self.__dist_prefix = distprefix
        self.__dest_lookaside = dest_lookaside

        pkg_name = self.__srpm_metadata['name']
        git_url = f'ssh://{git_user}@{git_url_path}/{org}/{pkg_name}.git'
        self.__git_url = git_url

        if len(release) == 0:
            self.__release = self.__get_srpm_release_version

            if not self.__release:
                raise err.RpmInfoError('The dist tag does not contain elX or elXY')

        self.__branch = branch
        if len(branch) == 0:
            self.__branch = f'c{release}'
            print(f'Warning: Branch name not specified, defaulting to {self.__branch}')

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

    def pkg_import(self, skip_lookaside: bool = False):
        """
        Actually perform the import

        If skip_lookaside is True, source files will just be deleted rather
        than uploaded to lookaside.
        """
        check_repo = gitutil.lsremote(self.git_url)
        git_repo_path = f'/var/tmp/{self.rpm_name}'
        branch = self.__branch
        repo_tags = []

        # We need to determine if this package has a modularity label. If it
        # does, we need to augment the branch name.
        if len(self.__srpm_metadata['modularitylabel']) > 0:
            stream_version = self.__srpm_metadata['modularitylabel'].split(':')[1]
            branch = f'{self.__branch}-stream-{stream_version}'

        # If we return None, we need to assume that this is a brand new repo,
        # so we will try to set it up accordingly. If we return refs, we'll see
        # if the branch we want to work with exists. If it does not exist,
        # we'll do a straight clone, and then create an orphan branch.
        if check_repo:
            # check for specific ref name
            ref_check = f'refs/heads/{branch}' in check_repo
            # if our check is correct, clone it. if not, clone normally and
            # orphan.
            print(f'Cloning: {self.rpm_name}')
            if ref_check:
                repo = gitutil.clone(
                        git_url_path=self.git_url,
                        repo_name=self.rpm_name_replace,
                        branch=branch
                )
            else:
                repo = gitutil.clone(
                        git_url_path=self.git_url,
                        repo_name=self.rpm_name_replace,
                        branch=None
                )
                gitutil.checkout(repo, branch=self.__branch, orphan=True)
            # Remove everything, plain and simple. Only needed for clone.
            self.remove_everything(repo.working_dir)
            for tag_name in repo.tags:
                repo_tags.append(tag_name.name)
        else:
            print('Repo may not exist or is private. Try to import anyway.')
            repo = gitutil.init(
                    git_url_path=self.git_url,
                    repo_name=self.rpm_name_replace,
                    to_path=git_repo_path,
                    branch=branch
            )

        # pylint: disable=line-too-long
        import_tag = generic.safe_encoding(f'imports/{branch}/{self.rpm_name}-{self.rpm_version}-{self.rpm_release}')
        commit_msg = f'import {self.rpm_name}-{self.rpm_version}-{self.rpm_release}'
        # Raise an error if the tag already exists. Force the importer to tag
        # manually.
        if import_tag in repo_tags:
            shutil.rmtree(git_repo_path)
            raise err.GitCommitError(f'Git tag already exists: {import_tag}')

        self.unpack_srpm(self.srpm_path, git_repo_path)
        sources = self.get_dict_of_lookaside_files(git_repo_path)
        self.generate_metadata(git_repo_path, self.rpm_name, sources)
        self.generate_filesum(git_repo_path, self.rpm_name, self.srpm_hash)

        if skip_lookaside:
            self.skip_import_lookaside(git_repo_path, sources)
        else:
            self.import_lookaside(git_repo_path, self.rpm_name, branch,
                                  sources, self.dest_lookaside)

        gitutil.add_all(repo)

        verify = repo.is_dirty()
        if verify:
            gitutil.commit(repo, commit_msg)
            ref = gitutil.tag(repo, import_tag, commit_msg)
            gitutil.push(repo, ref=ref)
            shutil.rmtree(git_repo_path)
            return True

        # The most recent commit is assumed to be tagged also. We will not
        # push. Force the importer to tag manually.
        print('Nothing to push')
        shutil.rmtree(git_repo_path)
        return False

    @property
    def git_url(self):
        """
        Returns git_url
        """
        return self.__git_url

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
        return self.__srpm_metadata['release']

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

    @property
    def rpm_name_replace(self):
        """
        Returns a "fixed" version of the RPM name
        """
        new_name = self.__srpm_metadata['name'].replace('+', 'plus')
        return new_name

    @property
    def distprefix(self):
        """
        Returns the distprefix value
        """
        return self.__dist_prefix

    @property
    def dest_lookaside(self):
        """
        Returns the destination path for the local lookaside
        """
        return self.__dest_lookaside

# pylint: disable=too-many-instance-attributes
class GitImport(Import):
    """
    Import class for importing from git (e.g. pagure or gitlab)

    This attempts to look at a git repo that was cloned and check for either a
    metadata file or a sources file. After that, it will make a best effort
    guess on how to convert it and push it to your git forge with an expected
    format.
    """
    # pylint: disable=too-many-arguments
    def __init__(
            self,
            package: str,
            source_git_url_path: str,
            source_git_org_path: str,
            git_url_path: str,
            release: str,
            branch: str,
            upstream_lookaside: str = '',
            dest_lookaside: str = '/var/www/html/sources',
            dest_branch: str = '',
            distprefix: str = 'el',
            git_user: str = 'git',
            org: str = 'rpms'
    ):
        """
        Init the class.

        Set the org to something else if needed. Note that if you are using
        subgroups, do not start with a leading slash (e.g. some_group/rpms)
        """
        self.__rpm = package
        self.__release = release
        self.__source_git_url = f'https://{source_git_url_path}/{source_git_org_path}/{package}.git'
        self.__git_url = f'ssh://{git_user}@{git_url_path}/{org}/{package}.git'
        self.__dist_prefix = distprefix
        self.__dist_tag = f'.{distprefix}{release}'
        self.__branch = branch
        self.__dest_branch = branch
        self.__dest_lookaside = dest_lookaside
        self.__upstream_lookaside = upstream_lookaside

        if len(dest_branch) > 0:
            self.__dest_branch = dest_branch

    def pkg_import(self, skip_lookaside: bool = False):
        """
        Actually perform the import

        If skip_lookaside is True, source files will just be deleted rather
        than uploaded to lookaside.
        """
        check_source_repo = gitutil.lsremote(self.source_git_url)
        check_dest_repo = gitutil.lsremote(self.source_git_url)
        source_git_repo_path = f'/var/tmp/{self.rpm_name}-source'
        dest_git_repo_path = f'/var/tmp/{self.rpm_name}'
        source_branch = self.source_branch
        dest_branch = self.dest_branch
        repo_tags = []

    @staticmethod
    def __get_lookaside_template_path(source):
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

    @property
    def rpm_name(self):
        """
        Returns the name of the RPM we're working with
        """
        return self.__rpm

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
    def dest_lookaside(self):
        """
        Returns destination local lookaside
        """
        return self.__dest_lookaside
