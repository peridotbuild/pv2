"""
File functions
"""

import os
import hashlib
from pv2.util import error as err

# File utilities
__all__ = [
        'filter_files',
        'get_checksum'
]

def filter_files(directory_path: str, filter_filename: str) -> list:
    """
    Filter out specified files
    """
    # it's literally 101/100 ...
    # pylint: disable=line-too-long
    return_list = []
    for file in os.listdir(directory_path):
        if filter_filename(file):
            return_list.append(os.path.join(directory_path, file))

    return return_list

def get_checksum(file_path: str, hashtype: str = 'sha256') -> str:
    """
    Generates a checksum from the provided path by doing things in chunks. This
    reduces the time needed to make the hashes and avoids memory issues.

    Borrowed from empanadas with some modifications
    """
    # We shouldn't be using sha1 or md5.
    if hashtype in ('sha', 'sha1', 'md5'):
        raise err.ProvidedValueError(f'{hashtype} is not allowed.')

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
