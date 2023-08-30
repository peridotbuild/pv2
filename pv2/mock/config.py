# -*- mode:python; coding:utf-8; -*-
# Louis Abel <label@rockylinux.org>
"""
Utility functions for mock configuration.
"""

import collections
import copy
import json
import re
import hashlib
from configparser import ConfigParser
from io import StringIO, IOBase
from pv2.util import error as err
from pv2.util import constants as const
from pv2.util import generic as generic_util

# List all classes in this module
__all__ = [
        'DnfConfig',
        'DnfRepoConfig',
        'MockConfig',
        'MockPluginConfig',
        'MockBindMountPluginConfig',
        'MockChrootScanPluginConfig',
        'MockChrootFileConfig',
        'MockConfigUtils',
        'MockMacroConfig',
        'MockMacroFileConfig',
]

# pylint: disable=too-few-public-methods
class MockConfigUtils:
    """
    Mock config utilities. Provides basic things needed when making a mock
    config.
    """
    @staticmethod
    def config_string(value):
        """
        Converts a given value to a mock compatible string

        Value should be:
            * bool
            * int
            * string
            * list
            * tuple
            * None
        """

        # If the value being sent is none, a boolean, int, or tuple, just
        # straight up return it as a string.
        if value is None or isinstance(value, (bool, int, tuple)):
            return str(value)

        # If it's a string or a list, return it as a json string/list. We make
        # sure we convert it properly and going through json makes sure it
        # comes out right.
        if isinstance(value, (str, list)):
            return json.dumps(value)

        # Error out if a value was sent that is not supported.
        raise err.ProvidedValueError(f'{type(value)}: {value} is not supported.')

    @staticmethod
    def gen_config_string(name: str, status: bool) -> str:
        """
        Generates a output string to enable a plugin
        """
        config_name = copy.copy(name)
        config_status = __class__.config_string(status)
        output = f'config_opts["plugin_conf"]["{config_name}_enable"] = {config_status}\n'
        return output

    @staticmethod
    def gen_config_string_with_opts(name: str, status: bool, opts: dict) -> str:
        """
        Generates a output string to add options to an enabled plugin
        """
        config_name = copy.copy(name)
        config_status = __class__.config_string(status)
        config_opts = copy.copy(opts)
        output = f'config_opts["plugin_conf"]["{config_name}_enable"] = {config_status}\n'
        if not status:
            return output

        output += f'config_opts["plugin_conf"]["{config_name}_opts"] = {{}}\n'

        # If plugin options were provided, we try to go through and spit them
        # out properly. Some documented plugins use nested dictionaries and the
        # value being a string. This helps with that.
        for key, option in sorted(config_opts):
            key_config = __class__.config_string(key)
            option_config = __class__.config_string(option)
            # pylint: disable=line-too-long
            output += f'config_opts["plugin_conf"]["{config_name}_opts"][{key_config}] = {option_config}\n'

        return output

    @staticmethod
    def gen_config_option(option, value, append=False) -> str:
        """
        Helps generate the 'config_opts' part of a mock configuration.
        """
        outter = ''
        option = __class__.config_string(option)

        # If a dictionary, get all key value pairs and splay them out into
        # strings (sending to config_string).
        if isinstance(value, dict):
            for key, val in sorted(value.items()):
                key_name = __class__.config_string(key)
                val_name = __class__.config_string(val)
                outter += f'config_opts[{option}][{key_name}] = {val_name}\n'
        # Some options/plugins use .append for whatever reason. Setting
        # append to True will allow this portion to work and play it out into a
        # string.
        elif append:
            value_str = __class__.config_string(value)
            outter += f'config_opts[{option}].append({value_str})\n'
        # Some options are just options in general, a key value string. This
        # covers the rest.
        else:
            value_str = __class__.config_string(value)
            # pylint: disable=consider-using-f-string
            outter += f'config_opts[{option}] = {value_str}\n'
        return outter

