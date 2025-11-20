# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
All constants
"""
from enum import Enum

__all__ = [
        'RpmConstants',
        'ErrorConstants',
        'MockConstants',
        'GitConstants'
]

# pylint: disable=too-few-public-methods
class RpmConstants:
    """
    All RPM constants are here. These are used mainly in the rpm utility but
    could be used elsewhere.
    """
    RPM_HEADER_MAGIC = b'\xed\xab\xee\xdb'
    RPM_TAG_HEADERSIGNATURES = 62
    RPM_TAG_FILEDIGESTALGO = 5011
    RPM_SIGTAG_DSA = 267
    RPM_SIGTAG_RSA = 268
    RPM_SIGTAG_PGP = 1002
    RPM_SIGTAG_MD5 = 1004
    RPM_SIGTAG_GPG = 1005

    RPM_FILEDIGESTALGO_IDS = {
        None: 'MD5',
        1: 'MD5',
        2: 'SHA1',
        3: 'RIPEMD160',
        8: 'SHA256',
        9: 'SHA384',
        10: 'SHA512',
        11: 'SHA224'
    }

    # rpmspec will be used in niche scenarios. several things here are set to
    # %{nil} because there cases where some spec files can't be parsed properly
    # without the macros existing, depending on how the system was setup.
    RPMSPEC_DEFINITIONS = {
        "__python3": "/usr/bin/python3",
        "forgemeta": "%{nil}",
        "gometa": "%{nil}",
        "ldconfig_scriptlets(n:)": "%{nil}",
        "pesign": "%{nil}",      # some SB packages don't parse without this set
        "efi_has_alt_arch": "0", # some arches simply don't have efi, so always 0
    }

#   RPM_PATCH_OBSOLETE = 0
#   RPM_PATCH_P_SPACE = 1
#   RPM_PATCH_P_NOSPACE = 2
#   RPM_PATCH_KERNEL = 3
#   RPM_PATCH_INC_FILE = 4
#   RPM_PATCH_AUTOSETUP = 5
#   RPM_SPEC_DIRECTIVE_PATCH = "Patch"
#   RPM_SPEC_DIRECTIVE_SOURCE = "Source"

    RPM_AUTORELEASE_FINAL_LINE = '}%{?-e:.%{-e*}}%{?-s:.%{-s*}}%{!?-n:%{?dist}}'

    class RpmSpecPatchTypes(Enum):
        """
        Patch types
        """
        OBSOLETE = 0
        P_SPACE = 1
        P_NOSPACE = 2
        KERNEL = 3
        INC_FILE = 4
        AUTOSETUP = 5

    class RpmSpecDirectives(Enum):
        """
        Directives
        """
        PATCH = "Patch"
        SOURCE = "Source"

# pylint: disable=too-few-public-methods
class ErrorConstants:
    """
    All error codes as constants.

    9000-9099: Generic Errors, this means not entirely specific to a process or
    component.

    9100-9199: Mock errors, any error that can occur in mock.

    9300-9399: Git errors, any error that happens in git
    9400-9499: RPM errors, specifically for rpm processing
    9500-9599: Uploader errors
    9600-9699: Editor errors, for when patching doesn't go right
    """
    # General errors
    ERR_GENERAL = 9000
    ERR_PROVIDED_VALUE = 9001
    ERR_VALUE_EXISTS = 9002
    ERR_MISSING_VALUE = 9003
    ERR_CONFIGURATION = 9004
    ERR_NOTFOUND = 9005
    ERR_DOWNLOAD = 9006
    ERR_FILEOP = 9007
    # Error in spec file
    MOCK_ERR_SPEC = 9100
    # Error trying to get dependencies for a build
    MOCK_ERR_DEP = 9101
    # Architecture is excluded - there should be no reason this appears normally.
    MOCK_ERR_ARCH_EXCLUDED = 9102
    # A build hung up during build
    MOCK_ERR_BUILD_HUP = 9103
    # Build ran out of disk space
    MOCK_ERR_NO_SPACE = 9104
    # Missing file error
    MOCK_ERR_ENOENT = 9105
    # Files were installed but not packaged
    MOCK_ERR_UNPACKED_FILES = 9106
    # Error in repository
    MOCK_ERR_REPO = 9107
    # Timeout
    MOCK_ERR_ETIMEDOUT = 9108
    # Changelog is not in chronological order
    MOCK_ERR_CHLOG_CHRONO = 9109
    # Invalid conf
    MOCK_ERR_CONF_INVALID = 9110
    # DNF Error
    MOCK_ERR_DNF_ERROR = 9111
    # Result dir generic error
    MOCK_ERR_RESULTDIR_GENERIC = 9180
    # Unexpected error
    MOCK_ERR_UNEXPECTED = 9198
    # Generic error
    MOCK_ERR_GENERIC = 9199
    # Git Generic Error
    GIT_ERR_GENERAL = 9300
    GIT_ERR_COMMIT = 9301
    GIT_ERR_PUSH = 9302
    GIT_ERR_INIT = 9303
    GIT_ERR_CHECKOUT = 9304
    GIT_ERR_APPLY = 9305

    # RPM errors
    RPM_ERR_OPEN = 9400
    RPM_ERR_SIG = 9401
    RPM_ERR_INFO = 9402
    RPM_ERR_BUILD = 9403
    RPM_ERR_SPEC_PARSE = 9404

    # Upload errors
    UPLOAD_ERR = 9500

    # Patch errors
    EDITOR_ERR_GENERIC = 9600
    EDITOR_ERR_CONFIG_VALUE = 9601
    EDITOR_ERR_CONFIG_TYPE = 9602
    EDITOR_ERR_CONFIG_MANY_FILES = 9603

# pylint: disable=too-few-public-methods
class MockConstants:
    """
    All mock constants, usually for defaults
    """
    # I'm aware this line is too long
    MOCK_DEFAULT_CHROOT_BUILD_PKGS = [
            'bash',
            'bzip2',
            'coreutils',
            'cpio',
            'diffutils',
            'findutils',
            'gawk',
            'glibc-minimal-langpack',
            'grep',
            'gzip',
            'info',
            'make',
            'patch',
            'redhat-rpm-config',
            'rpm-build',
            'sed',
            'shadow-utils',
            'system-release',
            'tar',
            'unzip',
            'util-linux',
            'which',
            'xz'
    ]
    MOCK_DEFAULT_CHROOT_SRPM_PKGS = [
            'bash',
            "glibc-minimal-langpack",
            "gnupg2",
            "rpm-build",
            "shadow-utils",
            "system-release"
    ]
    MOCK_DEFAULT_CHROOT_SETUP_CMD = 'install'
    MOCK_CLONE_DIRECTORY = '/var/peridot/peridot__rpmbuild_content'

    # Mock architecture related
    MOCK_X86_64_LEGAL_ARCHES = ('x86_64',)
    MOCK_I686_LEGAL_ARCHES = ('i386', 'i486', 'i586', 'i686', 'x86_64',)
    MOCK_AARCH64_LEGAL_ARCHES = ('aarch64',)
    MOCK_ARMV7HL_LEGAL_ARCHES = ('armv7hl',)
    MOCK_PPC64LE_LEGAL_ARCHES = ('ppc64le',)
    MOCK_S390X_LEGAL_ARCHES = ('s390x',)
    MOCK_RISCV64_LEGAL_ARCHES = ('riscv64',)
    # pylint: disable=line-too-long
    MOCK_NOARCH_LEGAL_ARCHES = ('i386', 'i486', 'i586', 'i686', 'x86_64', 'aarch64', 'ppc64le', 's390x', 'noarch')

    # Mock general config related
    MOCK_DNF_BOOL_OPTIONS = ('assumeyes', 'best', 'enabled', 'gpgcheck',
                             'install_weak_deps', 'keepcache', 'module_hotfixes',
                             'obsoletes')

    MOCK_DNF_STR_OPTIONS = ('debuglevel', 'retries', 'metadata_expire')
    MOCK_DNF_LIST_OPTIONS = ('syslog_device', 'protected_packages')
    MOCK_RPM_VERBOSITY = ('critical', 'debug', 'emergency', 'error', 'info', 'warn')

    # Most mock error codes
    MOCK_EXIT_SUCCESS = 0
    MOCK_EXIT_ERROR = 1
    MOCK_EXIT_SETUID = 2
    MOCK_EXIT_INVCONF = 3
    MOCK_EXIT_CMDLINE = 5
    MOCK_EXIT_INVARCH = 6
    MOCK_EXIT_BUILD_PROBLEM = 10
    MOCK_EXIT_CMDTMOUT = 11
    MOCK_EXIT_ERROR_IN_CHROOT = 20
    MOCK_EXIT_DNF_ERROR = 30
    MOCK_EXIT_EXTERNAL_DEP = 31
    MOCK_EXIT_PKG_ERROR = 40
    MOCK_EXIT_MOCK_CMDLINE = 50
    MOCK_EXIT_BUILDROOT_LOCKED = 60
    MOCK_EXIT_RESULTDIR_NOT_CREATED = 70
    MOCK_EXIT_WEAK_DEP_NOT_INSTALLED = 120
    MOCK_EXIT_SIGHUP_RECEIVED = 129
    MOCK_EXIT_SIGPIPE_RECEIVED = 141
    MOCK_EXIT_SIGTERM_RECEIVED = 143

class GitConstants:
    """
    All git related constants
    """

    CENTOS_LOOKASIDE_PATH = 'https://git.centos.org/sources/${PKG_NAME}/${BRANCH}/${HASH}'
    # pylint: disable=line-too-long
    STREAM_LOOKASIDE_PATH = 'https://sources.stream.centos.org/sources/rpms/${PKG_NAME}/${FILENAME}/${HASH_TYPE}/${HASH}/${FILENAME}'
    FEDORA_LOOKASIDE_PATH = 'https://src.fedoraproject.org/repo/pkgs/${PKG_NAME}/${FILENAME}/${HASH_TYPE}/${HASH}/${FILENAME}'
    ROCKY8_LOOKASIDE_PATH = 'https://rocky-linux-sources-staging.a1.rockylinux.org/${HASH}'
    ROCKY_LOOKASIDE_PATH = 'https://sources.build.resf.org/${HASH}'
