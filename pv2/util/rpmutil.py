# -*- mode:python; coding:utf-8; -*-
# Louis Abel <label@resf.org>
"""
Utility functions for RPM's
"""
import os
import re
import shutil
import stat
from pathlib import Path
import lxml.etree
from pv2.util import error as err
from pv2.util import generic
from pv2.util import processor
from pv2.util.constants import RpmConstants as rpmconst
from pv2.util import log as pvlog

# Address all capitalized vars
# pylint: disable=invalid-name

# We should have the python rpm modules. Forcing `rpm` to be none should make
# that known to the admin that they did not setup their node correctly.
try:
    import rpm
except ImportError:
    rpm = None

# We should have rpmautospec available. There is a good chance that if pv2 is
# used to import from one place to another, and the source uses %autochangelog,
# we should able to fill it in on import.
try:
    from rpmautospec.subcommands import process_distgit
    HAS_RPMAUTOSPEC = True
except ImportError:
    HAS_RPMAUTOSPEC = False
    pvlog.logger.warning('WARNING! rpmautospec was not found on this system and is not loaded.')

__all__ = [
        'add_rpm_key',
        'compare_rpms',
        'get_all_rpm_header_keys',
        'get_exclu_from_package',
        'get_files_from_package',
        'get_rpm_hdr_size',
        'get_rpm_header',
        'get_rpm_metadata_from_hdr',
        'is_debug_package',
        'is_rpm',
        'split_rpm_by_header',
        'verify_rpm_signature',
        'spec_parse',
        'spec_evr',
        'spec_autosetup',
        'spec_autochangelog',
        'spec_autorelease',
        'spec_line_changelog',
        'spec_line_version',
        'spec_line_release',
        'spec_line_epoch',
        'rpmautocl'
]

# NOTES TO THOSE RUNNING PYLINT OR ANOTHER TOOL
#
# It is normal that your linter will say that "rpm" does not have some sort of
# RPMTAG member or otherwise. You will find when you run this module in normal
# circumstances, everything is returned as normal. You are free to ignore those
# linting errors.

def is_debug_package(file_name: str) -> bool:
    """
    Quick utility to state if a package is a debug package

    file_name: str, package filename

    Returns: bool
    """

    file_name_search_rpm_res = re.search(r'.*?\.rpm$', file_name, re.IGNORECASE)
    file_name_search_srpm_res = re.search(r'.*?\.src\.rpm$', file_name, re.IGNORECASE)

    if not file_name_search_rpm_res:
        return False
    if file_name_search_srpm_res:
        return False

    return bool(re.search(r'-debug(info|source)', file_name))

def get_rpm_header(file_name: str, verify_signature: bool = False):
    """
    Gets RPM header metadata. This is a vital component to getting RPM
    information for usage later.

    Returns: dict
    """

    if rpm is None:
        raise err.GenericError("You must have the rpm python bindings installed")

    trans_set = rpm.TransactionSet()
    if not verify_signature:
        # this is harmless.
        # pylint: disable=protected-access
        trans_set.setVSFlags(rpm._RPMVSF_NOSIGNATURES | rpm._RPMVSF_NODIGESTS)

    with open(file_name, 'rb') as rpm_package:
        try:
            hdr = trans_set.hdrFromFdno(rpm_package)
        # pylint: disable=no-member
        except rpm.error as exc:
            pvlog.logger.exception(exc)
            raise err.RpmOpenError('RPM could not be opened: Public key is not available.')
    return hdr

