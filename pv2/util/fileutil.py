"""
File functions
"""

import os
import hashlib
import magic
from pv2.util import error as err

# File utilities
__all__ = [
        'filter_files',
        'filter_files_inverse',
        'get_checksum',
        'get_magic_file',
        'get_magic_content'
]

def filter_files(directory_path: str, filter_filename: str) -> list:
    """
    Filter out specified files
    """
    return_list = []
    for file in os.scandir(directory_path):
        if filter_filename(file.name):
            return_list.append(os.path.join(directory_path, file.name))

    return return_list

def filter_files_inverse(directory_path: str, filter_filename: str) -> list:
    """
    Filter out specified files (inverse)
    """
    return_list = []
    for file in os.scandir(directory_path):
        if not filter_filename(file.name):
            return_list.append(os.path.join(directory_path, file.name))

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
