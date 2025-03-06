# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Mock Error Classes (mainly for parsing, if we care)
"""

import os
import re
from pv2.util import constants as const
from pv2.util import generic as generic_util

# list every error class that's enabled

__all__ = [
        'MockErrorParser'
]

class MockErrorChecks:
    """
    Static methods of all error checks
    """
    @staticmethod
    def analyze_log(checks, log_file):
        """
        Go through the list of checks and verify the log file

        All checks are listed throughout the class below this one.
        """
        log_file_name = os.path.basename(log_file)
        result_dict = {}
        with open(log_file_name, 'rb') as file_descriptor:
            for line_number, line in enumerate(file_descriptor, 1):
                for check in checks:
                    result = check(line)
                    if result:
                        error_code, error_message = result
                        result_dict = {
                                'error_code': error_code,
                                'error_message': error_message,
                                'file_name': log_file_name,
                                'line': line_number
                        }

                    return result_dict

    @staticmethod
    def check_error(regex, message, error_code, line):
        """
        Does the actual regex verification
        """
        result = re.search(regex, generic_util.to_unicode(line))
        if result:
            return error_code, message.format(*result.groups())

        return None

    @staticmethod
    def unmet_dep(line):
        """
        Searches for a dependency error in the root log
        """
        regex = r'Error:\s+No\s+Package\s+found\s+for\s+(.*?)$'
        message_template = 'No package(s) found for "{0}"'
        verify_pattern = __class__.check_error(regex,
                                     message_template,
                                     const.MockConstants.MOCK_EXIT_DNF_ERROR,
                                     line)

        return verify_pattern

class MockErrorParser(MockErrorChecks):
    """
    Helps provide checking definitions to find errors and report them. This
    could be used in the case of having a generic error (like 1) from mock and
    needing to find the real reason.
    """
    def __init__(
            self,
            root_log,
            build_log
    ):
        """
        Initialize parser
        """
        self._root_log = root_log
        self._build_log = build_log

    def check_for_error(self):
        """
        Checks for errors
        """
        # we'll get this eventually
        #build_log_check = []

        root_log_check = [
                self.unmet_dep
        ]

        # pylint: disable=line-too-long
        return self.analyze_log(root_log_check, self._root_log)