# pylint: disable=too-many-locals
def get_rpm_metadata_from_hdr(hdr) -> dict:
    """
    Asks for RPM header information and generates some basic metadata in the
    form of a dict.

    Currently the metadata returns the following information, and their
    potential use cases:

        * changelog_xml -> Provides the changelog, which could be parsed and
                           placed on to a build's summary page

        * files -> List of all files in the package. Obtained from
                   get_files_from_package

        * obsoletes -> Packages that this obsoletes

        * provides -> Packages that this provides

        * conflicts -> Packages that this conflicts with

        * requires -> Packages that this requires

        * vendor -> Package vendor

        * buildhost -> Which system/container built it

        * filetime -> When the package was built

        * description -> Package description

        * license -> License of the packaged software

        * nvr -> NVR, excluding epoch and arch. This can be used as a build package
                  name, similar to how koji displays a particular build. For
                  example, bash-5.2.15-3.fc38

        * nevra -> Full NEVRA. Could be used as a filing mechanism in a
                   database and/or could be used to be part of a list of what
                   architecture this package may belong to for a particular
                   build.

        * name -> Package name

        * version -> Package version

        * release -> Package release

        * epoch -> Package epoch

        * arch -> Package arch

        * archivesize -> Size of the archive

        * packagesize -> Size of the package
    """
    changelog_result = ''
    header_data = hdr
    file_stuff = get_files_from_package(header_data)
    exclu_stuff = get_exclu_from_package(header_data)
    change_logs = zip(
            # pylint: disable=no-member
            header_data[rpm.RPMTAG_CHANGELOGNAME],
            header_data[rpm.RPMTAG_CHANGELOGTIME],
            header_data[rpm.RPMTAG_CHANGELOGTEXT]
    )
    for name, time, text in reversed(list(change_logs)):
        # I need to come back and address this
        # pylint: disable=c-extension-no-member
        change = lxml.etree.Element(
                'changelog',
                author=generic.to_unicode(name),
                date=generic.to_unicode(time)
        )
        change.text = generic.to_unicode(text)
        changelog_result += generic.to_unicode(lxml.etree.tostring(change, pretty_print=True))

    # Source RPM's can be built on any given architecture, regardless of where
    # they'll be built. There are also cases where an RPM may report some other
    # architecture that may be multilib or not native to the system checking
    # the headers. As a result, the RPM header may return erroneous information if we
    # are trying to look at the metadata of a source package. So this is a hack
    # to determine if we are dealing with a source package.
    # pylint: disable=no-member
    source_files = header_data[rpm.RPMTAG_SOURCE]
    source_pkg = header_data[rpm.RPMTAG_SOURCERPM]
    pkg_arch = generic.to_unicode(header_data[rpm.RPMTAG_ARCH])

    if len(source_files) != 0 or not source_pkg:
        pkg_arch = 'src'

    # The NEVRA exhibits the same issue.
    found_nevra = header_data[rpm.RPMTAG_NEVR] + '.' + pkg_arch

    # This avoids epoch being None or 'None' in the dict.
    found_epoch = header_data[rpm.RPMTAG_EPOCH]
    if not found_epoch:
        found_epoch = ''

    # This avoids the modularity label being None or 'None' in the dict.
    found_modularitylabel = header_data[rpm.RPMTAG_MODULARITYLABEL]
    if not found_modularitylabel:
        found_modularitylabel = ''

    metadata = {
            'changelog_xml': changelog_result,
            'files': file_stuff['file'],
            'obsoletes': header_data[rpm.RPMTAG_OBSOLETENEVRS],
            'provides': header_data[rpm.RPMTAG_PROVIDENEVRS],
            'conflicts': header_data[rpm.RPMTAG_CONFLICTNEVRS],
            'requires': header_data[rpm.RPMTAG_REQUIRENEVRS],
            'vendor': generic.to_unicode(header_data[rpm.RPMTAG_VENDOR]),
            'buildhost': generic.to_unicode(header_data[rpm.RPMTAG_BUILDHOST]),
            'filetime': int(header_data[rpm.RPMTAG_BUILDTIME]),
            'description': generic.to_unicode(header_data[rpm.RPMTAG_DESCRIPTION]),
            'license': generic.to_unicode(header_data[rpm.RPMTAG_LICENSE]),
            'exclusivearch': exclu_stuff['ExclusiveArch'],
            'excludearch': exclu_stuff['ExcludeArch'],
            'nvr': generic.to_unicode(header_data[rpm.RPMTAG_NEVR]),
            'nevra': found_nevra,
            'name': generic.to_unicode(header_data[rpm.RPMTAG_NAME]),
            'version': generic.to_unicode(header_data[rpm.RPMTAG_VERSION]),
            'release': generic.to_unicode(header_data[rpm.RPMTAG_RELEASE]),
            'epoch': found_epoch,
            'arch': pkg_arch,
            'modularitylabel': found_modularitylabel,
            'signature': header_data[rpm.RPMTAG_RSAHEADER],
    }
    for key, rpmkey, in (('archivesize', rpm.RPMTAG_ARCHIVESIZE),
                         ('packagesize', rpm.RPMTAG_SIZE)):
        value = header_data[rpmkey]
        if value is not None:
            value = int(value)
        metadata[key] = value
    return metadata

