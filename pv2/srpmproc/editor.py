# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Editor utilities
"""

from typing import List, Dict, Any
from pathlib import Path
import re
import shutil
import datetime
import textwrap
import yaml
from pv2.util import error as err
from pv2.util import log as pvlog
from pv2.util import fileutil, generic, gitutil, rpmutil, processor
from pv2.util.constants import RpmConstants as rpmconst
import pv2.srpmproc.util as srpmutil

# pylint: disable=line-too-long,unspecified-encoding
# pylint: disable=too-many-positional-arguments

class Action:
    """
    Actions and actions only
    """
    required_keys: List[str] = []
    allowed_keys: Dict[str, type] = {}

    def __init__(self, data: Dict[str, Any], config):
        """
        Initialize the actions
        """
        self.data = data
        self.config_path = config
        self.validate()

    def __repr__(self):
        """
        Present the data a specific way
        """
        attributes = []
        for key in self.allowed_keys:
            if hasattr(self, key):
                attributes.append(f"{key}={getattr(self, key)}")
        return f"{self.__class__.__name__}(', '.join(attributes))"

    def validate(self):
        """
        Validate required and allowed keys
        """
        keys = set(self.data.keys())

        # Check required keys
        missing = set(self.required_keys) - keys
        if missing:
            raise err.PatchConfigValueError("Missing keys", ', '.join(missing))

        # Check for unexpected keys
        unexpected = keys - set(self.allowed_keys.keys())
        if unexpected:
            raise err.PatchConfigValueError(
                    f"Unexpected keys: {', '.join(missing)}. Expected: {', '.join(self.allowed_keys.keys())}"
            )

        # Check value types and empty values
        for key, expected_type in self.allowed_keys.items():
            if key in self.data:
                if not isinstance(self.data[key], expected_type):
                    raise err.PatchConfigTypeError(
                            f"Invalid type for {key}: Expected {expected_type.__name__}, got {type(self.data[key]).__name__}"
                    )
                if self.data[key] in [None, "", [], {}]:
                    raise err.PatchConfigValueError(
                            f"Invalid data for {key}: Value cannot be empty.")

    def execute(self, package_path: Path):
        """
        This class does not execute anything.
        """
        raise NotImplementedError("Only subclasses and perform executions")

    @staticmethod
    def find_file_name(package: Path, name: str):
        """
        Finds a specific file's name
        """
        file_list = fileutil.filter_files(package, name)
        final_list = []

        for file in file_list:
            fobj = Path(file)
            index = fobj.parts.index(fobj.name)
            # "PATCH" is an srpmproc-ism that we are not currently carrying
            # over.
            if len(fobj.parts) > index + 1 and (fobj.parts[index + 1] == "PATCH"):
                continue
            final_list.append(fobj)

        if len(final_list) > 1:
            raise err.TooManyFilesError(
                    f"File: Too many files of that name ({name}) found in {package}")

        if not final_list:
            raise err.FileNotFound(f"File ({name}) was not found in {package}")

        return final_list[0]

    @staticmethod
    def __skip_line(target: str, line: str, find_lines: list[str]) -> bool:
        """
        Check if this line can be skipped safely
        """
        if target == "specfile":
            if rpmutil.spec_line_changelog(line):
                return True
            if generic.line_is_comment(line) and not generic.line_is_comment(find_lines[0]):
                return True
        return False

    @staticmethod
    def __find_indent(line: str) -> str:
        """
        Get the indent of a line
        """
        return line[:len(line) - len(line.lstrip())]

    @staticmethod
    def __apply_indent(lines: list[str], starting: str) -> list[str]:
        """
        Applies the found indentation
        """
        if not lines:
            return lines

        indent_lines = [lines[0]]
        for line in lines[1:]:
            if line.strip():
                indent_lines.append(starting + line)
            else:
                indent_lines.append(line)

        return indent_lines

    @staticmethod
    def __process_single_line(file, i, current_line, find,
                              replace_lines, counter, count):
        """
        Process a single line
        """
        changed = False
        count_in_line = current_line.count(find)
        to_replace_lines = None
        if count_in_line > 0:
            if count != -1 and counter >= count:
                return changed, counter

            if not replace_lines:
                if current_line.strip() == find:
                    file.pop(i)
                    changed = True
                    pvlog.logger.info("Deleted line: '%s' on line %s", find, i + 1)
                    return True, counter

            else:
                if file[i] == find:
                    to_replace_lines = replace_lines
                else:
                    indent = Action.__find_indent(file[i])
                    to_replace_lines = Action.__apply_indent(replace_lines, indent)

            file[i] = current_line.replace(find, "\n".join(to_replace_lines) if to_replace_lines else "", 1)
            pvlog.logger.info("Replaced line(s): '%s' on line %s", to_replace_lines, i + 1)
            counter += 1
            changed = True

        return changed, counter

    @staticmethod
    def __process_single_line_regex(file, i, current_line, pattern,
                                    replace_lines, counter, count):
        """
        Processes a single line that contains regex
        """
        changed = False
        regexstr = re.compile(pattern)
        matches = list(regexstr.finditer(current_line))
        if matches:
            replacer = "\n".join(replace_lines) if replace_lines else ""
            curcount = 1 if count != -1 else 0
            file[i] = regexstr.sub(replacer, current_line, curcount)
            pvlog.logger.info("Replaced regex match: '%s' with '%s'", pattern, replace_lines)
            changed = True

        return changed, counter

    @staticmethod
    def __process_multi_line(file, i, find_lines, replace_lines,
                             counter, count):
        """
        Processes multiline find and replace
        """
        changed = False
        stripped_block = [line.lstrip() for line in file[i:i + len(find_lines)]]
        stripped_find_lines = [line.lstrip() for line in find_lines]

        if stripped_block == stripped_find_lines:
            if count != -1 and counter >= count:
                return changed, counter

            if not replace_lines:
                del file[i:i + len(find_lines)]
                pvlog.logger.info("Deleted block of lines: %s-%s", i + 1, i + len(find_lines))
            else:
                indent = Action.__find_indent(file[i])
                formatted_repl_lines = [indent + line for line in replace_lines]
                file[i:i + len(find_lines)] = formatted_repl_lines
                pvlog.logger.info(
                        "Replaced lines: %s-%s with %s",
                        i + 1,
                        i + len(find_lines),
                        replace_lines)

            counter += 1
            changed = True
            i += len(replace_lines) - 1

        return changed, counter

    @staticmethod
    def __finalize_changes(path: Path, file: list[str], changes: bool,
                           replace_lines: list[str], find_lines: list[str]):
        """
        Finalizes all changes from processor
        """
        if not changes:
            action = "DeleteLine" if not replace_lines else "SearchAndReplace"
            raise err.NotAppliedError(
                    f"{action}: No changes were made for {find_lines} in {path.name}"
            )

        generic.write_file_from_list(path, file)

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def data_processor(
        self,
        path: Path,
        target: str,
        find_lines: list[str],
        replace_lines: list[str],
        count: int,
        regex: bool = False
    ):
        """
        Process lines for specific actions
        """
        counter = 0
        i = 0
        file = generic.read_file_to_list(path)
        changes = False

        while i < len(file):
            current_line = file[i]

            if self.__skip_line(target, current_line, find_lines):
                i += 1
                continue

            if len(find_lines) == 1:
                if regex:
                    changed, counter = self.__process_single_line_regex(
                            file, i, current_line, find_lines[0],
                            replace_lines, counter, count)
                else:
                    changed, counter = self.__process_single_line(
                            file, i, current_line, find_lines[0],
                            replace_lines, counter, count)

            else:
                changed, counter = self.__process_multi_line(
                        file, i, find_lines, replace_lines, counter, count)
            i += 1

            if changed:
                changes = True

        self.__finalize_changes(path, file, changes, replace_lines, find_lines)

class SearchAndReplace(Action):
    """
    Performs a simple search and replace
    """
    required_keys = ["target", "find", "replace"]
    allowed_keys = {"target": str, "find": str, "regex": bool, "replace": str, "count": int}

    def execute(self, package_path: Path):
        """
        The executed action
        """
        find = self.data['find']
        replace = self.data['replace']
        target = self.data['target']
        count = self.data.get('count', -1)
        regex = self.data.get('regex', False)
        file_name = target

        if 'specfile' in target:
            file_name = "*.spec"

        file_path = self.find_file_name(package_path, file_name)

        lines = find.splitlines() if "\n" in find else [find]
        repl_lines = replace.splitlines() if "\n" in replace else [replace]

        pvlog.logger.info("Replacing '%s' with '%s' in '%s'",
                          find,
                          replace,
                          target)

        self.data_processor(
                file_path,
                target,
                lines,
                repl_lines,
                count,
                regex
        )

class DeleteLine(Action):
    """
    Deletes a line from a target file
    """
    required_keys = ["target", "lines"]
    allowed_keys = {"target": str, "lines": list}

    def execute(self, package_path: Path):
        """
        The executed action
        """
        target = self.data['target']
        lines = self.data['lines']
        file_name = self.data['target']
        if 'specfile' in target:
            file_name = "*.spec"
        file_path = self.find_file_name(package_path, file_name)
        for line in lines:
            pvlog.logger.info("Deleting line: %s", line)
            find_lines = line.splitlines() if "\n" in line else [line]

            self.data_processor(
                    file_path,
                    target,
                    find_lines,
                    "",
                    -1
            )

class AppendRelease(Action):
    """
    Appends the release tag of a spec file
    """
    required_keys = ["suffix", "enabled"]
    allowed_keys = {"suffix": str, "enabled": bool}

    def execute(self, package_path: Path):
        """
        The executed action
        """
        modified = False
        if not self.data['enabled']:
            pvlog.logger.info("Release modification disabled")
            return

        file_path = self.find_file_name(package_path, "*.spec")
        file = generic.read_file_to_list(file_path)
        autorelease = rpmutil.spec_autorelease(file)
        pvlog.logger.info("Modifying release line")

        if autorelease:
            pvlog.logger.warning("%autorelease found, modification may be incomplete")
            #return

        for i, line in enumerate(file):
            if autorelease:
                if rpmconst.RPM_AUTORELEASE_FINAL_LINE in line:
                    file[i] += self.data['suffix']
                    modified = True
                    break
            else:
                if rpmutil.spec_line_release(line):
                    file[i] += self.data['suffix']
                    modified = True

        if not modified:
            msg = "Release: We were not able to modify the autorelease." if autorelease \
                    else "Release: There were no release lines found."
            raise err.NotAppliedError(msg)

        generic.write_file_from_list(file_path, file)

class SpecChangelog(Action):
    """
    Adds a changelog entry to a spec file
    """
    required_keys = ["name", "email", "line"]
    allowed_keys = {"name": str, "email": str, "line": list}

    # pylint: disable=too-many-locals
    def execute(self, package_path: Path):
        """
        The executed action
        """
        name = self.data['name']
        email = self.data['email']
        line = self.data['line']
        changelog_info_lines = []
        file_path = self.find_file_name(package_path, "*.spec")
        file = generic.read_file_to_list(file_path)

        if rpmutil.spec_autochangelog(file):
            pvlog.logger.warning("Spec file has %autochangelog, skipping")
            return

        parsed = rpmutil.spec_parse(file_path)
        epoch, version, release = rpmutil.spec_evr(parsed)

        pvlog.logger.info("Adding changelog entry by %s (%s): %s", name, email, line)

        current_date = datetime.datetime.today().strftime("%a %b %d %Y")
        for c, l in enumerate(file):
            if l == "%changelog":
                full_version = f"{version}-{release}"
                if epoch is not None:
                    full_version = f"{epoch}:{full_version}"
                change_meta = f"* {current_date} {name} <{email}> - {full_version}"
                file.insert(c + 1, f"{change_meta}")
                for change_entry in line:
                    changelog_info_lines.extend(
                            textwrap.wrap(
                                change_entry, 80,
                                initial_indent="- ",
                                subsequent_indent="  "
                            )
                    )
                file.insert(c + 2, "\n".join(changelog_info_lines) + "\n")
        generic.write_file_from_list(file_path, file)

class AddFile(Action):
    """
    Adds a file to the package, including source to spec file
    """
    required_keys = ["type", "name", "number"]
    allowed_keys = {
            "type": str,
            "name": str,
            "source_name": str,
            "number": str,
            "add_to_spec": bool,
            "upload": bool
    }
    valid_types = {"patch", "source"}

    def validate(self):
        """
        Ensure that "type" is one of patch or source
        """
        super().validate()

        if self.data["type"] not in self.valid_types:
            raise err.PatchConfigTypeError(
                    "Invalid config: Must be one of {self.valid_types}"
            )

    def __copy_file(self, package_path: Path, file_to_copy: str, source_override: str = None):
        """
        Copies the specified file from the patch repo into the package repo.
        """
        # Making sure source_override is treated as unset is empty
        source_filename = (source_override or "").strip() or file_to_copy
        files_dir = self.config_path.parent / "files"

        source = files_dir / source_filename
        target = Path(package_path) / "SOURCES" / file_to_copy

        target.parent.mkdir(parents=True, exist_ok=True)

        # Run checks against the source
        fileutil.file_is_relative(source, files_dir)

        if not source.exists():
            raise err.NotAppliedError(f"Source does not exist: The file {source}")

        if not source.is_file():
            raise err.NotAppliedError(f"Source is not a file: {source}")

        if target.exists():
            raise err.NotAppliedError(f"Target Exists: The file {file_to_copy} already exists")

        pvlog.logger.info("Copying %s to %s", source, target)
        shutil.copy2(source, target)

    def execute(self, package_path: Path):
        """
        The executed action
        """
        name = self.data['name']
        source_override = self.data.get("source_name") or None
        filetype = self.data['type']
        number = self.data['number'] if self.data['number'] != "latest" else -1

        # If no value is set, the answer is ALWAYS true.
        add_to_spec = self.data.get('add_to_spec', True)

        # If no value is set, the answer is ALWAYS false.
        upload_to_lookaside = self.data.get('upload', False)

        package_name = package_path.name
        patches_file = any(Path(package_path).rglob("*.patches"))
        directive_type = None

        spec_file_path = self.find_file_name(package_path, "*.spec")
        spec_data = generic.read_file_to_list(spec_file_path)

        if filetype == "patch":
            directive_type = rpmconst.RpmSpecDirectives.PATCH
        elif filetype == "source":
            directive_type = rpmconst.RpmSpecDirectives.SOURCE

        pvlog.logger.info("Adding file to package: %s", name)
        if add_to_spec:
            srpmutil.add_new_source(
                    spec_data,
                    name,
                    directive_type,
                    package_name,
                    patches_file,
                    number
            )

        if patches_file:
            patch_file_path = self.find_file_name(package_path, "*.patches")
            patch_file_data = generic.read_file_to_list(patch_file_path)
            srpmutil.add_new_source_patch_file(
                    patch_file_data,
                    name,
                    directive_type,
                    number
            )
            generic.write_file_from_list(patch_file_path, patch_file_data)

        # we can determine if we're uploading to a lookaside here
        if upload_to_lookaside and filetype == "source":
            srpmutil.upload_to_lookaside(name)
            # modify the metadata here...
        else:
            self.__copy_file(package_path, name, source_override)

        generic.write_file_from_list(spec_file_path, spec_data)

class DeleteFile(Action):
    """
    Deletes a file from the package
    """
    required_keys = ["filename"]
    allowed_keys = {"filename": str}

    def __delete_from_metadata(self, filename: str, metadata: list[str]):
        """
        Deletes from the metadata file provided
        """
        for i, line in enumerate(metadata):
            if re.match(rf'[0-9a-f]+\s+{filename}', line):
                del metadata[i]
                break

            raise err.NotAppliedError(f'Delete File: {filename} not found in metadata')

    def execute(self, package_path: Path):
        """
        The executed action
        """
        filename = Path(package_path) / self.data['filename']
        metadata_file = package_path / f'.{package_path.name}.metadata'

        if not metadata_file.exists():
            raise err.FileNotFound('metadata file not found')

        pvlog.logger.info("Reading in metadata file")
        metadata_file_data = generic.read_file_to_list(metadata_file)

        pvlog.logger.info("Deleting file from package: %s", filename.name)
        try:
            if filename.exists():
                filename.unlink()
                pvlog.logger.info("%s deleted", filename.name)
        except FileNotFoundError:
            self.__delete_from_metadata(filename.name, metadata_file_data)
            pvlog.logger.info("%s deleted from metadata", filename.name)

        generic.write_file_from_list(metadata_file, metadata_file_data)

class ReplaceFile(Action):
    """
    Replaces a file in the package with another
    """
    required_keys = ["filename"]
    allowed_keys = {
            "filename": str,
            "source_filename": str,
            "upload_to_lookaside": bool
    }

    def __copy_file(self, package_path: Path, file_to_copy: str, source_override: str = None):
        """
        Copies the specified file from the patch repo into the package repo.
        """
        # Making sure source_override is treated as unset is empty
        source_filename = (source_override or "").strip() or file_to_copy
        files_dir = self.config_path.parent / "files"

        source = files_dir / source_filename
        target = Path(package_path) / "SOURCES" / file_to_copy

        target.parent.mkdir(parents=True, exist_ok=True)

        # Run checks against the source
        fileutil.file_is_relative(source, files_dir)

        if not source.exists():
            raise err.NotAppliedError(f"Source does not exist: The file {source}")

        if not source.is_file():
            raise err.NotAppliedError(f"Source is not a file: {source}")

        if not target.exists():
            raise err.NotAppliedError(f"Target Does Not Exist: The file {file_to_copy} isn't there.")

        pvlog.logger.info("Replacing %s with %s", target, source)
        shutil.copy2(source, target)

    def execute(self, package_path: Path):
        """
        The executed action
        """
        filename = self.data['filename']
        source_override = self.data.get("source_filename") or None

        # If no value is set, the answer is ALWAYS false.
        upload_to_lookaside = self.data.get('upload', False)

        pvlog.logger.info("Replacing file in package: %s", filename)

        if upload_to_lookaside:
            srpmutil.upload_to_lookaside(filename)
            # modify the metadata here...
        else:
            self.__copy_file(package_path, filename, source_override)

class ApplyScript(Action):
    """
    Runs an arbitrary script

    Script must be in a "scripts" directory
    """
    required_keys = ["script"]
    allowed_keys = {"script": str}

    def execute(self, package_path: Path):
        """
        The executed action
        """
        scr = (self.config_path.parent / "scripts") / self.data['script']

        if not scr.exists():
            raise err.FileNotFound(f'{scr} was not found')

        pvlog.logger.info("Running script %s", scr)
        command = f"/bin/bash {scr}"
        ret = processor.run_proc_foreground_shell(command)
        if ret.returncode != 0:
            screrr = ret.stderr
            raise err.NotAppliedError("Script failed: {screrr.strip()}")

class ApplyPatch(Action):
    """
    Applies a specific patch file
    """
    required_keys = ["filename"]
    allowed_keys = {"filename": str}

    def execute(self, package_path: Path):
        """
        Apply arbitrary patch files
        """
        patch = (self.config_path.parent / "files") / self.data['filename']

        if not patch.exists():
            raise err.FileNotFound(f'{patch} was not found')

        pvlog.logger.info("Applying patch file %s", patch)
        repo = gitutil.obj(package_path)
        gitutil.apply(repo, patch)

class ActionQueue:
    """
    Collects and executes actions
    """
    def __init__(self):
        self.queue: List[Action] = []

    def add_action(self, action: Action):
        """
        Adds an action to the queue
        """
        self.queue.append(action)

    def execute_all(self, package_path: Path):
        """
        Loops throw actions and executes them
        """
        spec_changelog_actions = []
        everything_else = []

        for action in self.queue:
            if isinstance(action, SpecChangelog):
                spec_changelog_actions.append(action)
            else:
                everything_else.append(action)

        for action in everything_else:
            action.execute(package_path)

        for action in reversed(spec_changelog_actions):
            action.execute(package_path)

class Config:
    """
    Read and assess configuration
    """
    ACTIONS = {
            "append_release": AppendRelease,
            "apply_patch": ApplyPatch,    # Patches via a patch file
            "apply_script": ApplyScript,  # Runs an arbitrary script
            "add_file": AddFile,          # Adds an arbitrary file
            "delete_file": DeleteFile,    # Deletes an arbitrary file
            "delete_line": DeleteLine,    # Deletes an arbitrary line in a given file
            "replace_file": ReplaceFile,  # Replaces an arbitrary file
            "search_and_replace": SearchAndReplace,    # Performs search and replace on a given file
            "spec_changelog": SpecChangelog,  # Adds changelog entries
    }

    def __init__(self, config):
        """
        Initialize config portion
        """
        # We want to potentially accept a str, bytes, or Path object.
        if isinstance(config, (str, bytes, Path)):
            self.config = Path(config)
        else:
            raise err.PatchConfigTypeError(
                    "Invalid config: Provided config is not a str, bytes, or Path object."
            )

        self.spec_modified = False
        self.loaded_config = None
        self.queue = ActionQueue()
        self.__process_config()

    def __process_config(self):
        """
        Process YAML configuration for actions
        """
        pvlog.logger.info("Loading configuration")
        if isinstance(self.config, Path):
            with open(self.config, "r") as y:
                self.loaded_config = yaml.safe_load(y)
                y.close()
        elif hasattr(self.config, "read"):
            self.loaded_config = yaml.safe_load(self.config)
        else:
            raise err.PatchConfigTypeError("Invalid config", "Not a file or file-like object")

        pvlog.logger.info("Configuration successfully loaded")
        pvlog.logger.info("Validating configuration")

        self.__validate_config()

        pvlog.logger.info("Attempting to add patch actions to the queue")
        for patch_dict in self.loaded_config.get("patch", []):
            for patch_action_name, patch_action_list in patch_dict.items():
                patch_action = self.ACTIONS.get(patch_action_name)
                for patch_data in patch_action_list:
                    action = patch_action(patch_data, self.config)
                    self.queue.add_action(action)

    def __validate_config(self):
        """
        Validates the config has supported actions
        """
        pvlog.logger.info("Checking for top-level patch directive")
        if not self.loaded_config or "patch" not in self.loaded_config:
            raise err.PatchConfigValueError(
                    "Invalid config: Missing patch configuration or configuration is empty"
            )

        pvlog.logger.info("Checking for valid 'patch' data set")
        patch_data = self.loaded_config.get("patch")
        if patch_data is None:
            raise err.PatchConfigValueError(
                    "Invalid config: Actions section cannot be 'None'"
            )
        if not isinstance(patch_data, list):
            raise err.PatchConfigTypeError(
                    "Invalid config: Patch data is not a list of dicts"
            )

        pvlog.logger.info("Checking that all actions are valid")
        for patch_dict in self.loaded_config.get("patch", []):
            for patch_action_name, patch_action_list in patch_dict.items():
                patch_action = self.ACTIONS.get(patch_action_name)
                if not patch_action:
                    raise err.PatchConfigValueError(
                            f"Unknown Action: {patch_action_name} is not a valid action."
                    )
                if not isinstance(patch_action_list, list):
                    raise err.PatchConfigTypeError(
                            f"Wrong format: {patch_action_name} is not a list."
                    )

    def run(self, package_path: Path):
        """
        Run all actions
        """
        pvlog.logger.info("Attempting to patch package")
        self.queue.execute_all(package_path)

    @property
    def config_data(self):
        """
        Display imported config
        """
        return self.loaded_config

    @property
    def modified_spec(self):
        """
        Display spec modification status
        """
        return self.spec_modified
