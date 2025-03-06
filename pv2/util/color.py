# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
# borrowed from empanadas
"""
Color classes
"""
# RPM utilities
__all__ = [
        'Color',
]

# pylint: disable=too-few-public-methods
class Color:
    """
    Supported colors
    """
    RED = "\033[91m"
    GREEN = "\033[92m"
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    DARKCYAN = "\033[36m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    UNDERLINE = "\033[4m"
    BOLD = "\033[1m"
    END = "\033[0m"
    INFO = "[" + BOLD + GREEN + "INFO" + END + "] "
    WARN = "[" + BOLD + YELLOW + "WARN" + END + "] "
    FAIL = "[" + BOLD + RED + "FAIL" + END + "] "
    STAT = "[" + BOLD + CYAN + "STAT" + END + "] "