def compare_rpms(first_pkg, second_pkg) -> int:
    """
    Compares package versions. Both arguments must be a dict.

    Returns an int.
    1  = first version is greater
    0  = versions are equal
    -1 = second version is greater
    """
    # pylint: disable=no-member
    return rpm.labelCompare(
            (first_pkg['epoch'], first_pkg['version'], first_pkg['release']),
            (second_pkg['epoch'], second_pkg['version'], second_pkg['release'])
    )

def is_rpm(file_name: str, magic: bool = False) -> bool:
    """
    Checks if a file is an RPM
    """
    file_name_search_res = re.search(r'.*?\.rpm$', file_name, re.IGNORECASE)
    if magic:
        with open(file_name, 'rb') as file:
            block = file.read(4)
            file.close()
        return bool(block == rpmconst.RPM_HEADER_MAGIC) and bool(file_name_search_res)
    return bool(file_name_search_res)

def get_files_from_package(hdr) -> dict:
    """
    hdr should be the header of the package.

    returns a dict
    """
    cache = {}
    # pylint: disable=no-member
    files = hdr[rpm.RPMTAG_FILENAMES]
    fileflags = hdr[rpm.RPMTAG_FILEFLAGS]
    filemodes = hdr[rpm.RPMTAG_FILEMODES]
    filetuple = list(zip(files, filemodes, fileflags))
    returned_files = {}

    for (filename, mode, flag) in filetuple:
        if mode is None or mode == '':
            if 'file' not in returned_files:
                returned_files['file'] = []
            returned_files['file'].append(generic.to_unicode(filename))
            continue
        if mode not in cache:
            cache[mode] = stat.S_ISDIR(mode)
        filekey = 'file'
        if cache[mode]:
            filekey = 'dir'
        elif flag is not None and (flag & 64):
            filekey = 'ghost'
        returned_files.setdefault(filekey, []).append(generic.to_unicode(filename))
    return returned_files

def get_exclu_from_package(hdr) -> dict:
    """
    Gets exclusivearch and excludedarch from an RPM's header. This mainly
    applies to source packages.
    """
    # pylint: disable=no-member
    excluded_arches = hdr[rpm.RPMTAG_EXCLUDEARCH]
    exclusive_arches = hdr[rpm.RPMTAG_EXCLUSIVEARCH]

    exclu = {
            'ExcludeArch': excluded_arches,
            'ExclusiveArch': exclusive_arches
    }
    return exclu

def get_rpm_hdr_size(file_name: str, offset: int = 0, padding: bool = False) -> int:
    """
    Returns the length of the rpm header in bytes

    Accepts only a file name.
    """
    with open(file_name, 'rb') as file_outer:
        if offset is not None:
            file_outer.seek(offset, 0)
        magic = file_outer.read(4)
        if magic != rpmconst.RPM_HEADER_MAGIC:
            raise err.GenericError(f"RPM error: bad magic: {magic}")

        # Skips magic, plus end of reserve (4 bytes)
        file_outer.seek(offset + 8, 0)

        data = [generic.ordered(x) for x in file_outer.read(8)]
        start_length = generic.conv_multibyte(data[0:4])
        end_length = generic.conv_multibyte(data[4:8])

        hdrsize = 8 + 16 * start_length + end_length

        if padding:
            # signature headers are padded to a multiple of 8 bytes
            hdrsize = hdrsize + (8 - (hdrsize % 8)) % 8

        hdrsize = hdrsize + 8
        file_outer.close()

    return hdrsize

