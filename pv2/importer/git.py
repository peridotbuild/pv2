# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Importer accessories
"""

import os
import string
from pv2.util import gitutil, rpmutil, generic
from pv2.util import error as err
from pv2.util import log as pvlog
from . import Import

__all__ = ['GitImport']
# todo: add in logging and replace print with log

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
        # pylint: disable=line-too-long
        full_source_git_host = source_git_host
        if source_git_protocol == 'ssh':
            full_source_git_host = f'{source_git_user}@{source_git_host}'

        package_name = package
        if preconv_names:
            package_name = package.replace('+', 'plus')

        self.__source_git_url = f'{source_git_protocol}://{full_source_git_host}/{source_org}/{package_name}.git'
        self.__dest_git_url = f'ssh://{dest_git_user}@{dest_git_host}/{dest_org}/{package_name}.git'
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
        self.__aws_region = aws_region
        self.__aws_use_ssl = aws_use_ssl

        if len(distcustom) > 0:
            self.__dist_tag = f'.{distcustom}'

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
        source_git_repo_changelog = f'{source_git_repo_path}/changelog'
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
            # this is to get around "rhel-next" cases
            if _stream_name == "next":
                _stream_name = f"rhel{release_ver}"
            dest_branch = f'{dest_branch}-stream-{_stream_name}'
            distmarker = self.dist_tag.lstrip('.')
            _dist_tag = f'.module+{distmarker}+1010+deadbeef'

        # Do SCL logic here.

        # Try to clone first
        pvlog.logger.info('Cloning upstream: %s', self.rpm_name)
        source_repo = gitutil.clone(
                git_url_path=self.source_git_url,
                repo_name=self.rpm_name_replace,
                to_path=source_git_repo_path,
                branch=source_branch,
                single_branch=True
        )

        if check_dest_repo:
            ref_check = f'refs/heads/{dest_branch}' in check_dest_repo
            pvlog.logger.info('Cloning: %s', self.rpm_name)
            if ref_check:
                dest_repo = gitutil.clone(
                        git_url_path=self.dest_git_url,
                        repo_name=self.rpm_name_replace,
                        to_path=dest_git_repo_path,
                        branch=dest_branch,
                        single_branch=True
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
            pvlog.logger.warning('Repo may not exist or is private... Try to import anyway.')
            dest_repo = gitutil.init(
                    git_url_path=self.dest_git_url,
                    repo_name=self.rpm_name_replace,
                    to_path=dest_git_repo_path,
                    branch=dest_branch
            )

        # Within the confines of the source git repo, we need to find a
        # "sources" file or a metadata file. One of these will determine which
        # route we take.
        metafile_to_use = None
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
            # There isn't a reason to make a blank file right now.
            pvlog.logger.warning('WARNING: There was no sources or metadata found.')
            with open(metadata_file, 'w+') as metadata_handle:
                pass

        if not metafile_to_use:
            pvlog.logger.warning('Source: There was no metadata file found. Import may not work correctly.')
            #metafile_to_use = ''
            #self.perform_cleanup([source_git_repo_path, dest_git_repo_path])
            #return False

        sources_dict = {}
        if metafile_to_use:
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

        # do rpm autochangelog logic here
        autospec_return = rpmutil.rpmautocl(source_git_repo_spec)
        if not autospec_return:
            pvlog.logger.warning('WARNING! rpmautospec was not found on this system. autospec logic is ignored.')

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

        if not skip_lookaside:
            if s3_upload:
                # I don't want to blatantly blow up here yet.
                if not self.__aws_region or not self.__aws_access_key_id or not self.__aws_access_key:
                    pvlog.logger.warning('WARNING: Access key, ID, nor region were provided. We will try to guess these values.')
                if not self.__aws_bucket:
                    pvlog.logger.warning('WARNING: No bucket was provided. Skipping upload.')
                else:
                    self.upload_to_s3(
                            dest_git_repo_path,
                            sources,
                            self.__aws_bucket,
                            self.__aws_access_key_id,
                            self.__aws_access_key,
                            self.__aws_use_ssl,
                            self.__aws_region,
                    )
                # this is a quick cleanup op, will likely change the name
                # later.
                self.skip_local_import_lookaside(dest_git_repo_path, sources)
            else:
                self.import_lookaside(dest_git_repo_path, self.rpm_name, dest_branch,
                                      sources, self.dest_lookaside)
        else:
            self.skip_local_import_lookaside(dest_git_repo_path, sources)

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
            pvlog.logger.info('Imported: %s', import_tag)
            return True
        pvlog.logger.info('Nothing to push')
        self.perform_cleanup([source_git_repo_path, dest_git_repo_path])
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
