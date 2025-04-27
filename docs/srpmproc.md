---
title: srpmproc
---

`srpmproc` is the utility that takes a given source repo that is in an expect
"srpm format" and imports it into another git location. While similar to the
importer utility, its purpose is to provide greater flexibility in its imports
and patching capability.

### Compatibility

`srpmproc`, as part of "pv2" is *not* backwards compatible with the previous
version written in golang. This means:

* Do not expect APIs and CLI from the previous version to have equivalents
* Import methodology has been restructured
* Patch methodology has been moved to a pure YAML format
* `PATCH` is not accepted during patching[^1]

If you are wishing to transition from the original `srpmproc` to this version,
please ensure you have read the below sections on usage and the patch format.

### Requirements

To run `srpmproc`, the following is required:

* Fedora or Enterprise Linux 9+ system
* python modules
* rpm-build + \*-(s)rpm-macros
* A few python modules

  * file-magic (python3-file-magic)
  * GitPython (python3-GitPython via EPEL or pip)
  * lxml (python3-lxml)
  * rpm (python3-rpm)
  * pycurl (python3-pycurl)
  * PyYAML (python3-pyyaml)
  * boto3 (optional)
  * botocore (optional)

* A git-forge (or multiple) that you are interacting with

### Usage

!!! note
    Before continuing, please ensure that you have your SSH keys on your system
    and that you have `~/.ssh/config` configured if absolutely necessary. Custom
    SSH key paths are not supported.

There are different ways that `srpmproc` can be utilized. The provided CLI can
do just about anything you'd expect to work on in the general case. For more
advanced use cases, you can hook directly into `pv2.srpmproc.*` modules as you
need. In most cases, you will use the `pv2.srpmproc.rpm` part of the library.

#### rpm

As an extremely minimal example, you can create a simple python script that
performs an import for you.

```
#!/usr/bin/python3
from pv2.srpmproc.rpm import RpmImport as srpmproc
a = srpmproc(
        rpm='bash',
        version='9',
        source_git_host='git.build.angelsofclockwork.net:3000',
        dest_git_host='git.build.angelsofclockwork.net',
        source_org='src-rpms',
        dest_org='rpms',
        source_git_protocol='http',
        distcustom='.el9.0.1')
a.srpmproc_import()
```

What this does is that it imports `bash` from the `c9` branch in the `src-rpms`
organization into the `rpms` organization with a custom dist of `.el9.0.1`. When
the import is finished, assuming there are any changes in the destination, a new
commit and tag will be pushed. The tag will display like so:

```
imports/r9/bash-5.1.8-9.el9.0.1
```

If a `patch` organization was found with a repository of the package name and
there were patches applied, the tag will have a different string.

```
patched/r9/bash-5.1.8-9.el9.0.1
```

This is on purpose to distinguish which imports were unmodified from the source
or if they were patched in some way.

#### CLI

The library already comes with an `srpmproc` script that provides simplified and
easy access to all import options.

To be filled.

### Patching

Patches are performed via reading a configured YAML file in the main branch of
a patch repository. A patch repository will sit in an organization of your
choosing (the default being `patch`). These YAML files can dictate exactly how
a package is going to be patched and provides a decent selection of patch
options, such as search and replace or adding files such as sources and patches.

#### General Format

The YAML is structured as a list of dictionaries, where `patch` is the starting
directive as a list type. Each item in the list is its own dictionary, where the
key is the action that will take place. In this key, its value is another list
of dictionaries, where each list item is a dictionary with key-value pairs
either required or optional for that given action.

Below is a very small example.

```
---
patch:
  - search_and_replace:
      - target: specfile
        find: "%define patchlevel 26"
        replace: "%define patchlevel 27"
...
```

We can validate the items of this patch below.

```
>>> with open('/tmp/conf.yaml', 'r') as f:
...     a = yaml.safe_load(f)
...     f.close()
...
>>> type(a)
<class 'dict'>
>>> type(a['patch'])
<class 'list'>
>>> type(a['patch'][0])
<class 'dict'>
>>> type(a['patch'][0]['search_and_replace'])
<class 'list'>
>>> type(a['patch'][0]['search_and_replace'][0])
<class 'dict'>
>>> type(a['patch'][0]['search_and_replace'][0]['target'])
<class 'str'>
>>>
```

#### Supported Actions

There are a number of supported actions for the patcher.

| Action               | Description                                        | Required Keys                  | Optional Keys                 |
|----------------------|----------------------------------------------------|--------------------------------|-------------------------------|
| `append_release`     | Appends the `Release:` field with a given value    | `suffix`, `enabled` (bool)     |                               |
| `apply_patch`        | Applies an arbitrary patch to the destination repo | `filename`                     |                               |
| `apply_script`       | Runs an arbitrary script                           | `script`                       |                               |
| `add_file`           | Adds a file to a given package into its repostiory | `type`, `name`, `number` (str) |                               | 
| `delete_file`        | Delets a file from a given package                 | `filename`                     |                               |
| `delete_line`        | Deletes a line from a given target file            | `target`, `lines` (list)       |                               |
| `replace_file`       | Replaces a target file with another file           | `filename`                     | `upload_to_lookaside` (bool)  |
| `search_and_replace` | Performs a searcn and replace on a target file     | `target`, `find`, `replace`    | `regex` (bool), `count` (int) |
| `spec_changelog`     | Adds a change log entry to the package spec file   | `name`, `email`, `line` (list) |                               |

Some actions have keys that can accept multi-line values. The following support
multi-line:

* `delete_line` -> `lines` - While it is a list, each item can be a string or a multi-line string
* `search_and_replace` -> `find`
* `search_and_replace` -> `replace`

#### Repository Structure

The patch repository must be setup in a very specific way for your patch files
to be used or recognized.

| Name        | Type      | Usage                                                                 |
|-------------|-----------|-----------------------------------------------------------------------|
| main.yml    | Config    | Applies to all branches being imported                                |
| branch.yml  | Config    | Applies to a single branch being imported                             |
| package.yml | Config    | Applies to a single branch being imported if *not* in the main branch |
| files       | Directory | Contains source files and patches that may be used in a patch config  |
| scripts     | Directory | Contains scripts that may be ran for `apply_script`                   |

!!! note
    The package.yml is only recognized if a branch.yml was not found in main. If
    a branch.yml was found, package.yml will be ignored.

Example structure is below.

```
.
├── files
│   ├── example2.patch
│   ├── example.patch
│   ├── somefile2.txt
│   └── somefile.txt
├── main.yml
├── r9.yml
└── scripts
    └── ex.sh
```

This structure contains a `main.yml`, which will be called no matter the branch
that is imported and `r9.yml`, which will be called after `main.yml` if the `r9`
branch is being imported. All applicable scripts and files are in their
designated directories.

[^1]: 
    If you are coming from the original srpmproc and wish to have this
    support, please file a PR.
