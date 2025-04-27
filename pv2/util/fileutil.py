"""
File functions
"""

import os
import hashlib
from pathlib import Path
import magic
from pv2.util import error as err

# File utilities
__all__ = [
        'filter_files',
        'filter_files_inverse',
        'get_checksum',
        'get_magic_file',
        'get_magic_content',
        'mkdir',
        'file_exists_local'
]

def filter_files(directory_path,
                 filter_filename: str,
                 recursive: bool = True) -> list:
    """
    Filter out specified files

    Accepts either a str path or path object
    """
    if isinstance(directory_path, (str, bytes, Path)):
        directory = Path(directory_path)
    else:
        directory = directory_path

    if recursive:
        return_list = [str(file) for file in directory.rglob(filter_filename)]
    else:
        return_list = [str(file) for file in directory.glob(filter_filename)]
    return return_list

def filter_files_inverse(directory_path: str, filter_filename: str) -> list:
    """
    Filter out specified files (inverse)

    Accepts either a str path or path object
    """
    if isinstance(directory_path, (str, bytes, Path)):
        directory = Path(directory_path)
    else:
        directory = directory_path
    return_list = []
    # This is a carry over from previous os module use.
    # I don't think there's a way to inverse rglob.
    for file in directory.iterdir():
        if not filter_filename(file.name):
            return_list.append(str(file))

    return return_list

def get_checksum(file_path: str, hashtype: str = 'sha256') -> str:
    """
    Generates a checksum from the provided path by doing things in chunks. This
    reduces the time needed to make the hashes and avoids memory issues.

    Borrowed from empanadas with some modifications
    """
    # We shouldn't be using sha1 or md5.
    #if hashtype in ('sha', 'sha1', 'md5'):
    #    raise err.ProvidedValueError(f'{hashtype} is not allowed.')

    try:
        checksum = hashlib.new(hashtype)
    except ValueError as exc:
        raise err.GenericError(f'hash type not available: {ValueError}') from exc

    try:
        with open(file_path, 'rb') as input_file:
            while True:
                chunk = input_file.read(8192)
                if not chunk:
                    break
                checksum.update(chunk)

            input_file.close()
        return checksum.hexdigest()
    except IOError as exc:
        raise err.GenericError(f'Could not open or process file {file_path}: {exc})')

def get_magic_file(file_path: str):
    """
    Returns the magic data from a file. Use this to get mimetype and other info
    you'd get by just running `file`
    """
    detect = magic.detect_from_filename(file_path)
    return detect

def get_magic_content(data):
    """
    Returns the magic data from content. Use this to get mimetype and other info
    you'd get by just running `file` on a file (but only pass read file data)
    """
    detect = magic.detect_from_content(data)
    return detect

def mkdir(file_path: str):
    """
    Creates a new directory
    """
    try:
        os.mkdir(file_path)
    except FileExistsError as exc:
        raise err.GenericError('Path already exists') from exc
    except Exception as exc:
        raise err.GenericError(f'There was another error: {exc}') from exc

def file_exists_local(file_path) -> bool:
    """
    Checks if a file exists
    """
    confirmed_path = file_path
    if not isinstance(file_path, Path):
        confirmed_path = Path(file_path)

    return confirmed_path.exists()
