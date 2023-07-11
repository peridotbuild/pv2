# pv2

![pv2 last commit](https://img.shields.io/github/last-commit/peridotbuild/pv2/development) ![pv2 issues](https://img.shields.io/github/issues/peridotbuild/pv2?link=https%3A%2F%2Fgithub.com%2Fperidotbuild%2Fpv2%2Fissues) ![prs](https://img.shields.io/github/issues-pr/peridotbuild/pv2?link=https%3A%2F%2Fgithub.com%2Fperidotbuild%2Fpv2%2Fpulls)

![language](https://img.shields.io/badge/language-python-blue)

![license](https://img.shields.io/github/license/peridotbuild/pv2)

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
* rpm-build
* A few python modules

  * file-magic (python3-file-magic)
  * GitPython (python3-GitPython or via pip)
  * lxml (python3-lxml or via pip)
  * rpm (python3-rpm)
  * pycurl (python3-pycurl)

* rpm macros packages (brought in by rpm-build package)

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
