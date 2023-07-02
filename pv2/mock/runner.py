# -*- mode:python; coding:utf-8; -*-
# Louis Abel <label@rockylinux.org>
"""
Mock runners and limited error handler
"""

import os
import re
import logging
from pv2.util import error as err
from pv2.util import fileutil
from pv2.util import constants as const
from pv2.util import processor

__all__ = [
        'MockRunner',
        'MockResult'
]

class MockRunner:
    """
    Mock runner definitions
    """
    def __init__(self, config_path: str):
        """
        Initialize the runner
        """
        self.logger = logging.getLogger(self.__module__)
        self.config_path = config_path

    def init(self, resultdir=None, quiet=None, isolation=None, foreground=False):
        """
        Inits a mock root
        """
        return self.__run_mock(mock_call='init', resultdir=resultdir,
                               quiet=quiet, isolation=isolation,
                               foreground=foreground)

    # pylint: disable=too-many-arguments
    def shell(
            self,
            command: str,
            resultdir=None,
            quiet=None,
            isolation=None,
            foreground=False
    ):
        """
        Runs shell for a given mock root
        """
        return self.__run_mock(mock_call='shell', mock_arg=command,
                               resultdir=resultdir, quiet=quiet,
                               isolation=isolation, foreground=foreground)

    def clean(self, quiet=None, isolation=None, foreground=False):
        """
        Clean up the mock root
        """
        try:
            self.__run_mock(mock_call='clean', quiet=quiet,
                            isolation=isolation, foreground=foreground)
        except MockErrorResulter as exc:
            self.logger.error('Unable to run clean on %s', self.config_path)
            self.logger.error('Output:\n%s\n', exc)

        self.__run_mock(mock_call='clean')

    # pylint: disable=too-many-arguments
    def buildsrpm(
            self,
            spec: str,
            sources: str,
            resultdir=None,
            definitions=None,
            timeout=None,
            quiet=None,
            isolation=None,
            foreground=False
    ):
        """
        Builds a source RPM, but does not actually build the package
        """
        return self.__run_mock(
                mock_call='buildsrpm',
                spec=spec,
                sources=sources,
                resultdir=resultdir,
                definitions=definitions,
                rpmbuild_timeout=timeout,
                quiet=quiet,
                target='noarch',
                isolation=isolation,
                foreground=foreground
        )

    # pylint: disable=too-many-arguments
    def build(
            self,
            srpm_path: str,
            resultdir=None,
            definitions=None,
            timeout=None,
            quiet=None,
            isolation=None,
            foreground=False
    ):
        """
        Builds a given source package
        """
        return self.__run_mock(
                mock_call='rebuild',
                mock_arg=srpm_path,
                resultdir=resultdir,
                rpmbuild_timeout=timeout,
                definitions=definitions,
                quiet=quiet,
                isolation=isolation,
                foreground=foreground
        )

    def __determine_resultdir(self):
        """
        Receives no input. This should figure out where the resultdir
        will ultimately be.
        """

        mock_debug_args = [
                'mock',
                '--root', self.config_path,
                '--debug-config-expanded'
        ]

        mock_debug_run = processor.run_proc_no_output(command=mock_debug_args)
        regex = r"^config_opts\['resultdir'\] = '(.*)'"
        regex_search = re.search(regex, mock_debug_run.stdout, re.MULTILINE)
        if regex_search:
            return regex_search.group(1)

        return None

    # pylint: disable=too-many-locals,too-many-branches
    def __run_mock(
            self,
            mock_call: str,
            mock_arg: str = '',
            resultdir=None,
            foreground=False,
            **kwargs
    ):
        """
        Actually run mock.

        mock_call should be the command being used (such as rebuild, shell, and
        so on)
        mock_arg is a string, and can be an additional argument (some mock
        commands do not need an additional argument, thus default is an empty
        string)
        kwargs can be any set of additional arguments to add to mock as
        key:value pairs. for example, lets say your function accepts an
        argument like isolation and you set it to 'simple', the kwargs.items()
        block will parse it as `--isolation simple`. if your function does not
        require an argument, and it's not a matter of it being true or false,
        you would send it as argument='' to ensure that an additional list item
        is not added after the argument.
        """
        # Note: You will notice that everything appears to be separate list
        # items. This is on purpose to try to make sure subprocess is happy.
        # Don't try to simplify it.
        initial_args = [
                'mock',
                '--root', self.config_path,
                f'--{mock_call}', mock_arg
        ]

        if resultdir:
            initial_args.append('--resultdir')
            initial_args.append(resultdir)

        # As you probably noticed, not all options being sent by the other
        # methods are accounted for, so we are using kwargs to deal with them
        # instead. This is because not all mock commands use the same options
        # (or get the same effects out of them if they can be specified). But
        # we are firm on on the ones that should be set.
        for option, argument in kwargs.items():
            if argument is None:
                continue

            # If we are sending mock specific macro definitions that are not in
            # the config, this is how you do it. It's expected that definitions
            # is a dict with only key value pairs.
            if option == 'definitions':
                for macro, value in argument.items():
                    initial_args.append('--define')
                    # Macro definitions require quotes between name and value.
                    # DO NOT UNDO THIS.
                    initial_args.append(f"'{macro} {value}'")
            # "quiet" is a weird one because it doesn't accept a value in mock.
            # We purposely set it to "None" so it gets passed over (way above).
            # Setting to True will make this flag appear.
            elif option == 'quiet':
                initial_args.append('--quiet')
            elif option == 'isolation':
                if argument in ('simple', 'nspawn', 'simple'):
                    initial_args.append('--isolation')
                    initial_args.append(str(argument))
                else:
                    raise err.ProvidedValueError(f'{argument} is an invalid isolation option.')

            # If we're not covering the obvious ones above that we need special
            # care for, this is where the rest happens. If an argument is sent
            # with an empty string, it'll just show up as --option. Any
            # argument will make it show up as --option argument.
            else:
                initial_args.append(f'--{option}')
                if len(str(argument)) > 0:
                    initial_args.append(str(argument))

        # Might not need this. This just makes sure our list is in order.
        initial_args = [arg for arg in initial_args if arg]
        mock_command = ' '.join(initial_args)
        self.logger.info('The following mock command will be executed: %s', mock_command)

        # If foreground is enabled, all output from mock will show up in the
        # user's terminal (or wherever the output is being sent). This means
        # stdout and stderr will NOT contain any data. It may be better to set
        # "quiet" instead of foreground and then stream the actual log files
        # themselves, but this requires you to be specific on the resultdir to
        # find and stream them.
        if foreground:
            mock_run = processor.run_proc_foreground(command=initial_args)
        else:
            mock_run = processor.run_proc_no_output(command=initial_args)

        # Assign vars based on what happened above.
        mock_config = self.config_path
        exit_code = mock_run.returncode
        stdout = mock_run.stdout
        stderr = mock_run.stderr

        # If a resultdir wasn't presented, we try to look for it. We do this by
        # running mock's debug commands to get the correct value and regex it
        # out.
        if not resultdir:
            resultdir = self.__determine_resultdir()

        if exit_code != 0:
            raise MockErrorResulter(
                    mock_command,
                    exit_code,
                    resultdir)

        return MockResult(
                    mock_command,
                    mock_config,
                    exit_code,
                    stdout,
                    stderr,
                    resultdir)

