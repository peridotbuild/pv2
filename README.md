# pv2

pv2 is a backend module framework for building and development. Initially
designed as a POC to support peridot's transition to python, it provides
utilities that can be used for developers in and outside of the projects
in the RESF (such as Rocky Linux).

## Requirements

* An RPM Distribution

  * Fedora
  * Enterprise Linux 8, 9+ recommended
  * CentOS Stream 8, 9+ recommended

* Python 3.6 or higher - Python 3.9+ recommended
* A few python modules

  * file-magic (python3-file-magic)
  * GitPython (python3-GitPython or via pip)
  * lxml (python3-lxml or via pip)
  * rpm (python3-rpm)
  * pycurl (python3-pycurl)

* rpm macros packages

  * \*-rpm-macros
  * \*-srpm-macros

## Example Scripts

Example scripts are found in the `examples` directory, which can utilize
parts of the pv2 module.

## Contributing

If you see a bug or a potential enhancement, we always encourage Pull Requests
to be sent in. When sending in your pull request, make sure it is against the
`development` branch. PR's to main will be closed.

To submit a change, we recommend that you do so on GitHub:

* Fork the repository as necessary
* Make a new branch based on the `development` branch - Ensure that it is up-to-date
* Make your changes
* Send in the PR for review to our `development` branch