class DnfConfigurator:
    """
    Base class for dnf configuration generation. Should only contain static
    classes.
    """
    @staticmethod
    def gen_config_section(section, opts):
        """
        Generate a config section using the config parser and data we're
        receiving. This should be able to handle both [main] and repo sections.
        """
        # A dnf configuration is key=value, sort of like an ini file.
        # ConfigParser gets us close to that.
        config = ConfigParser()
        config.add_section(section)
        for key, value in sorted(opts.items()):

            # Continue if repositoryid was caught. We already added the section
            # above.
            if key == 'repositoryid':
                continue

            # Based on the key we received, we'll determine how the value will
            # be presented. For example, for cases of the key/values being
            # boolean options, regardless of what's received as the truthy
            # value, we'll convert it to a string integer. The rest are
            # strings in general.
            if key in const.MockConstants.MOCK_DNF_BOOL_OPTIONS:
                config.set(section, key, generic_util.gen_bool_option(value))
            elif key in const.MockConstants.MOCK_DNF_STR_OPTIONS:
                config.set(section, key, str(value))
            elif key in const.MockConstants.MOCK_DNF_LIST_OPTIONS:
                config.set(section, key, value.strip())
            elif key == 'baseurl':
                if isinstance(value, (list, tuple)):
                    value = "\n        ".join(value)
                config.set(section, key, value.strip())
            else:
                config.set(section, key, generic_util.trim_non_empty_string(key, value))

        # Export the configuration we made into a file descriptor for use in
        # DnfConfig.
        file_descriptor = StringIO()
        config.write(file_descriptor, space_around_delimiters=False)
        file_descriptor.flush()
        file_descriptor.seek(0)
        return file_descriptor.read()

class DnfConfig(DnfConfigurator):
    """
    This helps with the base configuration part of a mock config.
    """
    # All these arguments are used. Everything made here is typically pushed
    # into MockConfig.
    # pylint: disable=too-many-locals,too-many-arguments,unused-argument
    def __init__(
            self,
            debuglevel=1,
            retries=20,
            obsoletes=True,
            gpgcheck=False,
            assumeyes=True,
            keepcache=True,
            best=True,
            syslog_ident='peridotbuilder',
            syslog_device='',
            metadata_expire=0,
            install_weak_deps=False,
            protected_packages='',
            reposdir='/dev/null',
            logfile='/var/log/yum.log',
            mdpolicy='group:primary',
            rpmverbosity='info',
            repositories=None,
            module_platform_id=None,
            user_agent='peridotbuilder',
            exclude=None,
    ):
        if rpmverbosity not in const.MockConstants.MOCK_RPM_VERBOSITY:
            raise err.ProvidedValueError(f'{rpmverbosity} is not set to a valid value')
        # The repodata setup is a bit weird. What we do is we go through all
        # "locals" for this class and build everything into a dictionary. We
        # later send this and the repositories dictionary to gen_config_section.
        self.__repodata = {}
        for (key, value) in iter(list(locals().items())):
            if key not in ['self', 'repositories'] and value is not None:
                self.__repodata[key] = value

        self.__repositories = {}
        if repositories:
            for repo in repositories:
                self.add_repo_slot(repo)

    def add_repo_slot(self, repo):
        """
        Adds a repository as needed for mock.

        DnfRepoConfig object is expected for repo.
        """
        if not isinstance(repo, DnfRepoConfig):
            raise err.ProvidedValueError(f'This type of repo is not supported: {type(repo)}')
        if repo.name in self.__repositories:
            raise err.ExistsValueError(f'Repository already added: {repo.name}')
        self.__repositories[repo.name] = repo

    def gen_config(self) -> str:
        """
        Generates the configuration that will be used for mock.

        Call this to generate the configuration.
        """
        outter = 'config_opts["dnf.conf"] = """\n'
        outter += self.gen_config_section('main', self.__repodata)
        # Each "repo" instance as a gen_config() command as DnfRepoConfig has
        # that method.
        for repo_name in sorted(self.__repositories.keys()):
            outter += self.__repositories[repo_name].gen_config()
        outter += '"""\n'
        return outter

