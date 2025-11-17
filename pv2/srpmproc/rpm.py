# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
rpm operations
"""

import sys
from pathlib import Path
from pv2.util import log as pvlog
from pv2.util import gitutil, fileutil, decorators
from pv2.util import error as err
from pv2.util import uploader as upload
#from pv2.util.constants import RpmConstants as rpmconst
from pv2.importer.operation import Import, GitHandler
from .editor import Config

__all__ = ['RpmImport']

# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
# pylint: disable=line-too-long,broad-exception-caught,unspecified-encoding

class RpmImport(Import):
    """
    Import class for importing an rpm via git
    """
    def __init__(
            self,
            package: str,
            release: str,
            source_git_host: str,
            dest_git_host: str,
            source_branch=None,
            upstream_lookaside: str = 'rocky',
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
            overwrite_tags: bool = False,
            skip_sources: bool = True,
            preconv_names: bool = False
    ):
        """
        Rev up the importer for srpmproc
        """
        # I *should* be able to simplify this somehow
        super().__init__(
                _package=package,
                _release=release,
                _preconv_names=preconv_names,
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
                _patch_org=patch_org,
                _overwrite_tags=overwrite_tags,
                _aws_access_key_id=aws_access_key_id,
                _aws_access_key=aws_access_key,
                _aws_bucket=aws_bucket,
                _aws_region=aws_region,
                _aws_use_ssl=aws_use_ssl,
                _local_path=local_path,
                _upstream_lookaside=upstream_lookaside,
        )
        self.__rpm_name = package
        if preconv_names:
            self._package = self._package.replace('+', 'plus')

        # Determine branch stuff here
        if not source_branch:
            self._source_branch = f'{source_branch_prefix}{release}{source_branch_suffix}'
        if not dest_branch:
            self._dest_branch = f'{dest_branch_prefix}{release}{dest_branch_suffix}'

        if self.distcustom:
            self._dist_tag = f'.{self.distcustom}'

        self.__skip_sources = skip_sources

        self.git = GitHandler(self)

    # functions
    def __upload_or_check_artifacts(self, metafile):
            #bucket, aws_key_id: str, aws_secret_key: str, use_ssl = bool, region = str):
        """
        Checks for artifacts in a given bucket and reports if they're there or
        not and if configured, it will try to upload said artifacts from a
        given lookaside.

        In most cases, these should already be uploaded with the importer
        utility.
        """
        pvlog.logger.info("Checking if sources exist in the lookaside")

        # Note: We don't support uploading from here yet. Uploads to our
        # lookaside should be done via regular src-rhel import means or another
        # method.
        if not self.aws_bucket:
            pvlog.logger.warning('No bucket was provided. We cannot check for sources.')
            return

        if not self.aws_region or not self.aws_access_key_id or not self.aws_access_key:
            pvlog.logger.warning('WARNING: Access key, ID, nor region were provided. We will try to guess these values.')

        file_dict = self.parse_metadata_file(metafile)
        for name, sha in file_dict.items():
            dest_name = sha
            exists = upload.file_exists_s3(
                    self.aws_bucket,
                    dest_name,
                    self.aws_access_key_id,
                    self.aws_access_key,
                    self.aws_use_ssl,
                    self.aws_region)

            if exists:
                pvlog.logger.info('File %s with hash %s exists in the bucket %s.', dest_name, name, self.aws_bucket)
            else:
                pvlog.logger.warning('File %s with hash %s is not in the bucket %s.', dest_name, name, self.aws_bucket)

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

    def __get_checksum_from_dest(self, repo_path):
        """
        Gets the checksum from the destination
        """
        met = Path(repo_path) / f'.{self.rpm_name}.checksum'
        with open(met, 'r') as fp:
            content = fp.read()

        return content.strip()

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

    def srpmproc_import(self):
        """
        Imports the package
        """
        fault = 0
        result_dict = {}
        patched = False
        try:
            _source, _source_tag, _spec = self.git.clone_source()
            _dest = self.git.clone_dest()
            _patch, _main_ref, _branch_ref = self.git.clone_patch_repo()
            _dist = self.dist_tag
            _metafile = self.get_metafile()

            if _source_tag:
                if (".module_el" in _source_tag) or (".module+el" in _source_tag):
                    _dist = self.parse_module_git_tag(str(_source_tag))[-1]
                else:
                    _dist = self.parse_git_tag(str(_source_tag))[-1]

            # This is the absolute final dist override
            if self.distcustom:
                _dist = self.distcustom

            # Remove everything from the destination, copy, and patch
            pvlog.logger.info('Copying package data')
            self.remove_everything(_dest.working_dir)
            self.copy_everything(_source.working_dir, _dest.working_dir)
            if _patch:
                patched = self.__perform_patch(_patch, _main_ref, _branch_ref)
            checksum_from_pkg = self.__get_checksum_from_dest(_dest.working_dir)
            _dest_spec = self.find_spec_file(_dest.working_dir)

            # artifact checking here
            self.__upload_or_check_artifacts(_metafile)

            # Get the NEVRA and make a new tag
            pvlog.logger.info('Getting package information')
            evr_dict = self.get_evr_dict(_dest_spec, _dist)
            evr = "{version}-{release}".format(**evr_dict)
            nvr = f"{self.rpm_name}-{evr}"
            msg = f'import {nvr}'
            pvlog.logger.info('Importing: %s', nvr)
            commit_res, commit_hash, commit_ref = self.git.commit_and_tag(_dest, msg, nvr, patched, self.overwrite_tags)
            if commit_res:
                self.git.push_changes(_dest, commit_ref, self.overwrite_tags)

            result_dict = self.set_import_metadata(
                    commit_hash,
                    evr_dict,
                    checksum_from_pkg
            )
        except (err.ConfigurationError, err.FileNotFound,
                err.TooManyFilesError, err.NotAppliedError,
                err.PatchConfigTypeError, err.PatchConfigValueError,
                err.GitInitError, err.GitApplyError, err.UploadError) as exc:
            pvlog.logger.error('%s', exc)
            fault = exc.fault_code
        except Exception as exc:
            pvlog.logger.error('An unexpected error occurred.')
            pvlog.logger.exception('%s', exc)
            fault = 2
        else:
            pvlog.logger.info('Completed')
        finally:
            self.perform_cleanup([self.source_clone_path,
                                  self.dest_clone_path,
                                  self.dest_patch_clone_path])

        if fault > 0:
            sys.exit(fault)

        # return data
        return result_dict

    # pylint: disable=unused-argument
    @decorators.alias_for("srpmproc_import", warn=True)
    def pkg_import(self, *args, **kwargs):
        """
        This function is useless here.
        """
        return NotImplemented

    # properties
    @property
    def rpm_name(self):
        """
        Returns the name of the RPM we're working with
        """
        return self.__rpm_name

    @property
    def rpm_name_replace(self):
        """
        Returns the name of the RPM we're working with
        """
        new_name = self.__rpm_name.replace('+', 'plus')
        return new_name

    @property
    def skip_sources(self):
        """
        Skip bothering with sources
        """
        pvlog.logger.warning('WARNING: Sources for this import will not be verified')
        return self.__skip_sources