class MockResult:
    """
    Mock result parser
    """
    # pylint: disable=too-many-arguments
    def __init__(
            self,
            mock_command,
            mock_config,
            exit_code,
            stdout,
            stderr,
            resultdir=None
    ):
        """
        Initialize the mock result parser
        """
        self.mock_command = mock_command
        self.mock_config = mock_config
        self.exit_code = exit_code
        self.__stdout = stdout
        self.__stderr = stderr
        self.resultdir = resultdir

    @property
    def srpm(self):
        """
        Turns a string (or None) of the build source RPM package
        """
        return next(iter(fileutil.filter_files(
            self.resultdir,
            lambda file: file.endswith('src.rpm'))),
            None
        )

    @property
    def rpms(self):
        """
        Returns a list of RPM package paths in the resultdir.
        """
        return fileutil.filter_files(
                self.resultdir,
                lambda file: re.search(r'(?<!\.src)\.rpm$', file)
        )

    @property
    def logs(self):
        """
        Returns a list of mock log files
        """
        mock_log_files = fileutil.filter_files(self.resultdir,
                                          lambda file: file.endswith('.log'))

        # If we are using the chroot scan plugin, then let's search for other
        # logs that we may have cared about in this build.
        chroot_scan_dir = os.path.join(self.resultdir, 'chroot_scan')
        if os.path.exists(chroot_scan_dir):
            for dir_name, _, files in os.walk(chroot_scan_dir):
                for file in files:
                    if file.endswith('.log'):
                        mock_log_files.append(os.path.join(os.path.abspath(dir_name), file))

        return mock_log_files

    @property
    def stdout(self):
        """
        Returns stdout
        """
        return self.__stdout

    @property
    def stderr(self):
        """
        Returns stdout
        """
        return self.__stderr

