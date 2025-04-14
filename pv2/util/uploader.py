# -*- mode:python; coding:utf-8; -*-
# Louis Abel <label@resf.org>
"""
Utility functions for uploading artifacts
"""
import os
import sys
import threading
import pv2.util.error as err
try:
    import boto3
    s3 = boto3.client('s3')
except ImportError:
    s3 = None

__all__ = [
        'S3ProgressPercentage',
        'upload_to_s3',
        'upload_to_local'
]

class S3ProgressPercentage:
    """
    Displays progress of uploads. Loosely borrowed from the aws documentation.
    """
    def __init__(self, filename):
        self.__filename = filename
        self.__size = float(os.path.getsize(filename))
        self.__seen = 0
        self.__lock = threading.Lock()

    def __call__(self, num_of_bytes):
        with self.__lock:
            self.__seen += num_of_bytes
            percentage = (self.__seen / self.__size) * 100
            sys.stdout.write(
                    "\r%s %s / %s (%.2f%%)" % (self.__filename,
                                               self.__seen,
                                               self.__size,
                                               percentage)
            )
            sys.stdout.flush()

def upload_to_s3(
        input_file,
        bucket,
        access_key_id = None,
        access_key = None,
        dest_name = None,
        overwrite = False
    ):
    """
    Uploads an artifact to s3.
    """
    if dest_name is None:
        dest_name = os.path.basename(input_file)

    if s3 is None:
        raise err.UploadError('s3 module is not available')

    s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key_id,
            aws_secret_access_key=access_key
    )

    with open(input_file, 'rb') as inner:
        s3_client.upload_fileobj(
                inner,
                bucket,
                dest_name,
                Callback=S3ProgressPercentage(input_file)
        )
        inner.close()

    # Hacky way to get a new line
    sys.stdout.write('\n')

def upload_to_local(
        input_file,
        upload_path,
        overwrite = False
    ):
    """
    local 'upload'
    """
