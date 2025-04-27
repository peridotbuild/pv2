# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
rpm operations
"""

import sys
from pathlib import Path
from pv2.util import log as pvlog
from pv2.util import gitutil, rpmutil, fileutil, decorators, generic
from pv2.util import error as err
#from pv2.util.constants import RpmConstants as rpmconst
from pv2.importer.operation import Import
from .editor import Config

__all__ = ['RpmImport']

# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
# pylint: disable=line-too-long,too-many-public-methods,too-many-instance-attributes
# pylint: disable=broad-exception-caught,too-many-branches

class RpmImport(Import):
    """
    Import class for importing an rpm via git
    """
    def __init__(
            self,
            rpm: str,
            version: str,
            source_git_host: str,
            dest_git_host: str,
            source_branch=None,
            dest_branch=None,
            distprefix: str = 'el',
            distcustom=None,
            source_git_protocol: str = 'https',
            source_git_user: str = 'git',
            dest_git_user: str = 'git',
            dest_git_protocol: str = 'ssh',
            source_org: str = 'src',
            dest_org: str = 'rpms',
            patch_org: str = 'patch',
            source_branch_prefix: str = 'c',
            source_branch_suffix: str = '',
            dest_branch_prefix: str = 'r',
            dest_branch_suffix: str = '',
            local_path=None,
            aws_access_key_id=None,
            aws_access_key=None,
            aws_bucket=None,
            aws_region=None,
            aws_use_ssl: bool = False,
            skip_lookaside: bool = False,
            skip_duplicate_tags: bool = False,
            skip_sources: bool = True,
            preconv_names: bool = False
    ):
        """
        Rev up the importer for srpmproc
        """
        self.__rpm = rpm
        self.__version = version
        self.__skip_lookaside = skip_lookaside
        self.__skip_duplicate_tags = skip_duplicate_tags
        self.__skip_sources = skip_sources
        self.__local_path = local_path

        # Determine branch stuff here
        set_source_branch = source_branch
        set_dest_branch = source_branch
        if not source_branch:
            set_source_branch = f'{source_branch_prefix}{version}{source_branch_suffix}'
        if not dest_branch:
            set_dest_branch = f'{dest_branch_prefix}{version}{dest_branch_suffix}'

        self.__source_branch = set_source_branch
        self.__dest_branch = set_dest_branch
        self.__dist_prefix = distprefix
        self.__dist_tag = f'.{distprefix}{version}'
        self.__distcustom = distcustom

        if distcustom:
            self.__dist_tag = f'.{distcustom}'

        # If we need to preconvert names, we can do it here. In most cases,
        # srpmproc should be importing within the same git forge. But there
        # will be cases that this isn't true, just like with the importer
        # module. The importer module though generally imports from git forges
        # that do not accept "+" in their repo names. This does not affect the
        # spec files.
        pkg = rpm
        if preconv_names:
            pkg = rpm.replace('+', 'plus')

        # Figure out the git url paths
        full_source_git_host = source_git_host
        if source_git_protocol == 'ssh':
            full_source_git_host = f'{source_git_user}@{source_git_host}'

        full_dest_git_host = dest_git_host
        if dest_git_protocol == 'ssh':
            full_dest_git_host = f'{dest_git_user}@{dest_git_host}'

        self.__source_git_url = f'{source_git_protocol}://{full_source_git_host}/{source_org}/{pkg}.git'
        self.__source_clone_path = f'/var/tmp/{pkg}-source'
        self.__dest_git_url = f'{dest_git_protocol}://{full_dest_git_host}/{dest_org}/{pkg}.git'
        self.__dest_clone_path = f'/var/tmp/{pkg}-dest'
        self.__dest_patch_git_url = f'{dest_git_protocol}://{full_dest_git_host}/{patch_org}/{pkg}.git'
        self.__dest_patch_clone_path = f'/var/tmp/{pkg}-patch'

        self.__aws_access_key_id = aws_access_key_id
        self.__aws_access_key = aws_access_key
        self.__aws_bucket = aws_bucket
        self.__aws_region = aws_region
        self.__aws_use_ssl = aws_use_ssl

    # functions
    def __clone_source(self):
        """
        Clone source repo.

        Check for spec file. Die early if none found.

        Return git obj.
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
            ref_check = gitutil.ref_check(check_source_repo,
                                          self.source_branch)
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

    def __clone_dest(self):
        """
        Clone destination repo.

        If it doesn't exist, we'll just prime ourselves for a new one.

        Return git obj.
        """
        pvlog.logger.info('Checking if destination repo exists: %s', self.rpm_name)

        try:
            check_dest_repo = gitutil.lsremote(self.dest_git_url)
        except err.GitInitError:
            pvlog.logger.error(
                    'Git repo for %s does not exist at the destination',
                    self.rpm_name)
            sys.exit(2)
        except Exception as exc:
            pvlog.logger.warning('An unexpected issue occurred: %s', exc)
            sys.exit(2)

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

        return dest_repo

    def __clone_patch_repo(self):
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
            return None
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

    def __upload_or_check_artifacts(self):
        """
        Checks for artifacts in a given bucket and reports if they're there or
        not and if configured, it will try to upload said artifacts from a
        given lookaside.

        In most cases, these should already be uploaded with the importer
        utility.
        """

    def __find_single_yaml(self, search_path, filename):
        """
        Find a single YAML file by name. Raise and error if more found.
        """
        search_path = Path(search_path)
        found = fileutil.filter_files(search_path, filename, recursive=False)
        if len(found) == 1:
            return Path(found[0])
        if len(found) > 1:
            raise err.TooManyFilesError(
                    'Patch: Too many yaml files found. This should not be possible with recursive disabled. ' +
                    'Was this module modified?'
            )

        return None

    def __perform_patch(self, patch_repo, main_branch, dest_branch):
        """
        Performs the patching operations if applicable

        * main.yml is first
        * branch_name.yml is second
        * package.yml is only in specific branches and only applies if
          branch_name.yml doesn't exist
        """
        # Checks if main branch exists, if so clones it here
        # Checks if dest branch exists and notes it.
        # If main doesn't exist, clone dest branch instead.
        # If main exists and is cloned and branch_name.yml exists, skip
        # checkout phase.

        dest_path = Path(self.dest_clone_path)
        patch_config_list = []
        patched = False
        branch_yaml_exists = False

        if main_branch:
            # it should already be main, but just in case...
            if patch_repo.active_branch.name != 'main':
                gitutil.checkout(patch_repo, 'main')

            pvlog.logger.info('Searching for a main.yml patch file')
            # Look for the main.yml
            main_yaml = self.__find_single_yaml(self.dest_patch_clone_path,
                                                'main.yml')
            if main_yaml:
                patch_config_list.append(main_yaml)
            else:
                pvlog.logger.info('No main.yml found')

            pvlog.logger.info('Searching for a %s.yml patch file', self.dest_branch)

            # look for a branch specific yaml
            branch_yaml = self.__find_single_yaml(self.dest_patch_clone_path,
                                                  f'{self.dest_branch}.yml')
            if branch_yaml:
                branch_yaml_exists = True
                patch_config_list.append(branch_yaml)
            else:
                pvlog.logger.info('No %s.yml found', self.dest_branch)

        # Apply patch list
        for patch_path in patch_config_list:
            pvlog.logger.info('Patch config: %s', patch_path)
            Config(config=patch_path).run(dest_path)
            patched = True

        if dest_branch and not branch_yaml_exists:
            pvlog.logger.info('Searching for a package.yml in %s',
                              self.dest_branch)

            gitutil.checkout(patch_repo, branch=self.dest_branch)
            package_yaml = self.__find_single_yaml(self.dest_patch_clone_path, f'{self.rpm_name}.yml')
            if package_yaml:
                pvlog.logger.info('Patch config: %s.yml', self.rpm_name)
                Config(config=package_yaml).run(dest_path)
                patched = True

        return patched

    # Move this to the importer module at some point?
    @decorators.clean_returned_dict(defaults={"epoch": "0"})
    def __get_nevra(self, spec_file, dist) -> dict:
        """
        Gets a NEVRA, returns as a dict
        """
        _epoch, _version, _release = rpmutil.spec_evr(rpmutil.spec_parse(spec_file, dist=dist))
        return {"epoch": _epoch, "version": _version, "release": _release}

    # Consider looking into putting this into importer/operation.py
    # Though this is extremely specific to srpmproc
    def __commit_and_tag(self, repo, commit_msg: str, nevra: str, patched: bool):
        """
        Commits and tags changes. Returns none if there's nothing to do.
        """
        pvlog.logger.info('Attempting to commit and tag...')
        tag = generic.safe_encoding(f'imports/{self.dest_branch}/{nevra}')
        if patched:
            tag = generic.safe_encoding(f'patched/{self.dest_branch}/{nevra}')
        gitutil.add_all(repo)
        verify = repo.is_dirty()
        if verify:
            gitutil.commit(repo, commit_msg)
            ref = gitutil.tag(repo, tag, commit_msg)
            pvlog.logger.info('Tag: %s', tag)
            return True, str(repo.head.commit), ref
        pvlog.logger.info('No changes found.')
        return False, str(repo.head.commit), None

    def __push_changes(self, repo, ref):
        """
        Pushes all changes to destination
        """
        pvlog.logger.info('Pushing to downstream repo')
        gitutil.push(repo, ref)

    def __srpmproc_cleanup(self):
        """
        Cleans up all stuff
        """
        pvlog.logger.info('Cleaning up')
        self.perform_cleanup([self.source_clone_path,
                              self.dest_clone_path,
                              self.dest_patch_clone_path])

    def srpmproc_import(self):
        """
        Imports the package
        """
        fault = 0
        result_dict = {}
        try:
            _source, _source_tag, _spec = self.__clone_source()
            _dest = self.__clone_dest()
            _patch, _main_ref, _branch_ref = self.__clone_patch_repo()
            _dist = f'.{self.dist_prefix}{self.version}'

            if _source_tag:
                _dist = self.parse_git_tag(str(_source_tag))[-1]

            if self.distcustom:
                _dist = self.distcustom

            # Remove everything from the destination, copy, and patch
            pvlog.logger.info('Copying package data')
            self.remove_everything(_dest.working_dir)
            self.copy_everything(_source.working_dir, _dest.working_dir)
            patched = self.__perform_patch(_patch, _main_ref, _branch_ref)

            # Get the NEVRA and make a new tag
            pvlog.logger.info('Getting package information')
            evra_dict = self.__get_nevra(_spec, _dist)
            evra = "{version}-{release}".format(**evra_dict)
            msg = f'import {self.rpm_name}-{evra}'
            pvlog.logger.info('Importing: %s-%s', self.rpm_name, evra)
            commit_res, commit_hash, commit_ref = self.__commit_and_tag(_dest, msg, evra, patched)
            if commit_res:
                self.__push_changes(_dest, commit_ref)

            result_dict['branch_commits'] = {self.dest_branch: commit_hash}
            result_dict['branch_versions'] = {self.dest_branch: evra_dict}
            print(result_dict)
        except (err.ConfigurationError, err.FileNotFound,
                err.TooManyFilesError, err.NotAppliedError,
                err.PatchConfigTypeError, err.PatchConfigValueError) as exc:
            pvlog.logger.error('%s', exc)
            fault = exc.fault_code
        except Exception as exc:
            pvlog.logger.error('An unexpected error occurred.')
            pvlog.logger.exception('%s', exc)
            fault = 2
        else:
            pvlog.logger.info('Completed')
        finally:
            self.__srpmproc_cleanup()

        if fault > 0:
            sys.exit(fault)

        # return data

    def pkg_import(self, skip_lookaside: bool = False, s3_upload: bool = False):
        """
        This function is useless here.
        """
        raise NotImplementedError("This function is useless here. Use srpmproc_import instead.")

    # properties
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
    def version(self):
        """
        Returns the release version we're working with
        """
        return self.__version

    @property
    def source_branch(self):
        """
        Returns the source branch
        """
        return self.__source_branch

    @property
    def dest_branch(self):
        """
        Returns the destination branch
        """
        return self.__dest_branch

    @property
    def source_git_url(self):
        """
        Returns the source git url
        """
        return self.__source_git_url

    @property
    def source_clone_path(self):
        """
        Returns the source clone path
        """
        return self.__source_clone_path

    @property
    def dest_git_url(self):
        """
        Returns the destination git url
        """
        return self.__dest_git_url

    @property
    def dest_clone_path(self):
        """
        Returns the destination clone path
        """
        return self.__dest_clone_path

    @property
    def dest_patch_git_url(self):
        """
        Returns the destination git url
        """
        return self.__dest_patch_git_url

    @property
    def dest_patch_clone_path(self):
        """
        Returns the destination clone path
        """
        return self.__dest_patch_clone_path

    @property
    def dist_tag(self):
        """
        Returns the dist tag
        """
        return self.__dist_tag

    @property
    def distcustom(self):
        """
        Returns the custom dist tag
        """
        return self.__distcustom

    @property
    def dist_prefix(self):
        """
        Returns the dist_prefix, which is normally "el"
        """
        return self.__dist_prefix

    @property
    def skip_lookaside(self):
        """
        Skip lookaside
        """
        return self.__skip_lookaside

    @property
    def skip_duplicate_tags(self):
        """
        Skip duplicate tags
        """
        return self.__skip_duplicate_tags

    @property
    def skip_sources(self):
        """
        Skip bothering with sources
        """
        pvlog.logger.warning('WARNING: Sources for this import will not be verified')
        return self.__skip_sources

    @property
    def local_path(self):
        """
        Local sources path. This is equal to "tmpfs" of the prior srpmproc
        version.
        """
        return self.__local_path

    @property
    def aws_access_key_id(self):
        """
        aws
        """
        return self.__aws_access_key_id

    @property
    def aws_access_key(self):
        """
        aws
        """
        return self.__aws_access_key

    @property
    def aws_bucket(self):
        """
        aws
        """
        return self.__aws_bucket

    @property
    def aws_region(self):
        """
        aws
        """
        return self.__aws_region

    @property
    def aws_use_ssl(self):
        """
        aws
        """
        return self.__aws_use_ssl