class DnfRepoConfig(DnfConfigurator):
    """
    This helps with the repo configs that would be in a mock config.
    """
    # pylint: disable=too-many-arguments,unused-argument
    def __init__(self,
                 repoid,
                 name,
                 priority,
                 baseurl=None,
                 enabled=True,
                 gpgcheck=None,
                 gpgkey=None,
                 sslverify=None,
                 module_hotfixes=None
    ):
        """
        Basic dnf repo init, tailored for peridot usage. Mirror lists are *not*
        supported in this class.

        repoid: str
            A unique name for the repository.
        name: str
            Human readable repo description
        priority: str
            Repository priority. Recommended to set if emulating koji tagging
            and/or doing bootstrapping of some sort.
        baseurl: str or list
            A URL to the directory where the repo is located. repodata must be
            there. Multiple URL's can be provided as a list.
        enabled: bool or int
            Enabled (True or 1) or disabled (False or 0) for this repository.
            More than likely if you've added some extra repository, you want it
            enabled. Otherwise, why are you adding it? For aesthetic reasons?
        gpgcheck: bool or int
            Perform a GPG check on packages if set to True/1.
        gpgkey: str or None
            Some URL or location of the repo gpg key
        sslverify: str or None
            Enable SSL certificate verification if set to 1.
        """

        self.__repoconf = {}
        for (key, value) in locals().items():
            if key != 'self' and value is not None:
                self.__repoconf[key] = value

    def gen_config(self) -> str:
        """
        Generates the dnf repo config

        Returns a string
        """
        section = generic_util.trim_non_empty_string(
                'repoid',
                self.__repoconf['repoid']
        )
        return self.gen_config_section(section, self.__repoconf)

    @property
    def name(self):
        """
        Repo name
        """
        return self.__repoconf['name']


