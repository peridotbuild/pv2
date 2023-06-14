"""
Generic functions
"""
import datetime
import hashlib
from pv2.util import error as err

# General utilities
__all__ = [
        'ordered',
        'conv_multibyte',
        'to_unicode',
        'convert_from_unix_time',
        'trim_non_empty_string',
        'gen_bool_option',
        'generate_password_hash'
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