def split_rpm_by_header(hdr) -> tuple:
    """
    Attempts to split an RPM name into parts. Relies on the RPM header. May
    result in failures.

    Only use this if you need simplicity.

    Note: A package without an epoch turns None. We turn an empty string
    instead.

    Note: Splitting a source package will result in an erroneous "arch" field.
    """
    # pylint: disable=no-member
    source_files = hdr[rpm.RPMTAG_SOURCE]
    source_pkg = hdr[rpm.RPMTAG_SOURCERPM]
    pkg_arch = generic.to_unicode(hdr[rpm.RPMTAG_ARCH])

    if len(source_files) != 0 or not source_pkg:
        pkg_arch = 'src'

    name = hdr[rpm.RPMTAG_NAME]
    version = hdr[rpm.RPMTAG_VERSION]
    release = hdr[rpm.RPMTAG_RELEASE]
    epoch = hdr[rpm.RPMTAG_EPOCH]
    arch = pkg_arch

    if not epoch:
        epoch = ''

    return name, version, release, epoch, arch

def get_all_rpm_header_keys(hdr) -> dict:
    """
    Gets all applicable header keys from an RPM.
    """
    returner = {}
    # pylint: disable=no-member
    fields = [rpm.tagnames[k] for k in hdr.keys()]
    for field in fields:
        hdr_key = getattr(rpm, f'RPMTAG_{field}', None)
        returner[field] = hdr_key

    return returner

def quick_bump(file_name: str, user: str, comment: str):
    """
    Does a quick bump of a spec file. For dev purposes only.

    Loosely borrowed from sig core toolkit mangler
    """
    bumprel = ['rpmdev-bumpspec', '-D', '-u', user, '-c', comment, file_name]
    success = processor.run_check_call(bumprel)
    return success

def verify_rpm_signature(file_name: str) -> bool:
    """
    Returns a boolean on if the RPM signature can be verified by what is
    currently imported into the RPM keyring.
    """
    trans_set = rpm.TransactionSet()
    with open(file_name, 'rb') as rpm_package:
        try:
            trans_set.hdrFromFdno(rpm_package)
        # pylint: disable=bare-except
        except:
            return False
    return True

def add_rpm_key(file_name: str):
    """
    Adds a RPM signing signature to the keyring
    """
    with open(file_name, 'rb') as key:
        keydata = key.read()
        keydata.close()

    try:
        # pylint: disable=no-member
        pubkey = rpm.pubkey(keydata)
        keyring = rpm.keyring()
        keyring.addKey(pubkey)
    # pylint: disable=no-member
    except rpm.error as exc:
        raise err.RpmSigError(f'Unable to import signature: {exc}')

# The spec file will be parsed by the rpm module
def spec_parse(spec_file_path, dist: str = "%{nil}", release: str = None) -> list[str]:
    """
    Parses the spec file given to it. Equivalent to rpmspec. A dist tag can be
    optionally defined, which will alter the result of the "Release" directive
    in the spec file in most (if not all) packages.

    Equivalent rpmspec command:
        % rpmspec -q --parse <spec> \
                --define "dist <value or %{nil}>" \
                --define "__python3 /usr/bin/python3" \
                --define "forgemeta %{nil}" \
                --define "gometa %{nil}" \
                --define "ldconfig_scriptlets(n:) %{nil}" \
                --define "pesign %{nil}" \
                --define "efi_has_alt_arch 0" \
                --define "rhel <value or %{nil}" \
                --define "centos <value or %{nil}" \
                --define "rocky <value or %{nil}"
    """
    try:
        spec_path = Path(spec_file_path)
        source_path = spec_path.parent
        # pylint: disable=no-member
        rpm.addMacro("dist", dist)
        rpm.addMacro("_topdir", str(source_path))
        for m in rpmconst.RPMSPEC_DEFINITIONS.items():
            rpm.addMacro(m[0], m[1])

        if release:
            rpm.addMacro("rhel", release)
            rpm.addMacro("centos", release)
            rpm.addMacro("rocky", release)
            rpm.addMacro("fedora", "%{nil}")

        s = rpm.spec(str(spec_path))
        return s.parsed.splitlines()

    # pylint: disable=no-member
    except rpm.error as exc:
        raise err.RpmParseError(f"Failed to parse spec file: {exc}")