# All mock classes
class MockConfig(MockConfigUtils):
    """
    Mock configuration file generator
    """
    # pylint: disable=too-many-locals,too-many-arguments,unused-argument
    def __init__(
            self,
            target_arch,
            root=None,
            chroot_setup_cmd=None,
            chroot_setup_cmd_pkgs=None,
            dist=None,
            releasever=None,
            package_manager: str = 'dnf',
            enable_networking: bool = False,
            files=None,
            macros=None,
            dnf_config=None,
            basedir=None,
            print_main_output: bool = True,
            target_vendor: str = 'redhat',
            vendor: str = 'Default Vendor',
            packager: str = 'Default Packager <packager@noone.home>',
            distsuffix=None,
            distribution=None,
            bootstrap_image_ready=False,
            use_bootstrap_image=False,
            **kwargs
    ):
        """
        Mock config init

        target_arch: string (config_opts['target_arch'])
        files: list (optional)
        dist: must be a string with starting characters . and alphanumeric character
        macros: dict expected, key should start with '%'
        target_vendor: typically 'redhat' and shouldn't be changed in most cases
        vendor: packaging vendor, e.g. Rocky Enterprise Software Foundation
        packager: the packager, e.g. Release Engineering <releng@rockylinux.org>
        chroot_setup_cmd_pkgs: list of packages for the chroot
        """

        # A dist value must be defined. This dist value is typically what we
        # see as the %{dist} macro in RPM distributions. For EL and Fedora,
        # they usually start with a "." and then continue with an alphanumeric
        # character.
        if not dist:
            raise err.MissingValueError('The dist value is NOT defined')
        if dist and not re.match(r'^\.[a-zA-Z0-9]', dist):
            raise err.ProvidedValueError('The dist value does not start with a ' +
                                         '. and alphanumeric character')

        # A releasever value must be defined. This is basically the version of
        # the EL we're building for.
        if not releasever:
            raise err.MissingValueError('The releasever value is NOT defined.')
        if releasever and not re.match(r'^[0-9]+', releasever):
            raise err.ProvidedValueError('The releasever value does not start ' +
                                         'with a number.')

        # Set chroot defaults if necessary. In the constants module, we have a
        # list of the most basic package set required. In the event that
        # someone is building a mock config to use, they can set the
        # chroot_setup_cmd if they wish to something other than install
        # (usually this is almost never the case). More importantly, the
        # packages actually installed into the chroot can be set. Some projects
        # in peridot can potentially dictate this to something other than the
        # defaults.
        if not chroot_setup_cmd:
            chroot_setup_cmd = const.MockConstants.MOCK_DEFAULT_CHROOT_SETUP_CMD
        if not chroot_setup_cmd_pkgs:
            chroot_setup_cmd_pkgs = const.MockConstants.MOCK_DEFAULT_CHROOT_BUILD_PKGS

        # Each mock chroot needs a name. We do not arbitrarily generate any.
        # The admin must be specific on what they want.
        if not root:
            raise err.MissingValueError('The mock root name was not provided.')

        # Here we are building the basic mock configuration. We push most of it
        # into dictionaries and then later translate it all into strings.
        legal_host_arches = self.determine_legal_host_arches(target_arch)
        interpreted_dist = self.determine_dist_macro(dist)
        chroot_pkgs = ' '.join(chroot_setup_cmd_pkgs)
        chroot_setup_cmd_string = chroot_setup_cmd + ' ' + chroot_pkgs
        default_macros = {
                '%_rpmfilename': '%%{NAME}-%%{VERSION}-%%{RELEASE}.%%{ARCH}.rpm',
                '%_host': f'{target_arch}-{target_vendor}-linux-gnu',
                '%_host_cpu': target_arch,
                '%_vendor': target_vendor,
                '%_vendor_host': target_vendor,
                '%vendor': vendor,
                '%packager': packager,
        }
        self.__config_opts = {
                'root': root,
                'target_arch': target_arch,
                'legal_host_arches': legal_host_arches,
                'chroot_setup_cmd': chroot_setup_cmd_string,
                'dist': dist.strip('.'),
                'releasever': releasever,
                'basedir': basedir,
                'use_host_resolv': enable_networking,
                'rpmbuild_networking': enable_networking,
                'print_main_output': print_main_output,
                'macros': default_macros,
                'bootstrap_image_ready': bootstrap_image_ready,
                'use_bootstrap_image': use_bootstrap_image,
        }
        self.__config_opts.update(**kwargs)
        self.__extra_config_opts = collections.defaultdict(list)
        self.__files = {}
        self.__macros = {}
        self.__plugins = {}
        if files:
            for chroot_file in files:
                self.add_file(chroot_file)

        # Set absolute default macros for each build. This is a partial carry
        # over from peridot v1. We add these to an /etc/rpm/macros... file on
        # purpose. Otherwise, if they are set as macros in config_opts, they
        # are placed in /builddir/.rpmmacros, which cannot be overriden. Doing
        # this ensures we can override these macros (e.g. for modules)
        starter_macros = {
                '%dist': interpreted_dist,
                '%distribution': distribution,
        }
        self.add_macros(starter_macros, macro_file='/etc/rpm/macros.xx')
        if macros:
            self.add_macros(macros)

        # Set the absolute disabled plugins for each build. These three are
        # disabled on purpose. Do NOT alter these. Do NOT attempt to override
        # them. There should never be a reason to ever have these enabled in a
        # build system nor in development tools that use this module.
        yum_cache_plugin = MockPluginConfig(name='yum_cache', enable=False)
        root_cache_plugin = MockPluginConfig(name='root_cache', enable=False)
        ccache_plugin = MockPluginConfig(name='ccache', enable=False)
        self.add_plugin(yum_cache_plugin)
        self.add_plugin(root_cache_plugin)
        self.add_plugin(ccache_plugin)

        self.__dnf_config = dnf_config

    def add_file(self, chroot_file):
        """
        Adds a chroot file to the configuration.
        """
        if chroot_file.file in self.__files:
            raise err.ProvidedValueError(f'file {chroot_file.file} is already added')
        self.__files[chroot_file.file] = chroot_file

    def add_macros(self, macro_set, macro_file='/etc/macros/macros.zz'):
        """
        Adds a set of macros to a mock configuration. This generates a file
        that will be placed into the mock chroot, rather than
        /builddir/.rpmmacros made by config_opts.
        """
        macro_data = ''
        for key, value in macro_set.items():
            if '%' not in key:
                macro_name = f'%{key}'
            else:
                macro_name = key

            if not value:
                continue

            macro_value = value

            macro_data += f'{macro_name} {macro_value}\n'

        macro_config = MockMacroFileConfig(content=macro_data, file=macro_file)
        returned_content = macro_config.gen_config()
        self.__macros[macro_file] = returned_content

    def add_plugin(self, plugin):
        """
        Adds a mock plugin to the configuration.
        """
        if plugin.name in self.__plugins:
            raise err.ProvidedValueError(f'plugin {plugin.name} is already configured')
        self.__plugins[plugin.name] = plugin

    def module_install(self, module_name):
        """
        Adds a module to module_install
        """
        if 'module_install' not in self.__config_opts:
            self.__config_opts['module_install'] = []

        if module_name in self.__config_opts['module_install']:
            raise err.ExistsValueError(f'{module_name} is already provided in module_install')

        self.__config_opts['module_install'].append(module_name)

    def module_enable(self, module_name):
        """
        Adds a module to module_enable
        """
        if 'module_enable' not in self.__config_opts:
            self.__config_opts['module_enable'] = []

        if module_name in self.__config_opts['module_enable']:
            raise err.ExistsValueError(f'{module_name} is already provided in module_enable')

        self.__config_opts['module_enable'].append(module_name)

    def add_config_opt(self, key: str, value: str):
        """
        Use this to add additional options not covered by this module
        """
        self.__extra_config_opts[key].append(value)

    @staticmethod
    def determine_dist_macro(dist: str) -> str:
        """
        Return a string of the interpreted dist macro. This will typically
        match current EL release packages.
        """
        # We don't want a case where we are sending "~bootstrap" as the dist
        # already. So we're stripping it and letting the build figure it out
        # for itself. The macro with_bootstrap conditional should dictate it.
        if "~bootstrap" in dist:
            starting_dist = dist.replace('~bootstrap', '')
        else:
            starting_dist = dist

        # This is the current dist value that is used in current EL's. It will
        # likely change over time. This value is *also* provided in
        # system-release, but having it here is to make sure it *is* here just
        # in case. This is especially useful when bootstrapping from ELN or
        # stream.
        # pylint: disable=line-too-long,consider-using-f-string
        dist_value = '%{{!?distprefix0:%{{?distprefix}}}}%{{expand:%{{lua:for i=0,9999 do print("%{{?distprefix" .. i .."}}") end}}}}{0}%{{?distsuffix}}%{{?with_bootstrap:~bootstrap}}'.format(starting_dist)
        return dist_value

    # pylint: disable=too-many-return-statements
    @staticmethod
    def determine_legal_host_arches(target_arch: str) -> tuple:
        """
        Return a tuple of acceptable arches for a given architecture. This will
        appear as a list in the final mock config.
        """
        # The legal_host_arches is typically a tuple of supported arches for a
        # given platform. Based on the target_arch sent, we'll set the legal
        # arches.

        # We can easily use "switch" here but we are accounting for python 3.9
        # at this time, which does not have it.
        returner = {
                'x86_64': const.MockConstants.MOCK_X86_64_LEGAL_ARCHES,
                'i386': const.MockConstants.MOCK_I686_LEGAL_ARCHES,
                'i486': const.MockConstants.MOCK_I686_LEGAL_ARCHES,
                'i586': const.MockConstants.MOCK_I686_LEGAL_ARCHES,
                'i686': const.MockConstants.MOCK_I686_LEGAL_ARCHES,
                'aarch64': const.MockConstants.MOCK_AARCH64_LEGAL_ARCHES,
                'armv7hl': const.MockConstants.MOCK_ARMV7HL_LEGAL_ARCHES,
                'ppc64le': const.MockConstants.MOCK_PPC64LE_LEGAL_ARCHES,
                's390x': const.MockConstants.MOCK_S390X_LEGAL_ARCHES,
                'riscv64': const.MockConstants.MOCK_RISCV64_LEGAL_ARCHES,
                'noarch': const.MockConstants.MOCK_NOARCH_LEGAL_ARCHES
        }.get(target_arch, None)

        if returner:
            return returner

        return err.ProvidedValueError(f'Legal arches not found for {target_arch}.')

    def set_dnf_config(self, dnf_config):
        """
        Adds a dnf config section
        """
        self.__dnf_config = dnf_config

    # Disabling until I can figure out a better way to handle this
    # pylint: disable=too-many-branches
    def export_mock_config(self, config_file, root=None):
        """
        Exports the mock configuration to a file.
        """
        if not root:
            if self.__config_opts.get('root'):
                root = self.__config_opts.get('root')
            else:
                raise err.MissingValueError('root value is missing. This should ' +
                                            'not have happened and is likely the ' +
                                            'result of this module being ' +
                                            'modified and not tested.')

        if not isinstance(config_file, str):
            if isinstance(config_file, IOBase):
                raise err.ProvidedValueError('config_file must be a string. it cannot ' \
                                             'be an open file handle.')
            raise err.ProvidedValueError('config_file must be a string.')

        # This is where we'll write the file. We'll go through each
        # configuration option, generate their configs as they're found, and
        # write them. It should look close, if not identical to a typical mock
        # configuration.
        with open(config_file, 'w', encoding='utf-8') as file_descriptor:
            try:
                if root:
                    file_descriptor.write(self.gen_config_option('root', root))
                for option, value in sorted(self.__config_opts.items()):
                    if option == 'root' or value is None:
                        continue
                    file_descriptor.write(self.gen_config_option(option, value))
                for option, value_list in sorted(self.__extra_config_opts.items()):
                    for value in value_list:
                        file_descriptor.write(self.gen_config_option(option, value, append=True))
                for plugin in self.__plugins.values():
                    file_descriptor.write(plugin.gen_config())
                for macro_file in self.__macros.values():
                    file_descriptor.write(macro_file)
                for chroot_file in self.__files.values():
                    file_descriptor.write(chroot_file.gen_config())
                if self.__dnf_config:
                    file_descriptor.write(self.__dnf_config.gen_config())
            except Exception as exc:
                raise err.ConfigurationError('There was an error exporting the mock ' \
                        f'configuration: {exc}')
            finally:
                file_descriptor.close()

    @property
    def mock_config_hash(self):
        """
        Creates a hash sum of the configuration. Could be used for tracking
        and/or comparison purposes.

        This may not currently work at this time.
        """
        hasher = hashlib.sha256()
        file_descriptor = StringIO()
        self.export_mock_config(file_descriptor)
        file_descriptor.seek(0)
        hasher.update(file_descriptor.read().encode('utf-8'))
        file_descriptor.close()
        return hasher.hexdigest()

