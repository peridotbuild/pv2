# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
rpm spec operations
"""

import re
from pv2.util.constants import RpmConstants as rpmconst
from pv2.util import log as pvlog
from pv2.util import error as err
from pv2.util import rpmutil

def generate_patch_line(
        patch_name: str,
        patch_number: str,
        directive_type: rpmconst.RpmSpecPatchTypes
    ) -> str:
    """
    Generates a patch line
    """
    patch_line = ""
    if directive_type == rpmconst.RpmSpecPatchTypes.OBSOLETE:
        patch_line = f"%patch{patch_number} -p1"
    elif directive_type == rpmconst.RpmSpecPatchTypes.P_SPACE:
        patch_line = f"%patch -P {patch_number} -p1"
    elif directive_type == rpmconst.RpmSpecPatchTypes.P_NOSPACE:
        patch_line = f"%patch -P{patch_number} -p1"
    elif directive_type == rpmconst.RpmSpecPatchTypes.KERNEL:
        patch_line = f"ApplyPatch {patch_name}.patch"
    else:
        raise err.RpmParseError("Unknown patch type")

    return patch_line

def get_last_directive(
        spec_data: list[str],
        directive_type: rpmconst.RpmSpecDirectives):
    """
    Gets the last directive of a given type
    """
    last_number = None
    last_idx = None
    no_numbers = False
    conditional = False
    last_endif_idx = None

    # Check for the conditional blocks
    for i, line in enumerate(spec_data):
        if re.match(r"^%endif\b", line):
            conditional = True
            last_endif_idx = i - 1
        elif re.match(r"^%if*", line) and conditional:
            conditional = False

        result = re.match(rf"{directive_type.value}([0-9]*):", line)
        if result:
            if not conditional:
                last_idx = i
            if result.group(1):
                last_number = int(result.group(1))
            else:
                last_number = 0
                no_numbers = True
            break

    if last_idx is None and last_endif_idx is not None:
        last_idx = last_endif_idx

    if last_number is None:
        if directive_type == rpmconst.RpmSpecDirectives.PATCH:
            pvlog.logger.warning("There were no %s directives found", directive_type.value)
            pvlog.logger.warning("We will attempt to add a new directive")
        else:
            raise err.RpmParseError("Unable to parse, there was no {directive_type.value} found")

    return (last_number, last_idx, no_numbers)

def get_source_ids(spec_data: list[str]):
    """
    Gets the ID's of all sources and patches
    """
    patches = []
    sources = []
    patchregex = re.compile(r"^Patch([0-9]+):")
    sourceregex = re.compile(r"^Source([0-9]+):")
    pvlog.logger.info("Finding every source ID in the spec file...")
    for line in spec_data:
        patch_check = patchregex.match(line)
        source_check = sourceregex.match(line)

        if patch_check is not None:
            patches.append(int(patch_check.group(1)))
        if source_check is not None:
            sources.append(int(source_check.group(1)))

    return patches, sources

def get_patch_type_by_line(line: str) -> rpmconst.RpmSpecPatchTypes:
    """
    Get's a patch type by the line sent
    """
    if re.match(r"^%patch[0-9]{1,5}", line):
        return rpmconst.RpmSpecPatchTypes.OBSOLETE
    if re.match(r"^%patch\s+-P\s+[0-9]{1,5}", line):
        return rpmconst.RpmSpecPatchTypes.P_SPACE
    if re.match(r"^%patch\s+-P[0-9]{1,5}", line):
        return rpmconst.RpmSpecPatchTypes.P_NOSPACE
    # There should be no reason to reach this unless the kernel is named
    # something else, like kernel-blah
    if re.match(r"^(ApplyOptionalPatch|ApplyPatch)", line):
        return rpmconst.RpmSpecPatchTypes.KERNEL
    return None

# pylint: disable=too-many-return-statements
def get_patch_type(
        spec_data: list[str],
        package_name: str,
        patch_file: bool) -> rpmconst.RpmSpecPatchTypes:
    """
    Get's a patch type and sends it back
    """
    pvlog.logger.info("Determining how this package applies patches...")
    if package_name == "kernel":
        pvlog.logger.info("This is a kernel package")
        return rpmconst.RpmSpecPatchTypes.KERNEL
    if patch_file:
        pvlog.logger.info("This package contains a patch file")
        return rpmconst.RpmSpecPatchTypes.INC_FILE
    if rpmutil.spec_autosetup(spec_data):
        pvlog.logger.info("This package uses autosetup")
        return rpmconst.RpmSpecPatchTypes.AUTOSETUP
    for line in spec_data:
        patch_type = get_patch_type_by_line(line)
        if patch_type is not None:
            return patch_type
    return None

def get_patch_idx_insert(spec_data: list[str]) -> int:
    """
    Gets where the patch insert should be
    """
    conditional = False
    start_idx = None
    last_patch_idx = None
    for i, line in enumerate(spec_data):
        if last_patch_idx is None and re.match(r"^%endif\b", line):
            conditional = True
            start_idx = i
        elif re.match(r"^%if*", line) and conditional:
            conditional = False
            if last_patch_idx is None:
                start_idx = None
        patch_line = get_patch_type_by_line(line)
        if (last_patch_idx is None and patch_line is not None):
            last_patch_idx = i
    insert_idx = start_idx if start_idx is not None else last_patch_idx
    return insert_idx

def get_setup_line(spec_data: list[str]) -> int:
    """
    Gets the line number of where %setup is, assuming that's what it is
    """
    for i, line in enumerate(spec_data):
        setup_line = re.match(r"^%setup\b", line)
        if setup_line:
            return i
    return None

def upload_to_lookaside(source_name):
    """
    Uploads to lookaside
    """
    # inherit the upload module
    print(source_name)

def get_new_number(spec_data, no_numbers, directive_type, last_number, source_number):
    """
    Gets the new number for a source or patch file
    """
    current_source_ids, current_patch_ids = get_source_ids(spec_data)
    conflict = False

    if no_numbers:
        new_number = ""
    else:
        new_number = str(last_number + 1)
        if source_number != -1:
            if directive_type == rpmconst.RpmSpecDirectives.PATCH:
                if source_number in current_patch_ids:
                    conflict = True
            if directive_type == rpmconst.RpmSpecDirectives.SOURCE:
                if source_number in current_source_ids:
                    conflict = True
            new_number = str(source_number)

    if conflict:
        raise err.RpmParseError(
                f"{directive_type.value} {str(source_number)} already exists.")

    return new_number

def add_patch_line(spec_data, source_name, patch_type, new_number):
    """
    Adds a patch line in %prep
    """
    if patch_type != rpmconst.RpmSpecPatchTypes.INC_FILE:
        insert_idx = get_patch_idx_insert(spec_data)
        pvlog.logger.info(
                "Patch directive type: %s",
                patch_type,
        )
        pvlog.logger.info(
                "Insert index: %s",
                insert_idx
        )

        if insert_idx is not None:
            if patch_type != rpmconst.RpmSpecPatchTypes.AUTOSETUP:
                spec_data.insert(
                    insert_idx,
                    generate_patch_line(
                        ''.join(source_name.split('.')[:-1]),
                        new_number,
                        patch_type
                    )
                )
        else:
            if patch_type != rpmconst.RpmSpecPatchTypes.AUTOSETUP:
                insert_idx = get_setup_line(spec_data)
                pvlog.logger.info("Insert index: %s", insert_idx)
                if insert_idx is not None:
                    patch_type = rpmconst.RpmSpecPatchTypes.P_SPACE
                    spec_data.insert(
                        insert_idx,
                        generate_patch_line(
                                ''.join(source_name.split('.')[:-1]),
                                new_number,
                                patch_type
                            )
                        )
                else:
                    raise err.RpmParseError("Unable to find a line where we can apply the patch")
            else:
                pvlog.logger.info("%autosetup package found, skipping patch lines")

        if patch_type is None:
            raise err.RpmParseError("Unknown patch type...")

# pylint: disable=too-many-positional-arguments,too-many-arguments
def add_new_source(
        spec_data: list[str],
        source_name: str,
        directive_type: rpmconst.RpmSpecDirectives,
        package_name: str,
        patch_file: bool,
        source_number: int = -1) -> None:
    """
    Adds the new source file to the RPM spec file
    """
    # turns out it's easier to just reverse the data than play guessing games
    spec_data.reverse()

    # find last directive thing here
    last_number, last_idx, no_numbers = get_last_directive(spec_data,
                                                             directive_type)

    pvlog.logger.info("Getting all source and patch information if needed")
    patch_type = get_patch_type(spec_data, package_name, patch_file)
    new_number = get_new_number(spec_data, no_numbers, directive_type,
                                last_number, source_number)

    spec_data.insert(last_idx, f"{directive_type.value}{new_number}: {source_name}")

    # If there is a patch file, there is a very good chance patches aren't
    # being applied one-by-one in the spec file. We're going to skip adding a
    # patch line.
    #
    # In the future, we will add the ability to modify the patch file. But for
    # now, SNR is recommended.
    if (directive_type == rpmconst.RpmSpecDirectives.PATCH and
        patch_type != rpmconst.RpmSpecPatchTypes.INC_FILE):
        add_patch_line(spec_data, source_name, patch_type, new_number)

    spec_data.reverse()
