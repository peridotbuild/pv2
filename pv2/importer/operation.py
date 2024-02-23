# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@rockylinux.org>
"""
Importer accessories
"""

import os
import re
import shutil
import string
import datetime
from pv2.util import gitutil, fileutil, rpmutil, processor, generic
from pv2.util import error as err
from pv2.util import constants as const
from pv2.util import uploader as upload

#try:
#    import gi
#    gi.require_version('Modulemd', '2.0')
#    from gi.repository import Modulemd
#    HAS_GI = True
#except ImportError:
#    HAS_GI = False

__all__ = [
        'Import',
        'SrpmImport',
        'GitImport',
        'ModuleImport'
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
                    source_dict[f'SOURCES/{file.name}'] = fileutil.get_checksum(full_path)
                if magic.encoding == 'binary':
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
                print(f'{dest_path} already exists, skipping')
                os.remove(source_path)
            else:
                print(f'Moving {source_path} to {dest_path}')
                shutil.move(src=source_path, dst=dest_path)
                if os.path.exists('/usr/sbin/restorecon'):
                    processor.run_proc_foreground_shell(f'/usr/sbin/restorecon {dest_path}')
    @staticmethod
    # pylint: disable=too-many-arguments
    def upload_to_s3(repo_path, file_dict: dict, bucket, aws_key_id: str,
                     aws_secret_key: str, overwrite: bool = False):
        """
        Upload an object to s3
        """
        print('Pushing sources to S3...')
        for name, sha in file_dict.items():
            source_path = f'{repo_path}/{name}'
            dest_name = sha
            upload.upload_to_s3(source_path, bucket, aws_key_id,
                                aws_secret_key, dest_name=dest_name,
                                overwrite=overwrite)

    @staticmethod
    def import_lookaside_peridot_cli(
            repo_path: str,
            repo_name: str,
            file_dict: dict,
    ):
        """
        Attempts to find and use the peridot-cli binary to upload to peridot's
        lookaside. This assumes the environment is setup correctly with the
        necessary variables.

        Note: This is a temporary hack and will be removed in a future update.
        """
        for name, _ in file_dict.items():
            source_path = f'{repo_path}/{name}'

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
            verify_signature: bool = False,
            aws_access_key_id: str = '',
            aws_access_key: str = '',
            aws_bucket: str = ''
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
            print(f'Warning: Branch name not specified, defaulting to {self.__branch}')

        self.__aws_access_key_id = aws_access_key_id
        self.__aws_access_key = aws_access_key
        self.__aws_bucket = aws_bucket

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
                gitutil.checkout(repo, branch=branch, orphan=True)
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
            self.perform_cleanup([git_repo_path])
            raise err.GitCommitError(f'Git tag already exists: {import_tag}')

        self.unpack_srpm(self.srpm_path, git_repo_path)
        sources = self.get_dict_of_lookaside_files(git_repo_path)
        self.generate_metadata(git_repo_path, self.rpm_name, sources)
        self.generate_filesum(git_repo_path, self.rpm_name, self.srpm_hash)

        if s3_upload:
            # I don't want to blatantly blow up here yet.
            if len(self.__aws_access_key_id) == 0 or len(self.__aws_access_key) == 0 or len(self.__aws_bucket) == 0:
                print('WARNING: No access key, ID, or bucket was provided. Skipping upload.')
            else:
                self.upload_to_s3(
                        git_repo_path,
                        sources,
                        self.__aws_bucket,
                        self.__aws_access_key_id,
                        self.__aws_access_key,
                )

        if skip_lookaside:
            self.skip_import_lookaside(git_repo_path, sources)
        else:
            self.import_lookaside(git_repo_path, self.rpm_name, branch,
                                  sources, self.dest_lookaside)

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
        print('Nothing to push')
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
    # pylint: disable=too-many-arguments,too-many-locals
    def __init__(
            self,
            package: str,
            source_git_url_path: str,
            source_git_org_path: str,
            dest_git_url_path: str,
            release: str,
            source_branch: str,
            upstream_lookaside: str,
            scl_mode: bool = False,
            scl_package: str = '',
            alternate_spec_name: str = '',
            preconv_names: bool = False,
            dest_lookaside: str = '/var/www/html/sources',
            source_git_protocol: str = 'https',
            dest_branch: str = '',
            distprefix: str = 'el',
            source_git_user: str = 'git',
            dest_git_user: str = 'git',
            dest_org: str = 'rpms',
            aws_access_key_id: str = '',
            aws_access_key: str = '',
            aws_bucket: str = ''
    ):
        """
        Init the class.

        Set the org to something else if needed. Note that if you are using
        subgroups, do not start with a leading slash (e.g. some_group/rpms)
        """
        self.__rpm = package
        self.__release = release
        # pylint: disable=line-too-long
        full_source_git_url_path = source_git_url_path
        if source_git_protocol == 'ssh':
            full_source_git_url_path = f'{source_git_user}@{source_git_url_path}'

        package_name = package
        if preconv_names:
            package_name = package.replace('+', 'plus')

        self.__source_git_url = f'{source_git_protocol}://{full_source_git_url_path}/{source_git_org_path}/{package_name}.git'
        self.__dest_git_url = f'ssh://{dest_git_user}@{dest_git_url_path}/{dest_org}/{package_name}.git'
        self.__dist_prefix = distprefix
        self.__dist_tag = f'.{distprefix}{release}'
        self.__source_branch = source_branch
        self.__dest_branch = source_branch
        self.__dest_lookaside = dest_lookaside
        self.__upstream_lookaside = upstream_lookaside
        self.__upstream_lookaside_url = self.get_lookaside_template_path(upstream_lookaside)
        self.__alternate_spec_name = alternate_spec_name
        self.__preconv_names = preconv_names
        self.__aws_access_key_id = aws_access_key_id
        self.__aws_access_key = aws_access_key
        self.__aws_bucket = aws_bucket

        if len(dest_branch) > 0:
            self.__dest_branch = dest_branch

        if not self.__upstream_lookaside:
            raise err.ConfigurationError(f'{upstream_lookaside} is not valid.')

    # pylint: disable=too-many-locals, too-many-statements, too-many-branches
    def pkg_import(self, skip_lookaside: bool = False, s3_upload: bool = False):
        """
        Actually perform the import

        If skip_lookaside is True, source files will just be deleted rather
        than uploaded to lookaside.
        """
        check_source_repo = gitutil.lsremote(self.source_git_url)
        check_dest_repo = gitutil.lsremote(self.dest_git_url)
        source_git_repo_path = f'/var/tmp/{self.rpm_name}-source'
        source_git_repo_spec = f'{source_git_repo_path}/{self.rpm_name}.spec'
        dest_git_repo_path = f'/var/tmp/{self.rpm_name}'
        metadata_file = f'{source_git_repo_path}/.{self.rpm_name}.metadata'
        sources_file = f'{source_git_repo_path}/sources'
        source_branch = self.source_branch
        dest_branch = self.dest_branch
        _dist_tag = self.dist_tag
        release_ver = self.__release
        repo_tags = []

        # If the upstream repo doesn't report anything, exit.
        if not check_source_repo:
            raise err.GitInitError('Upstream git repo does not exist')

        if len(self.alternate_spec_name) > 0:
            source_git_repo_spec = f'{source_git_repo_path}/{self.alternate_spec_name}.spec'

        # If the source branch has "stream" in the name, it should be assumed
        # it'll be a module. Since this should always be the case, we'll change
        # dest_branch to be: {dest_branch}-stream-{stream_name}
        if "stream" in source_branch:
            _stream_name = self.get_module_stream_name(source_branch)
            dest_branch = f'{dest_branch}-stream-{_stream_name}'
            distmarker = self.dist_tag.lstrip('.')
            _dist_tag = f'.module+{distmarker}+1010+deadbeef'

        # Do SCL logic here.

        # Try to clone first
        print(f'Cloning upstream: {self.rpm_name}')
        source_repo = gitutil.clone(
                git_url_path=self.source_git_url,
                repo_name=self.rpm_name_replace,
                to_path=source_git_repo_path,
                branch=source_branch
        )

        if check_dest_repo:
            ref_check = f'refs/heads/{dest_branch}' in check_dest_repo
            print(f'Cloning: {self.rpm_name}')
            if ref_check:
                dest_repo = gitutil.clone(
                        git_url_path=self.dest_git_url,
                        repo_name=self.rpm_name_replace,
                        to_path=dest_git_repo_path,
                        branch=dest_branch
                )
            else:
                dest_repo = gitutil.clone(
                        git_url_path=self.dest_git_url,
                        repo_name=self.rpm_name_replace,
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
                    repo_name=self.rpm_name_replace,
                    to_path=dest_git_repo_path,
                    branch=dest_branch
            )

        # Within the confines of the source git repo, we need to find a
        # "sources" file or a metadata file. One of these will determine which
        # route we take.
        if os.path.exists(metadata_file):
            no_metadata_list = ['stream', 'fedora']
            if any(ignore in self.upstream_lookaside for ignore in no_metadata_list):
                # pylint: disable=line-too-long
                raise err.ConfigurationError(f'metadata files are not supported with {self.upstream_lookaside}')
            metafile_to_use = metadata_file
        elif os.path.exists(sources_file):
            no_sources_list = ['rocky', 'centos']
            if any(ignore in self.upstream_lookaside for ignore in no_sources_list):
                # pylint: disable=line-too-long
                raise err.ConfigurationError(f'sources files are not supported with {self.upstream_lookaside}')
            metafile_to_use = sources_file
        else:
            #raise err.GenericError('sources or metadata file NOT found')
            print('WARNING: There was no sources or metadata found. Making blank file.')
            with open(metadata_file, 'w+') as metadata_handle:
                pass

        sources_dict = self.parse_metadata_file(metafile_to_use)

        # We need to check if there is a SPECS directory and make a SOURCES
        # directory if it doesn't exist
        if os.path.exists(f'{source_git_repo_path}/SPECS'):
            if not os.path.exists(f'{source_git_repo_path}/SOURCES'):
                try:
                    os.makedirs(f'{source_git_repo_path}/SOURCES')
                except Exception as exc:
                    raise err.GenericError(f'Directory could not be created: {exc}')

        for key, value in sources_dict.items():
            download_file = f'{source_git_repo_path}/{key}'
            download_hashtype = sources_dict[key]['hashtype']
            download_checksum = sources_dict[key]['checksum']
            the_url = self.__get_actual_lookaside_url(
                    download_file.split('/')[-1],
                    download_hashtype,
                    download_checksum
            )

            generic.download_file(the_url, download_file, download_checksum,
                                  download_hashtype)

        if not os.path.exists(source_git_repo_spec) and len(self.alternate_spec_name) == 0:
            source_git_repo_spec = self.find_spec_file(source_git_repo_path)

        # attempt to pack up the RPM, get metadata
        packed_srpm = self.pack_srpm(source_git_repo_path,
                                     source_git_repo_spec,
                                     _dist_tag,
                                     release_ver)
        if not packed_srpm:
            raise err.MissingValueError(
                    'The srpm was not written, yet command completed successfully.'
            )
        # We can't verify an srpm we just built ourselves.
        srpm_metadata = self.get_srpm_metadata(packed_srpm, verify=False)
        # pylint: disable=line-too-long
        srpm_nvr = srpm_metadata['name'] + '-' + srpm_metadata['version'] + '-' + srpm_metadata['release']
        import_tag = generic.safe_encoding(f'imports/{dest_branch}/{srpm_nvr}')
        commit_msg = f'import {srpm_nvr}'
        # unpack it to new dir, move lookaside if needed, tag and push
        if import_tag in repo_tags:
            self.perform_cleanup([source_git_repo_path, dest_git_repo_path])
            raise err.GitCommitError(f'Git tag already exists: {import_tag}')

        self.unpack_srpm(packed_srpm, dest_git_repo_path)
        sources = self.get_dict_of_lookaside_files(dest_git_repo_path)
        self.generate_metadata(dest_git_repo_path, self.rpm_name, sources)
        self.generate_filesum(dest_git_repo_path, self.rpm_name, "Direct Git Import")

        if s3_upload:
            # I don't want to blatantly blow up here yet.
            if len(self.__aws_access_key_id) == 0 or len(self.__aws_access_key) == 0 or len(self.__aws_bucket) == 0:
                print('WARNING: No access key, ID, or bucket was provided. Skipping upload.')
            else:
                self.upload_to_s3(
                        dest_git_repo_path,
                        sources,
                        self.__aws_bucket,
                        self.__aws_access_key_id,
                        self.__aws_access_key,
                )

        if skip_lookaside:
            self.skip_import_lookaside(dest_git_repo_path, sources)
        else:
            self.import_lookaside(dest_git_repo_path, self.rpm_name, dest_branch,
                                  sources, self.dest_lookaside)

        # This is a temporary hack. There are cases that the .gitignore that's
        # provided by upstream errorneouly keeps out certain sources, despite
        # the fact that they were pushed before. We're killing off any
        # .gitignore we find in the root.
        dest_gitignore_file = f'{dest_git_repo_path}/.gitignore'
        if os.path.exists(dest_gitignore_file):
            os.remove(dest_gitignore_file)

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

    def __get_actual_lookaside_url(self, filename, hashtype, checksum):
        """
        Returns the translated URL to obtain sources
        """
        dict_template = {
                'PKG_NAME': self.rpm_name,
                'FILENAME': filename,
                'HASH_TYPE': hashtype.lower(),
                'HASH': checksum
        }

        template = string.Template(self.upstream_lookaside_url)
        substitute = template.substitute(dict_template)
        return substitute

    @property
    def rpm_name(self):
        """
        Returns the name of the RPM we're working with
        """
        return self.__rpm

    @property
    def rpm_name_replace(self):
        """
        Returns the name of the RPM we're working with
        """
        new_name = self.__rpm.replace('+', 'plus')
        return new_name

    @property
    def alternate_spec_name(self):
        """
        Returns the actual name of the spec file if it's not the package name.
        """
        return self.__alternate_spec_name

    @property
    def source_branch(self):
        """
        Returns the starting branch
        """
        return self.__source_branch

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
        return self.__dest_git_url

    @property
    def dist_tag(self):
        """
        Returns the dist tag
        """
        return self.__dist_tag

    @property
    def upstream_lookaside(self):
        """
        Returns upstream lookaside
        """
        return self.__upstream_lookaside

    @property
    def upstream_lookaside_url(self):
        """
        Returns upstream lookaside
        """
        return self.__upstream_lookaside_url

    @property
    def dest_lookaside(self):
        """
        Returns destination local lookaside
        """
        return self.__dest_lookaside

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
            content_new = re.sub('ref:\s+(.*)', f'ref: {dest_branch}', content)
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