### Start Plugins
class MockPluginConfig(MockConfigUtils):
    """
    Mock plugin configuration helper. For cases where some plugin doesn't have
    some sort of class in this module.
    """
    def __init__(
            self,
            name: str,
            enable: bool,
            **kwargs
    ):
        """
        Plugin config init. Used to enable/disable plugins. Additional plugin
        options can be defined in kwargs (may or may not work)

        name: plugin name, string
        enable: boolean
        """
        self.name = copy.copy(name)
        self.enable = enable
        self.opts = copy.copy(kwargs)

    def gen_config(self):
        """
        Helps add a plugin configuration to mock
        """
        plugin_name = self.name
        config_string_status = self.enable
        outter = self.gen_config_string_with_opts(
                name=plugin_name,
                status=config_string_status,
                opts=self.opts
        )
        return outter

class MockBindMountPluginConfig(MockConfigUtils):
    """
    Mock plugin configuration helper
    """
    def __init__(
            self,
            enable: bool,
            mounts: list
    ):
        """
        Plugin config init. Used to enable/disable bind mount plugin.

        enable: boolean
        mounts: list of tuples
        """
        self.name = 'bind_mount'
        self.enable = enable
        self.mounts = mounts

    def gen_config(self):
        """
        Helps add a plugin configuration to mock
        """
        bind_config_status = self.config_string(self.enable)

        # Documentation wants a ['dirs'] section added, so we're obliging.
        outter = self.gen_config_string(name='bind_mount', status=bind_config_status)

        if not self.enable or not self.mounts:
            return outter

        for local_path, mock_chroot_path in self.mounts:
            # pylint: disable=line-too-long
            outter += f'config_opts["plugin_conf"]["bind_mount_opts"]["dirs"].append(("{local_path}", "{mock_chroot_path}"))\n'

        return outter

