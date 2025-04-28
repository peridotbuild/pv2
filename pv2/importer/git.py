# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import sys
import string
from pv2.util import gitutil, rpmutil, generic
from pv2.util import error as err
from pv2.util import log as pvlog
from . import Import

__all__ = ['GitImport']
# todo: add in logging and replace print with log

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
            scl_mode: bool = False,
            scl_package: str = '',
            alternate_spec_name: str = '',
            preconv_names: bool = False,
            dest_lookaside: str = '/var/www/html/sources',
            source_git_protocol: str = 'https',
            dest_branch: str = '',
            distprefix: str = 'el',
            distcustom: str = '',
            source_git_user: str = 'git',
            dest_git_user: str = 'git',
            dest_org: str = 'rpms',
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
        self.__rpm = package
        self.__release = release
        full_source_git_host = source_git_host
        if source_git_protocol == 'ssh':
            full_source_git_host = f'{source_git_user}@{source_git_host}'

        package_name = package
        if preconv_names:
            package_name = package.replace('+', 'plus')

        self.__source_git_url = f'{source_git_protocol}://{full_source_git_host}/{source_org}/{package_name}.git'
        self.__source_clone_path = f'/var/tmp/{package_name}-source'
        self.__source_git_spec = f'{self.__source_clone_path}/{package_name}.spec'
        self.__dest_git_url = f'ssh://{dest_git_user}@{dest_git_host}/{dest_org}/{package_name}.git'
        self.__dest_clone_path = f'/var/tmp/{package_name}-dest'
        self.__dist_prefix = distprefix
        self.__dist_tag = f'.{distprefix}{release}'

        # Branch logic
        # We need to determine if the branch names should be different based on
        # the input. Unfortunately we have to put up with modularity. If the
        # source branch has "stream" in the name, it will be assumed that it
        # will be a module. Since this should almost always be the case, we'll
        # change the destination branch accordingly.
        self.__source_branch = source_branch
        self.__dest_branch = source_branch

        if len(dest_branch) > 0:
            self.__dest_branch = dest_branch

        if "stream" in source_branch:
            if len(dest_branch) > 0:
                pvlog.logger.warning('Warning: This is a module import. Custom ' +
                                     'dest_branch will be ignored.')
            _stream_name = self.get_module_stream_name(source_branch)
            # This is supposed to get around "rhel-next" cases
            # It may still fail and this logic may need adjusting
            if _stream_name == "next":
                _stream_name = f"rhel{self.__release}"
            self.__dest_branch = f'{dest_branch}-stream-{_stream_name}'
            _distmarker = self.__dist_tag.lstrip('.')
            self.__dist_tag = f'.module+{_distmarker}+1010+deadbeef'

        self.__dest_lookaside = dest_lookaside
        self.__upstream_lookaside = upstream_lookaside
        self.__upstream_lookaside_url = self.get_lookaside_template_path(upstream_lookaside)
        self.__alternate_spec_name = alternate_spec_name
        self.__preconv_names = preconv_names
        self.__aws_access_key_id = aws_access_key_id
        self.__aws_access_key = aws_access_key
        self.__aws_bucket = aws_bucket
        self.__aws_region = aws_region
        self.__aws_use_ssl = aws_use_ssl

        if len(distcustom) > 0:
            self.__dist_tag = f'.{distcustom}'

        if not self.__upstream_lookaside:
            raise err.ConfigurationError(f'{upstream_lookaside} is not valid.')

        if len(alternate_spec_name) > 0:
            self.__source_git_spec = f'{self.__source_clone_path}/{alternate_spec_name}.spec'

        # metadata files for sources
        self.__metadata_file = f'{self.__source_clone_path}/.{package_name}.metadata'
        self.__sources_file = f'{self.__source_clone_path}/sources'

    # pylint: disable=too-many-locals, too-many-statements, too-many-branches
    def pkg_import(self, skip_lookaside: bool = False, s3_upload: bool = False):
        """
        Actually perform the import

        If skip_lookaside is True, source files will just be deleted rather
        than uploaded to lookaside.
        """
        try:
            check_source_repo = gitutil.lsremote(self.source_git_url)
        except err.GitInitError as exc:
            pvlog.logger.exception('Upstream git repo does not exist')
            sys.exit(2)
        except Exception as exc:
            pvlog.logger.warning('An unexpected issue occured: %s', exc)
            sys.exit(2)

        try:
            check_dest_repo = gitutil.lsremote(self.dest_git_url)
        except err.GitInitError as exc:
            pvlog.logger.exception(exc)
            check_dest_repo = None
        except Exception as exc:
            pvlog.logger.warning('An unexpected issue occured: %s', exc)
            sys.exit(2)

        # We still assign this to try to look for the file, in case it's not
        # where we think it's supposed to be.
        source_git_repo_spec = self.source_git_spec
        repo_tags = []

        # Do SCL logic here.

        # Try to clone first
        pvlog.logger.info('Cloning upstream: %s', self.rpm_name)
        source_repo = gitutil.clone(
                git_url_path=self.source_git_url,
                repo_name=self.rpm_name_replace,
                to_path=self.source_clone_path,
                branch=self.source_branch,
                single_branch=True
        )

        if check_dest_repo:
            ref_check = f'refs/heads/{self.dest_branch}' in check_dest_repo
            pvlog.logger.info('Cloning: %s', self.rpm_name)
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
            self.remove_everything(dest_repo.working_dir)
            for tag_name in dest_repo.tags:
                repo_tags.append(tag_name.name)
        else:
            pvlog.logger.warning('Repo may not exist or is private... Try to import anyway.')
            dest_repo = gitutil.init(
                    git_url_path=self.dest_git_url,
                    repo_name=self.rpm_name_replace,
                    to_path=self.dest_clone_path,
                    branch=self.dest_branch
            )

        # Within the confines of the source git repo, we need to find a
        # "sources" file or a metadata file. One of these will determine which
        # route we take.
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
            #metafile_to_use = ''
            #self.perform_cleanup([self.source_clone_path, self.dest_clone_path])
            #return False

        sources_dict = {}
        if metafile_to_use:
            sources_dict = self.parse_metadata_file(metafile_to_use)

        # We need to check if there is a SPECS directory and make a SOURCES
        # directory if it doesn't exist
        if os.path.exists(f'{self.source_clone_path}/SPECS'):
            if not os.path.exists(f'{self.source_clone_path}/SOURCES'):
                try:
                    os.makedirs(f'{self.source_clone_path}/SOURCES')
                except Exception as exc:
                    raise err.GenericError(f'Directory could not be created: {exc}')

        for key, value in sources_dict.items():
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

        if not os.path.exists(source_git_repo_spec) and len(self.alternate_spec_name) == 0:
            source_git_repo_spec = self.find_spec_file(self.source_clone_path)

        # do rpm autochangelog logic here
        autospec_return = rpmutil.rpmautocl(source_git_repo_spec)
        if not autospec_return:
            pvlog.logger.warning('WARNING! rpmautospec was not found on this system. autospec logic is ignored.')

        # attempt to pack up the RPM, get metadata
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
        # pylint: disable=line-too-long
        srpm_nvr = srpm_metadata['name'] + '-' + srpm_metadata['version'] + '-' + srpm_metadata['release']
        import_tag = generic.safe_encoding(f'imports/{self.dest_branch}/{srpm_nvr}')
        commit_msg = f'import {srpm_nvr}'
        # unpack it to new dir, move lookaside if needed, tag and push
        if import_tag in repo_tags:
            self.perform_cleanup([self.source_clone_path, self.dest_clone_path])
            raise err.GitCommitError(f'Git tag already exists: {import_tag}')

        self.unpack_srpm(packed_srpm, self.dest_clone_path)
        sources = self.get_dict_of_lookaside_files(self.dest_clone_path)
        self.generate_metadata(self.dest_clone_path, self.rpm_name, sources)
        self.generate_filesum(self.dest_clone_path, self.rpm_name, "Direct Git Import")

        if not skip_lookaside:
            if s3_upload:
                # I don't want to blatantly blow up here yet.
                if not self.__aws_region or not self.__aws_access_key_id or not self.__aws_access_key:
                    pvlog.logger.warning('WARNING: Access key, ID, nor region were provided. We will try to guess these values.')
                if not self.__aws_bucket:
                    pvlog.logger.warning('WARNING: No bucket was provided. Skipping upload.')
                else:
                    self.upload_to_s3(
                            self.dest_clone_path,
                            sources,
                            self.__aws_bucket,
                            self.__aws_access_key_id,
                            self.__aws_access_key,
                            self.__aws_use_ssl,
                            self.__aws_region,
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

        # This is a temporary hack. There are cases that the .gitignore that's
        # provided by upstream errorneouly keeps out certain sources, despite
        # the fact that they were pushed before. We're killing off any
        # .gitignore we find in the root.
        dest_gitignore_file = f'{self.dest_clone_path}/.gitignore'
        if os.path.exists(dest_gitignore_file):
            os.remove(dest_gitignore_file)

        gitutil.add_all(dest_repo)
        verify = dest_repo.is_dirty()
        if verify:
            gitutil.commit(dest_repo, commit_msg)
            ref = gitutil.tag(dest_repo, import_tag, commit_msg)
            gitutil.push(dest_repo, ref=ref)
            self.perform_cleanup([self.source_clone_path, self.dest_clone_path])
            pvlog.logger.info('Imported: %s', import_tag)
            return True
        pvlog.logger.info('Nothing to push')
        self.perform_cleanup([self.source_clone_path, self.dest_clone_path])
        return False

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

    @property
    def release_ver(self):
        """
        Returns the release version of this import
        """
        return self.__release

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
    def source_clone_path(self):
        """
        Returns the source clone path
        """
        return self.__source_clone_path

    @property
    def source_git_spec(self):
        """
        Returns the source clone rpm spec
        """
        return self.__source_git_spec

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
    def dist_tag(self):
        """
        Returns the dist tag
        """
        return self.__dist_tag

    @property
    def dist_prefix(self):
        """
        Returns the dist_prefix, which is normally "el"
        """
        return self.__dist_prefix

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

    @property
    def preconv_names(self):
        """
        Returns if names are being preconverted
        """
        return self.__preconv_names

    @property
    def metadata_file(self):
        """
        Returns a metadata file path
        """
        return self.__metadata_file

    @property
    def sources_file(self):
        """
        Returns a sources metadata file path
        """
        return self.__sources_file
