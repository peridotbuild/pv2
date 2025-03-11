"""
Generic functions
"""
import os
import sys
import datetime
import hashlib
# I want to at some point look into pathlib
# from pathlib import Path
from urllib.parse import quote as urlquote
import pycurl
from pv2.util import error as err
from pv2.util import fileutil
from pv2.util import log as pvlog

# General utilities
__all__ = [
        'conv_multibyte',
        'convert_from_unix_time',
        'gen_bool_option',
        'generate_password_hash',
        'ordered',
        'to_unicode',
        'trim_non_empty_string',
        'hash_checker',
        'download_file',
        'read_file_to_list',
        'write_file_from_list',
        'line_is_comment'
]

def to_unicode(string: str) -> str:
    """
    Convert to unicode
    """
    if isinstance(string, bytes):
        return string.decode('utf8')
    if isinstance(string, str):
        return string
    return str(string)

def conv_multibyte(data):
    """
    Convert to multibytes
    """
    potential_sum = 0
    num = len(data)
    for i in range(num):
        potential_sum += data[i] << (8 * (num - i - 1))
    return potential_sum

def ordered(data):
    """
    Lazy ordering
    """
    if isinstance(data, int):
        return data
    return ord(data)

def convert_from_unix_time(timestamp: int) -> str:
    """
    Convert UNIX time to a timestamp
    """
    return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%dT%H:%M:%S')

def trim_non_empty_string(key, value) -> str:
    """
    Verify that a given value is a non-empty string
    """
    if not isinstance(value, str) or not value.strip():
        raise err.ProvidedValueError(f'{key} must be a non-empty string')
    return value

def gen_bool_option(value) -> str:
    """
    Helps convert a value to how dnf and other configs interpret a boolean config value.

    This should accept bool, string, or int and will act accordingly.
    """
    return '1' if value and value != '0' else '0'

def generate_password_hash(password: str, salt: str, hashtype: str = 'sha256') -> str:
    """
    Generates a password hash with a given hash type and salt
    """
    if hashtype in ('sha', 'sha1', 'md5'):
        raise err.ProvidedValueError(f'{hashtype} is not allowed.')

    hasher = hashlib.new(hashtype)
    hasher.update((salt + password).encode('utf-8'))
    return str(hasher.hexdigest())

def safe_encoding(data: str) -> str:
    """
    Does url quoting for safe encoding
    """
    quoter = urlquote(data, safe='/+')
    # the urllib library currently doesn't reserve this
    quoter = quoter.replace('~', '%7e')
    return quoter

def hash_checker(data: str) -> str:
    """
    Returns the type of hash the string possibly is
    """
    if len(data) == 128:
        hashtype = 'sha512'
    elif len(data) == 64:
        hashtype = 'sha256'
    elif len(data) == 40:
        hashtype = 'sha1'
    elif len(data) == 32:
        hashtype = 'md5'
    else:
        raise err.GenericError('Data is either invalid or is not a hash.')

    return hashtype

def download_file(url: str, to_path: str, checksum=None, hashtype=None):
    """
    Downloads a file to a specific path
    """
    url = url.encode('utf-8')
    if os.path.exists(to_path):
        if not checksum or not hashtype:
            # pylint: disable=line-too-long
            raise err.DownloadError(f'File {to_path} already exists, but a checksum was not provided to verify it.')

        file_checksum = fileutil.get_checksum(to_path, hashtype=hashtype)
        if file_checksum == checksum:
            pvlog.logger.info('File already downloaded and checksum is valid.')
        else:
            raise err.DownloadError('File exists, but checksum does not match')

    # Assume path doesn't exist, download it.
    pvlog.logger.info('Downloading %s', to_path)
    with open(to_path, 'wb') as dlf:
        # todo: add stdout or logging for this
        # pylint: disable=c-extension-no-member
        curl = pycurl.Curl()
        curl.setopt(pycurl.URL, url)
        curl.setopt(pycurl.HTTPHEADER, ['Pragma:'])
        curl.setopt(pycurl.NOPROGRESS, True)
        curl.setopt(pycurl.OPT_FILETIME, True)
        curl.setopt(pycurl.WRITEDATA, dlf)
        curl.setopt(pycurl.LOW_SPEED_LIMIT, 1000)
        curl.setopt(pycurl.LOW_SPEED_TIME, 300)
        curl.setopt(pycurl.FOLLOWLOCATION, 1)

        try:
            curl.perform()
            timestamp = curl.getinfo(pycurl.INFO_FILETIME)
            status = curl.getinfo(pycurl.RESPONSE_CODE)
        except Exception as exc:
            os.remove(to_path)
            raise err.DownloadError(exc)
        finally:
            curl.close()

        if sys.stdout.isatty():
            sys.stdout.write('\n')
            sys.stdout.flush()

        if status != 200:
            pvlog.logger.info('Removing invalid file %s', to_path)
            os.remove(to_path)
            raise err.DownloadError(f'There was an error downloading: {status}')

    os.utime(to_path, (timestamp, timestamp))
    # verify checksum
    if not checksum or not hashtype:
        # pylint: disable=line-too-long
        pvlog.logger.warning('checksum and hashtype were not set, skipping verification')
        return

    file_checksum = fileutil.get_checksum(to_path, hashtype=hashtype)
    if file_checksum != checksum:
        os.remove(to_path)
        raise err.DownloadError('Checksums do not match for downloaded file')

def read_file_to_list(file_path: str) -> list[str]:
    """
    Reads a file into a list
    """
    with open(file_path, "r") as file_to_read:
        file_data = [line.rstrip("\n") for line in file_to_read.readlines()]
        file_to_read.close()

    if file_data is None or not file_data:
        raise err.FileNotFound("File is empty, doesn't exist, or is not valid")

    return file_data

def write_file_from_list(file_path: str, data: list[str]):
    """
    Takes a list of strings and writes them to a file
    """
    with open(file_path, "w+") as file_data:
        file_data.writelines(f"{line}\n" for line in data)

def line_is_comment(line: str) -> bool:
    """
    Determines if this line is a comment

    Potentially move this to generic
    """
    return line.startswith("#")