class MockChrootScanPluginConfig(MockConfigUtils):
    """
    Helps setup the chroot scan plugin.
    """

    def __init__(
            self,
            enable,
            **kwargs
    ):
        """
        Inits the plugin configuration.

        enable: bool
        kwargs: additional options can be sent in here
        """
        self.name = 'chroot_scan'
        self.enable = enable
        self.opts = copy.copy(kwargs)

    def gen_config(self):
        """
        Helps add a plugin configuration to mock
        """
        chroot_config_status = self.enable

        # This one is weird. The documentation specifically wants a "dict" as a
        # string... Not really clear why. But we'll roll with it.
        outter = self.gen_config_string(
                name='chroot_scan',
                status=chroot_config_status
        )

        opts_dict = {}
        for key, option in sorted(self.opts.items()):
            opts_dict[key] = option

        outter += f'config_opts["plugin_conf"]["chroot_scan_opts"] = {opts_dict}\n'
        return outter

class MockShowrcPluginConfig(MockConfigUtils):
    """
    Helps enable the showrc plugin. Useful for showing defined rpm macros for a
    build.
    """

    def __init__(self, enable):
        """
        Inits the plugin configuration.

        enable: bool
        """
        self.name = 'showrc'
        self.enable = enable

    def gen_config(self):
        """
        Helps add a plugin configuration to mock
        """
        showrc_config_status = self.enable
        outter = f'config_opts["plugin_conf"]["showrc_enable"] = {showrc_config_status}\n'
        return outter

