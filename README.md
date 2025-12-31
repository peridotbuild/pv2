# pv2

![pv2 last commit](https://img.shields.io/github/last-commit/peridotbuild/pv2/development) ![pv2 issues](https://img.shields.io/github/issues/peridotbuild/pv2?link=https%3A%2F%2Fgithub.com%2Fperidotbuild%2Fpv2%2Fissues) ![prs](https://img.shields.io/github/issues-pr/peridotbuild/pv2?link=https%3A%2F%2Fgithub.com%2Fperidotbuild%2Fpv2%2Fpulls) ![language](https://img.shields.io/badge/language-python-blue) ![license](https://img.shields.io/github/license/peridotbuild/pv2)

pv2 is a backend module framework for building and development. Initially
designed as a POC to support peridot's potential transition to python, it
instead provides utilities that can be used for developers in and outside of the
projects in the RESF (such as Rocky Linux).

For a list of things that we want to look into, check the `TODO` list.

## Supported Operations

* importer utility from packages or a git source (such as Fedora or CentOS
  Stream)
* srpmproc utility - A complete rewrite of srpmproc in python

### srpmproc golang to python transition

`srpmproc`, as written in go, is feature complete, but comes with some problems.
Some of these problems are:

* Issues that cannot be fixed properly due to features being bolted on after the
  fact
* Lack of testing of the components of the tool to ensure bugs have not surfaced
* Command line options and variables that do not mean what they're actually
  called, partly due to the above
* Difficulty in "correct" and "efficient" usage plus understanding by the average
  user, a developer in Rocky Linux SIGs or general contributors, or even a Rocky
  Linux maintainer

While the tool works and does its job well, the issues above hold it back. As a
result, this forced the original author to request that it be rewritten in
python, which can be seen as a more approachable language that some contributors
or users will likely find easier to work with or understand.

It has essentially been rewritten to address the following:

* rpm bindings - golang has *zero* bindings and there appears to be no interest
  upstream to provide these at this time.
* patch configurations - The package configuration from srpmproc was not
  intuitive and complex patching required a patch file to simplify things. This
  rewrite expects a much more simpler YAML formatted patch file and multiple
  patch configurations per release branch can be simplified to the main branch.
* rpkg hooks - `rockypkg` development has started and this may serve as a
  secondary hook to extend/override rpkg related commands.

This by no means implies that golang is going away. Golang will remain the
primary language in the Rocky ecosystem. Build management systems, direct
utilities, and others will remain in golang.

For usage instructions and documentation, see the "docs" pages in this
repository.

## Requirements

* An RPM Distribution

  * Fedora
  * Enterprise Linux 9+ recommended
  * CentOS Stream 9+ recommended

* Python 3.9 or higher
* rpm-build + \*-(s)rpm-macros
* redhat-rpm-config
* A few python modules

  * file-magic (python3-file-magic)
  * GitPython (python3-GitPython via EPEL or pip)
  * lxml (python3-lxml)
  * rpm (python3-rpm)
  * pycurl (python3-pycurl)
  * PyYAML (python3-pyyaml)
  * boto3 (optional)
  * botocore (optional)

* additional packages either in Fedora Linux or EPEL

  * rpmautospec-rpm-macros

## Scripts

Current scripts can be found in `pv2/scripts`.

## Packaging

At this time it is not packaged into an RPM but will in the future and be placed
into a SIG/Core repositories for general consumption.

## Contributing

If you see a bug or a potential enhancement, we always encourage Pull Requests
to be sent in. When sending in your pull request, make sure it is against the
`development` branch. PR's to main will be closed.

To submit a change, we recommend that you do so on GitHub:

* Fork the repository as necessary
* Make a new branch based on the `development` branch - Ensure that it is up-to-date
* Make your changes
* Send in the PR for review to our `development` branch

**Please ensure that your changes are compatible with at least Python 3.9, as
that is the current Enterprise Linux 9 python version.**
