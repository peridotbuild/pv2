# -*- mode:python; coding:utf-8; -*-
# Louis Abel <label@resf.org>
"""
Utility functions for Modularity
"""
import datetime
import hashlib
import gi
from pv2.util import error as err
from pv2.util import constants as const
from pv2.util import generic
from pv2.util import fileutil

gi.require_version('Modulemd', '2.0')
# Note: linter says this should be at the top. but then the linter says that
# everything else should be above it. it's fine here.
# pylint: disable=wrong-import-order,wrong-import-position
from gi.repository import Modulemd

__all__ = [
        'GenericModuleHandler',
        'ArtifactHandler',
        'ModuleMangler'
]

class GenericModuleHandler:
    """
    Generic module utility functions
    """
    @staticmethod
    def gen_stream_prefix(major: int, minor: int, patch: int) -> int:
        """
        Generates a module stream prefix if one isn't provided by some other
        means.
        """
        major_version = str(major)
        minor_version = str(minor) if len(str(minor)) > 1 else f'0{str(minor)}'
        patch_version = str(patch) if len(str(patch)) > 1 else f'0{str(patch)}'
        return int(f'{major_version}{minor_version}{patch_version}')

    @staticmethod
    def gen_stream_version(prefix: int) -> int:
        """
        Generates a module stream version. Requires an initial prefix (like
        90200 or similar).
        """
        timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
        return int(f'{prefix}{timestamp}')

    @staticmethod
    def gen_stream_dist_prefix(major: int, minor: int, patch: int) -> str:
        """
        Generates a dist prefix (elX.Y.Z)
        """
        major_version = str(major)
        minor_version = str(minor)
        patch_version = str(patch)
        return f'el{major_version}.{minor_version}.{patch_version}'

    @staticmethod
    def gen_stream_dist_macro(
            dist_prefix: str,
            stream,
            index=None,
            scratch_build=False
    ) -> str:
        """
        Generates a dist macro. stream should be a Modulemd.ModuleStreamV2 object
        """
        # Fedora uses + it seems, while there are others who seem to use _.
        # We'll just use +
        # (Hopefully I did this better than in lazybuilder)
        mod_prefix = 'module+'

        # If this is a scratch build, change the initial prefix. Should be like
        # what MBS does.
        if scratch_build:
            mod_prefix = 'scrmod+'

        dist_string = '.'.join([
            stream.get_module_name(),
            stream.get_stream_name(),
            str(stream.get_version()),
            str(stream.get_context())
            ]
        ).encode('utf-8')

        dist_hash = hashlib.sha1(dist_string, usedforsecurity=False).hexdigest()[:8]
        template = f'.{mod_prefix}{dist_prefix}+{index}+{dist_hash}'

        return template

    @staticmethod
    def gen_stream_build_deps():
        """
        Gets a module stream's build deps
        """
        return 'how'

    @staticmethod
    def gen_stream_runtime_deps():
        """
        Gets a module stream's runtime deps
        """
        return 'how'

    @staticmethod
    def gen_xmd_data(data: dict):
        """
        Generates basic XMD information
        """
        xmd = {'peridot': data}
        return xmd

    @staticmethod
    def gen_module_defaults(name):
        """
        Creates a modulemd default object
        """
        return Modulemd.DefaultsV1.new(name)

    @staticmethod
    def merge_modules(module_a, module_b):
        """
        Merges two module yamls together
        """
        merge_object = Modulemd.ModuleIndexMerger.new()
        merge_object.associate_index(module_b, 0)
        merge_object.associate_index(module_a, 0)
        return merge_object.resolve()

    @staticmethod
    def dump_to_yaml(stream):
        """
        Dumps a module stream to YAML string
        """
        module_index = Modulemd.ModuleIndex.new()
        module_index.add_module_stream(stream)
        return module_index.dump_to_string()

    @staticmethod
    def get_stream_metadata(module, stream):
        """
        Gets a module's general information. Expects a Modulemd.Module object
        and a Modulemd.ModuleStreamV2 object.
        """
        module_dict = {
                'name': stream.get_module_name(),
                'stream': stream.get_stream_name(),
                'arch': stream.get_arch(),
                'version': stream.get_version(),
                'context': stream.get_context(),
                'summary': stream.get_summary(),
                'is_default_stream': False,
                'default_profiles': [],
                'yaml_template': __class__.dump_to_yaml(stream)
        }
        defaults = module.get_defaults()

        if not defaults:
            return module_dict

        default_stream = defaults.get_default_stream()
        module_dict['is_default_stream'] = stream.get_stream_name() == default_stream
        module_dict['default_profiles'] = defaults.get_default_profiles_for_stream(
                stream.get_stream_name()
        )

        return module_dict

# pylint: disable=too-few-public-methods
class ArtifactHandler:
    """
    Handles artifacts for a module. Typically RPMs
    """
    # pylint: disable=too-many-arguments
    def __init__(
            self,
            name: str,
            version: str,
            release: str,
            arch: str,
            epoch=None
    ):
        """
        Initialize wrapper
        """
        self.name = name
        self.version = version
        self.release = release
        self.arch = arch
        self.epoch = epoch

    def return_artifact(self) -> str:
        """
        Returns artifact string
        """
        epoch = self.epoch if self.epoch else '0'
        return f'{self.name}-{epoch}:{self.version}-{self.release}.{self.arch}'

class ModuleMangler:
    """
    Specific functions for dealing with module yamls.
    """
    def __init__(self):
        """
        Initialize class
        """