def spec_evr(spec_file_data: list[str]) -> tuple[str, ...]:
    """
    Provides EVR information from parsed spec data. Used for changelogs.
    """
    epoch, version, release = None, None, None
    for i, line in enumerate(spec_file_data):
        if epoch is None and line.startswith("Epoch:"):
            epoch = line.rstrip().split()[-1]
        if version is None and line.startswith("Version:"):
            version = line.rstrip().split()[-1]
        if release is None and line.startswith("Release:"):
            release = spec_file_data[i].rstrip().split()[-1]

    return epoch, version, release

# The spec file will be brought in as a list and read as such
def spec_autosetup(rpm_spec: list[str]) -> bool:
    """
    Determines if there's any type of autosetup
    """
    # Every one of these shouldn't be commented if they're being used. We don't
    # want to erroneously find it if it's in a comment and act on it. That
    # would be dumb.
    pattern = re.compile(r'^\s?%(autosetup|forgeautosetup|autopatch)')
    return any(pattern.match(line) for line in rpm_spec)

def spec_autochangelog(rpm_spec: list[str]) -> bool:
    """
    Determines if %autochangelog is in the rpm spec
    """
    # This makes sure that %autochangelog isn't commented out so that way we
    # don't get confused. And just in case a packager messages up somewhere,
    # check for whitespace. Very rare that this should happen.
    pattern = re.compile(r'^\s?%autochangelog')
    return any(pattern.match(line) for line in rpm_spec)

def spec_autorelease(rpm_spec: list[str]) -> bool:
    """
    Determines if %autorelease is in the rpm spec
    """
    # Release is ALWAYS at the beginning of a line.
    pattern = re.compile(r'^Release:.*%autorelease')
    return any(pattern.match(line) for line in rpm_spec)

def spec_line_changelog(line: str) -> bool:
    """
    Determines if this line is the start of the changelog
    """
    return "%changelog" == line.strip('\n \t')

def spec_line_version(line: str) -> bool:
    """
    Determines if this line is the Version: directive
    """
    return line.startswith("Version:")

def spec_line_release(line: str) -> bool:
    """
    Determines if this line is the Release: directive
    """
    return line.startswith("Release:")

def spec_line_epoch(line: str) -> bool:
    """
    Determines if this line is the Epoch: directive
    """
    return line.startswith("Epoch:")

def rpmautocl(path_to_spec: str):
    """
    Performs rpmautospec commands.
    """
    if not HAS_RPMAUTOSPEC:
        return None

    AUTOCHANGELOG = False
    AUTORELEASE = False
    spec_file = generic.read_file_to_list(path_to_spec)

    autochangelog_found = spec_autochangelog(spec_file)
    autorelease_found = spec_autorelease(spec_file)

    if autochangelog_found:
        AUTOCHANGELOG = True
        pvlog.logger.info('autochangelog found, attempting to append')
    if autorelease_found:
        AUTORELEASE = True
        pvlog.logger.info('autorelease found, attempting to evaluate')

    if AUTOCHANGELOG or AUTORELEASE:
        try:
            process_distgit.do_process_distgit(
                    path_to_spec,
                    '/tmp/temporary_name.spec'
            )
        except Exception as exc:
            raise err.GenericError('There was an error with autospec.') from exc
        shutil.copy('/tmp/temporary_name.spec',
                    f'{path_to_spec}')

        os.remove('/tmp/temporary_name.spec')

    else:
        pvlog.logger.info('No auto macros found nor processed')

    return True

def check_obsolete_patch(rpm_spec: list[str]):
    """
    Checks for obsolete patch
    """
    pattern = re.compile(r"^%patch\d+")
    return any(pattern.match(line) for line in rpm_spec)
