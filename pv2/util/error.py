# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@rockylinux.org>
"""
Generic Error Classes
"""

# needed imports
from pv2.util.constants import ErrorConstants as errconst

# list every error class that's enabled

__all__ = [
        'GenericError',
        'ProvidedValueError',
        'ExistsValueError',
        'MissingValueError',
        'ConfigurationError',
        'FileNotFound',
        'DownloadError',
        'MockGenericError',
        'MockUnexpectedError',
        'MockInvalidConfError',
        'MockInvalidArchError',
        'MockDnfError',
        'MockResultdirError',
        'MockSignalReceivedError',
        'GitCommitError',
        'GitPushError',
        'GitInitError',
        'GitCheckoutError',
        'RpmOpenError',
        'RpmSigError',
        'RpmInfoError',
        'RpmBuildError',
]


# todo: find a way to logically use fault_code
class GenericError(Exception):
    """
    Custom exceptions entrypoint
    """
    fault_code = errconst.ERR_GENERAL
    from_fault = False
    def __str__(self):
        try:
            return str(self.args[0]['args'][0])
        # pylint: disable=broad-exception-caught
        except Exception:
            try:
                return str(self.args[0])
            # pylint: disable=broad-exception-caught
            except Exception:
                return str(self.__dict__)

# Starting at this point is every error class that pv2 will deal with.
class ProvidedValueError(GenericError):
    """
    What it says on the tin
    """
    fault_code = errconst.ERR_PROVIDED_VALUE

class ExistsValueError(GenericError):
    """
    Value being requested already exists
    """
    fault_code = errconst.ERR_VALUE_EXISTS

class MissingValueError(GenericError):
    """
    Value being requested already exists
    """
    fault_code = errconst.ERR_MISSING_VALUE

class ConfigurationError(GenericError):
    """
    Value being requested already exists
    """
    fault_code = errconst.ERR_CONFIGURATION

class FileNotFound(GenericError):
    """
    Value being requested already exists
    """
    fault_code = errconst.ERR_NOTFOUND

class DownloadError(GenericError):
    """
    Value being requested already exists
    """
    fault_code = errconst.ERR_DOWNLOAD

class MockGenericError(GenericError):
    """
    Mock error exceptions
    """
    fault_code = errconst.MOCK_ERR_GENERIC

class MockUnexpectedError(MockGenericError):
    """
    Mock (or the environment) experienced an unexpected error.
    """
    fault_code = errconst.MOCK_ERR_UNEXPECTED

class MockInvalidConfError(MockGenericError):
    """
    Mock (or the environment) experienced an error with the conf.
    """
    fault_code = errconst.MOCK_ERR_CONF_INVALID

class MockInvalidArchError(MockGenericError):
    """
    Mock (or the environment) didn't like the arch
    """
    fault_code = errconst.MOCK_ERR_ARCH_EXCLUDED

class MockDnfError(MockGenericError):
    """
    Mock (or the environment) had some kind of dnf error
    """
    fault_code = errconst.MOCK_ERR_DNF_ERROR

class MockResultdirError(MockGenericError):
    """
    Mock (or the environment) had some kind of error in the resultdir
    """
    fault_code = errconst.MOCK_ERR_RESULTDIR_GENERIC

class MockSignalReceivedError(MockGenericError):
    """
    Mock had a SIG received
    """
    fault_code = errconst.MOCK_ERR_BUILD_HUP

class GitCommitError(GenericError):
    """
    There was an issue pushing to git
    """
    fault_code = errconst.GIT_ERR_COMMIT

class GitPushError(GenericError):
    """
    There was an issue pushing to git
    """
    fault_code = errconst.GIT_ERR_PUSH

class GitInitError(GenericError):
    """
    There was an issue pushing to git
    """
    fault_code = errconst.GIT_ERR_INIT

class GitCheckoutError(GenericError):
    """
    There was an issue pushing to git
    """
    fault_code = errconst.GIT_ERR_CHECKOUT

class RpmOpenError(GenericError):
    """
    There was an issue opening the RPM
    """
    fault_code = errconst.RPM_ERR_OPEN

class RpmSigError(GenericError):
    """
    There was an issue opening the RPM because the signature could not be
    verified
    """
    fault_code = errconst.RPM_ERR_SIG

class RpmInfoError(GenericError):
    """
    There was an issue opening the RPM because the RPM is not valid.
    """
    fault_code = errconst.RPM_ERR_INFO

class RpmBuildError(GenericError):
    """
    There was an issue building or packing the RPM.
    """
    fault_code = errconst.RPM_ERR_BUILD