# Is there a better way to do this?
# Note that this isn't in pv2.util.error because this *may* be used to parse
# logs at some point, and we do not want to add additional parsers to
# pv2.util.error or have it import mock modules if it's not actually required.
# I don't want to have to import more than needed in pv2.util.error.
class MockErrorResulter(Exception):
    """
    Mock error result checker.

    Takes in an exception and reports the exit code.
    """
    def __init__(
            self,
            mock_command,
            exit_code,
            resultdir=None,
            result_message=None
    ):
        """
        Initialize the MockError class this way.
        """

        # We probably don't need to do this, but it doesn't hurt. There should
        # always be a resultdir to reference.
        self.build_log = None
        self.root_log = None

        if resultdir:
            self.build_log = os.path.join(resultdir, 'build.log')
            self.root_log = os.path.join(resultdir, 'root.log')

        if not result_message:
            result_message = f'Command {mock_command} exited with code ' \
                    f'{exit_code}. Please review build.log and root.log ' \
                    f'located in the main root ({resultdir}) or bootstrap root.'

        # This is awkward. I can't think of a better way to do this.
        if exit_code == const.MockConstants.MOCK_EXIT_ERROR:
            #error_object = errmock(self.root_log, self.build_log)
            #error_dict = error_object.check_for_error()

            #if len(error_dict) > 0:
            #    result_message = f'Command {mock_command} exited with code ' \
            #            '{error_dict["error_code"]}: {error_dict["error_message"]}'

            # pylint: disable=non-parent-init-called
            err.MockGenericError.__init__(self, result_message)
            # Send to log parser to figure out what it actually is, and use the
            # above to report it.
        elif exit_code == const.MockConstants.MOCK_EXIT_SETUID:
            # pylint: disable=non-parent-init-called
            result_message = 'Either setuid/setgid is not available or ' \
                    'another error occurred (such as a bootstrap init failure). ' \
                    'Please review build.log or root.log, in the main root ' \
                    f'({resultdir}) or bootstrap root if applicable.'
            err.MockGenericError.__init__(self, result_message)

        elif exit_code == const.MockConstants.MOCK_EXIT_INVCONF:
            # pylint: disable=non-parent-init-called
            err.MockInvalidConfError.__init__(self, result_message)

        elif exit_code == const.MockConstants.MOCK_EXIT_INVARCH:
            # pylint: disable=non-parent-init-called
            err.MockInvalidArchError.__init__(self, result_message)

        elif exit_code in (const.MockConstants.MOCK_EXIT_DNF_ERROR,
                           const.MockConstants.MOCK_EXIT_EXTERNAL_DEP):
            # pylint: disable=non-parent-init-called
            err.MockDnfError.__init__(self, result_message)

        elif exit_code == const.MockConstants.MOCK_EXIT_RESULTDIR_NOT_CREATED:
            # pylint: disable=non-parent-init-called
            err.MockResultdirError.__init__(self, result_message)

        elif exit_code in (const.MockConstants.MOCK_EXIT_SIGHUP_RECEIVED,
                           const.MockConstants.MOCK_EXIT_SIGPIPE_RECEIVED,
                           const.MockConstants.MOCK_EXIT_SIGTERM_RECEIVED):
            # pylint: disable=non-parent-init-called
            err.MockSignalReceivedError.__init__(self, result_message)

        else:
            result_message = 'An unexpected mock error was caught. Review ' \
                    f'stdout/stderr or other logs to determine the issue. ' \
                    f'\n\nMock command: {mock_command}'
            # pylint: disable=non-parent-init-called
            err.MockUnexpectedError.__init__(self, result_message)