### End Plugins

class MockChrootFileConfig:
    """
    Helps embed files into a mock chroot. May be useful to trick builds if
    necessary but also could help with things like secureboot if needed.
    """
    def __init__(
            self,
            file: str,
            content=None
    ):
        """
        Create a file to embed into the mock root
        """

        if not content:
            raise err.MissingValueError('Macro content was not provided')

        self.file = file
        self._content = content

    def gen_config(self):
        """
        Return a string to be added to mock config
        """
        return f'config_opts["files"]["{self.file}"] = """{self._content}\n"""\n\n'

class MockMacroConfig:
    """
    Helps add macros into a mock configuration. This is a typical staple of
    builds. In most cases, you won't need this and instead will use
    MockMacroFileConfig.
    """
    def __init__(
            self,
            name: str,
            value: str
    ):
        """
        init the class
        """
        self.name = name
        self.value = value

    def gen_config(self):
        """
        Generate the macro option
        """
        return f'config_opts["macros"]["{self.name}"] = "{self.value}"'

class MockMacroFileConfig:
    """
    Helps add macros into a mock configuration into a file instead.
    """
    def __init__(
            self,
            file: str = '/etc/rpm/macros.zz',
            content=None
    ):
        """
        Create a macro file to embed into the mock root
        """

        if not content:
            raise err.MissingValueError('Macro content was not provided')

        self.file = file
        self._content = content

    def gen_config(self):
        """
        Return a string to be added to mock config
        """
        return f'config_opts["files"]["{self.file}"] = """\n\n{self._content}\n"""\n\n'
