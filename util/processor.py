# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@rockylinux.org>
"""
Provides subprocess utilities
"""

import os
import sys
import subprocess
from pv2.util import error as err

# todo: remove python 3.6 checks. nodes won't be on el8.

def run_proc_foreground(command: list):
    """
    Takes in the command in the form of a list and runs it via subprocess.
    Everything should be in the foreground. The return is just for the exit
    code.
    """
    try:
        processor = subprocess.run(args=command, check=False)
    except Exception as exc:
        raise err.GenericError(f'There was an error with your command: {exc}')

    return processor

def run_proc_no_output(command: list):
    """
    Output will be stored in stdout and stderr as needed.
    """
    try:
        if sys.version_info <= (3, 6):
            processor = subprocess.run(args=command, check=False,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       universal_newlines=True)
        else:
            processor = subprocess.run(args=command, check=False, capture_output=True,
                                       text=True)
    except Exception as exc:
        raise err.GenericError(f'There was an error with your command: {exc}')

    return processor

def popen_proc_no_output(command: list):
    """
    This opens a process, but is non-blocking.
    """
    try:
        if sys.version_info <= (3, 6):
            processor = subprocess.Popen(args=command, stdout=subprocess.PIPE,
                                         universal_newlines=True)
        else:
            # pylint: disable=consider-using-with
            processor = subprocess.Popen(args=command, stdout=subprocess.PIPE,
                                         text=True)
    except Exception as exc:
        raise err.GenericError(f'There was an error with your command: {exc}')

    return processor

def run_check_call(command: list) -> int:
    """
    Runs subprocess check_call and returns an integer.
    """
    env = os.environ
    try:
        subprocess.check_call(command, env=env)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f'Run failed: {exc}\n')
        return 1
    return 0
