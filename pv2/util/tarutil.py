"""
Tar functions
"""

import tarfile
from pv2.util import error as err
from pv2.util import fileutil

# Tar utilities
__all__ = [
        'tar_members',
        'type_of_tar',
        'tarextract'
]

def tar_members(tf, subdir):
    """
    Acts as a "strip component" for tar
    """
    l = len(f"{subdir}/")
    for member in tf.getmembers():
        if member.path.startswith(f"{subdir}/"):
            member.path = member.path[l:]
            yield member

def type_of_tar(tf):
    """
    Determines what compression method was used.
    """
    tardata = fileutil.get_magic_file(tf)

    if 'XZ compressed data' in tardata.name:
        return 'xz'
    if 'gzip compressed data' in tardata.name:
        return 'gz'
    if 'bzip2 compressed data' in tardata.name:
        return 'bz2'

    return None

def tarextract(source, dest, topdir_to_strip='', strip=False):
    """
    Extracts a given tar ball to a specific location
    """
    try:
        with tarfile.open(source) as tar:
            if strip:
                tar.extractall(members=tar_members(tar, topdir_to_strip), filter='tar', path=dest)
            else:
                tar.extractall(filter='tar', path=dest)
            tar.close()
    except tarfile.ReadError as re:
        raise err.GenericError(f'Could not read tar file: {re}')
    except tarfile.CompressionError as ce:
        raise err.GenericError(f'This system does not support compression type used: {ce}')
    except tarfile.ExtractError as ee:
        raise err.GenericError(f'Extraction error: {ee}')
    except Exception as exc:
        raise err.GenericError(f'Uncaught error: {exc}')
