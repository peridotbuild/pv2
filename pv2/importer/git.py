# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import sys
import string
from functools import cached_property
from pv2.util import rpmutil, generic
from pv2.util import error as err
from pv2.util import log as pvlog
from . import Import
from . import GitHandler

__all__ = ['GitImport']

# pylint: disable=too-many-instance-attributes
# pylint: disable=line-too-long
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
            source_git_host: str,
            source_org: str,
            dest_git_host: str,
            release: str,
            source_branch: str,
            upstream_lookaside: str,
            alternate_spec_name=None,
            preconv_names: bool = False,
            dest_lookaside: str = '/var/www/html/sources',
            source_git_protocol: str = 'https',
            dest_branch=None,
            distprefix: str = 'el',
            distcustom=None,
            source_git_user: str = 'git',
            dest_git_user: str = 'git',
            dest_org: str = 'rpms',
            dest_git_protocol: str = 'ssh',
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
        # I *should* be able to simplify this somehow
        super().__init__(
                _package=package,
                _release=release,
                _preconv_names=preconv_names,
                _distprefix=distprefix,
                _distcustom=distcustom,
                _alternate_spec_name=alternate_spec_name,
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
                _dest_lookaside=dest_lookaside,
                _aws_access_key_id=aws_access_key_id,
                _aws_access_key=aws_access_key,
                _aws_bucket=aws_bucket,
                _aws_region=aws_region,
                _aws_use_ssl=aws_use_ssl,
                _skip_lookaside=skip_lookaside,
                _s3_upload=s3_upload,
                _upstream_lookaside=upstream_lookaside,
        )
        self.__rpm_name = package
        if preconv_names:
            self._package = self._package.replace('+', 'plus')

        self.__source_git_spec = f'{self.source_clone_path}/{self.rpm_name}.spec'

        self._dest_branch = source_branch

        if dest_branch:
            self._dest_branch = dest_branch

        if distcustom:
            self.override_dist_tag(f'.{distcustom}')
        elif source_branch and "stream" in source_branch:
            stream_name = self.get_module_stream_name(source_branch)
            if "next" in stream_name:
                stream_name = f"rhel{self.release_ver}"
            _distmarker = self.default_dist_tag.lstrip('.')
            self.override_dist_tag(f'.module+{_distmarker}+1010+deadbeef')
            self._dest_branch = f'{self._dest_branch}-stream-{stream_name}'

        if not upstream_lookaside:
            raise err.ConfigurationError(f'{upstream_lookaside} is not valid.')

        if alternate_spec_name:
            self.__source_git_spec = f'{self.source_clone_path}/{alternate_spec_name}.spec'

        self.git = GitHandler(self)

    # functions
    def __get_metafile(self):
        """
        Gets which metadata file we're going to use
        """
        metafile_to_use = None
        if os.path.exists(self.metadata_file):
            no_metadata_list = ['stream', 'fedora']
            if any(ignore in self.upstream_lookaside for ignore in no_metadata_list):
                # pylint: disable=line-too-long
                raise err.ConfigurationError(f'metadata files are not supported with {self.upstream_lookaside}')
            metafile_to_use = self.metadata_file
        elif os.path.exists(self.sources_file):
            no_sources_list = ['rocky', 'centos']
            if any(ignore in self.upstream_lookaside for ignore in no_sources_list):
                # pylint: disable=line-too-long
                raise err.ConfigurationError(f'sources files are not supported with {self.upstream_lookaside}')
            metafile_to_use = self.sources_file
        else:
            #raise err.GenericError('sources or metadata file NOT found')
            # There isn't a reason to make a blank file right now.
            pvlog.logger.warning('WARNING: There was no sources or metadata found.')
            with open(self.metadata_file, 'w+') as metadata_handle:
                pass

        if not metafile_to_use:
            pvlog.logger.warning('Source: There was no metadata file found. Import may not work correctly.')
        return metafile_to_use

    def __get_actual_lookaside_url(self, filename, hashtype, checksum):
        """
        Returns the translated URL to obtain sources
        """
        rpm_name = self.rpm_name
        if self.preconv_names:
            rpm_name = self.rpm_name_replace
        dict_template = {
                'PKG_NAME': rpm_name,
                'FILENAME': filename,
                'HASH_TYPE': hashtype.lower(),
                'HASH': checksum
        }

        template = string.Template(self.upstream_lookaside_url)
        substitute = template.substitute(dict_template)
        return substitute

    def __download_sources(self, metafile):
        """
        Downloads sources based on the received sources file
        """
        sources_dict = {}
        if metafile:
            sources_dict = self.parse_metadata_file(metafile)

        # We need to check if there is a SPECS directory and make a SOURCES
        # directory if it doesn't exist
        if os.path.exists(f'{self.source_clone_path}/SPECS'):
            if not os.path.exists(f'{self.source_clone_path}/SOURCES'):
                try:
                    os.makedirs(f'{self.source_clone_path}/SOURCES')
                except Exception as exc:
                    raise err.GenericError(f'Directory could not be created: {exc}')

        for key, _ in sources_dict.items():
            download_file = f'{self.source_clone_path}/{key}'
            download_hashtype = sources_dict[key]['hashtype']
            download_checksum = sources_dict[key]['checksum']
            the_url = self.__get_actual_lookaside_url(
                    download_file.split('/')[-1],
                    download_hashtype,
                    download_checksum
            )

            generic.download_file(the_url, download_file, download_checksum,
                                  download_hashtype)

    def __get_actual_specfile(self):
        """
        Gets the actual spec file we need to work with
        """
        source_git_repo_spec = self.source_git_spec
        if not os.path.exists(self.source_git_spec) and not self.alternate_spec_name:
            source_git_repo_spec = self.find_spec_file(self.source_clone_path)

        return source_git_repo_spec

    def __pack_srpm(self, source_git_repo_spec):
        """
        Packs the rpm, returns a tuple of info
        """
        packed_srpm = self.pack_srpm(self.source_clone_path,
                                     source_git_repo_spec,
                                     self.dist_tag,
                                     self.release_ver)
        if not packed_srpm:
            raise err.MissingValueError(
                    'The srpm was not written, yet command completed successfully.'
            )
        # We can't verify an srpm we just built ourselves.
        srpm_metadata = self.get_srpm_metadata(packed_srpm, verify=False)

        return packed_srpm, srpm_metadata

    # duplicated between here and srpm.py for now
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
            _source, _source_tag, _spec = self.git.clone_source()
            _dest = self.git.clone_dest()
            _dist = self.dist_tag

            # I don't think git sources will have tags too often anymore. If we
            # determine they do, we can turn this back on.
            #if _source_tag:
            #    _dist = self.parse_git_tag(str(_source_tag))[-1]

            #if self.distcustom:
            #    _dist = self.distcustom

            _metafile = self.__get_metafile()
            self.__download_sources(_metafile)
            _specfile = self.__get_actual_specfile()

            # autospec
            autospec_return = rpmutil.rpmautocl(_specfile)
            if not autospec_return:
                pvlog.logger.warning('WARNING! rpmautospec was not found on this system. autospec logic is ignored.')

            _srpm, _srpmmeta = self.__pack_srpm(_specfile)
            self.remove_everything(_dest.working_dir)
            self.unpack_srpm(_srpm, _dest.working_dir)

            evr_dict = self.get_evr_dict(_srpmmeta, _dist)
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
                    'Direct Git Import'
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
    def source_git_spec(self):
        """
        Returns the source clone rpm spec
        """
        return self.__source_git_spec

    @property
    def rpm_name(self):
        """
        Returns the name of the RPM we're working with (duplicate)
        """
        return self.__rpm_name

    @property
    def rpm_name_replace(self):
        """
        Returns the name of the RPM we're working with
        """
        return self.__rpm_name.replace('+', 'plus')
