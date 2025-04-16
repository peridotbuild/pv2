# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import re
from pv2.util import gitutil, fileutil, generic
from pv2.util import error as err
from pv2.util import log as pvlog
from . import Import

__all__ = ['SrpmImport']
# todo: add in logging and replace print with log

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
            distcustom: str = '',
            git_user: str = 'git',
            org: str = 'rpms',
            preconv_names: bool = False,
            dest_lookaside: str = '/var/www/html/sources',
            verify_signature: bool = False,
            aws_access_key_id=None,
            aws_access_key=None,
            aws_bucket=None,
            aws_region=None,
            aws_use_ssl: bool = False
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
        self.__preconv_names = preconv_names

        pkg_name = self.__srpm_metadata['name']

        package_name = pkg_name
        if preconv_names:
            package_name = pkg_name.replace('+', 'plus')

        git_url = f'ssh://{git_user}@{git_url_path}/{org}/{package_name}.git'
        self.__git_url = git_url

        file_name_search_srpm_res = re.search(r'.*?\.src\.rpm$',
                                              self.__srpm_path, re.IGNORECASE)

        if not file_name_search_srpm_res:
            raise err.RpmInfoError('This is not a source package')

        if len(release) == 0:
            self.__release = self.__get_srpm_release_version

            if not self.__release:
                raise err.RpmInfoError('The dist tag does not contain elX or elXY')

        self.__branch = branch
        if len(branch) == 0:
            self.__branch = f'c{release}'
            pvlog.logger.warning(
                    'Warning: Branch name not specified, defaulting to %s', self.__branch
            )

        self.__aws_access_key_id = aws_access_key_id
        self.__aws_access_key = aws_access_key
        self.__aws_bucket = aws_bucket
        self.__aws_region = aws_region
        self.__aws_use_ssl = aws_use_ssl

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

    # pylint: disable=too-many-locals
    def pkg_import(self, skip_lookaside: bool = False, s3_upload: bool = False):
        """
        Actually perform the import

        If skip_lookaside is True, source files will just be deleted rather
        than uploaded to lookaside.
        """
        check_repo = gitutil.lsremote(self.git_url)
        git_repo_path = f'/var/tmp/{self.rpm_name_replace}'
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
            pvlog.logger.info('Cloning: %s', self.rpm_name)
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
                gitutil.checkout(repo, branch=branch, orphan=True)
            # Remove everything, plain and simple. Only needed for clone.
            self.remove_everything(repo.working_dir)
            for tag_name in repo.tags:
                repo_tags.append(tag_name.name)
        else:
            pvlog.logger.warning('Repo may not exist or is private. Try to import anyway.')
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
            self.perform_cleanup([git_repo_path])
            raise err.GitCommitError(f'Git tag already exists: {import_tag}')

        self.unpack_srpm(self.srpm_path, git_repo_path)
        sources = self.get_dict_of_lookaside_files(git_repo_path)
        self.generate_metadata(git_repo_path, self.rpm_name, sources)
        self.generate_filesum(git_repo_path, self.rpm_name, self.srpm_hash)

        if not skip_lookaside:
            if s3_upload:
                # I don't want to blatantly blow up here yet.
                if not self.__aws_region or not self.__aws_access_key_id or not self.__aws_access_key:
                    pvlog.logger.warning('WARNING: Access key, ID, nor region were provided. We will try to guess these values.')
                if not self.__aws_bucket:
                    pvlog.logger.warning('WARNING: No bucket was provided. Skipping upload.')
                else:
                    self.upload_to_s3(
                            git_repo_path,
                            sources,
                            self.__aws_bucket,
                            self.__aws_access_key_id,
                            self.__aws_access_key,
                            self.__aws_use_ssl,
                            self.__aws_region,
                    )
                # this is a quick cleanup op, will likely change the name
                # later.
                self.skip_local_import_lookaside(git_repo_path, sources)
            else:
                self.import_lookaside(git_repo_path, self.rpm_name, branch,
                                      sources, self.dest_lookaside)
        else:
            self.skip_local_import_lookaside(git_repo_path, sources)

        # Temporary hack like with git.
        dest_gitignore_file = f'{git_repo_path}/.gitignore'
        if os.path.exists(dest_gitignore_file):
            os.remove(dest_gitignore_file)

        gitutil.add_all(repo)

        verify = repo.is_dirty()
        if verify:
            gitutil.commit(repo, commit_msg)
            ref = gitutil.tag(repo, import_tag, commit_msg)
            gitutil.push(repo, ref=ref)
            self.perform_cleanup([git_repo_path])
            return True

        # The most recent commit is assumed to be tagged also. We will not
        # push. Force the importer to tag manually.
        pvlog.logger.info('Nothing to push')
        self.perform_cleanup([git_repo_path])
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

    @property
    def preconv_names(self):
        """
        Returns if names are being preconverted
        """
        return self.__preconv_names
