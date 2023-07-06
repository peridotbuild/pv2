# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@rockylinux.org>
"""
Git Utilities and Accessories
"""

import os
import git as rawgit
from git import Repo
from git import exc as gitexc
from pv2.util import error as err

__all__ = [
        'add_all',
        'clone',
        'commit',
        'init',
        'push',
        'tag',
        'lsremote'
]

def add_all(repo):
    """
    Add all files to repo
    """
    try:
        repo.git.add(all=True)
    except Exception as exc:
        raise err.GitCommitError('Unable to add files') from exc

def checkout(repo, branch: str, orphan: bool = False):
    """
    Checkout a branch for some reason or another

    Only set orphan to true if this is a brand new branch that never existed
    and you want to avoid tracking from another branch.
    """

    # We are NOT using repo.heads.NAME.checkout() because it does not play
    # very well with branches that have dashes in the name
    try:
        if orphan:
            repo.git.checkout('--orphan', branch)
        else:
            repo.git.checkout(branch)
    except repo.git.exc.CheckoutError as exc:
        raise err.GitCheckoutError('Unable to checkout that branch.') from exc

def clone(
        git_url_path: str,
        repo_name: str,
        to_path: str = None,
        branch: str = None
):
    """
    clone a repo. if branch is None, it will just clone the repo in general and
    you'll be expected to checkout.
    """
    clone_path = to_path
    if not to_path:
        clone_path = f'/var/tmp/{repo_name}'

    try:
        repo = Repo.clone_from(
                url=git_url_path,
                to_path=clone_path,
                branch=branch
        )
    # pylint: disable=no-member
    except gitexc.CommandError as exc:
        raise err.GitInitError(f'Repo could not be cloned: {exc.stderr}') from exc

    return repo

def commit(repo, message: str):
    """
    create a commit message (no tag)
    """
    try:
        repo.index.commit(message=message)
    # pylint: disable=no-member
    except gitexc.CommandError as exc:
        raise err.GitCommitError('Unable to create commit') from exc

def init(
        git_url_path: str,
        repo_name: str,
        to_path: str = None,
        branch: str = None
):
    """
    init a git repo
    """
    path_way = to_path
    if not to_path:
        path_way = f'/var/tmp/{repo_name}'

    if os.path.exists(path_way):
        raise err.GenericError(f'File or directory already exists: {path_way}')

    try:
        repo = Repo.init(path_way, initial_branch=branch)
        repo.create_remote(
                name='origin',
                url=git_url_path
        )
    # pylint: disable=no-member
    except gitexc.CommandError as exc:
        raise err.GitInitError('Could not generate git repository') from exc

    return repo


def push(repo, ref=None):
    """
    push what we want

    if ref is not none (aka an object), we'll push the commit first and
    then the tag ref, this way the commits and tags are in sync.
    """
    active_branch = f'{repo.active_branch.name}:{repo.active_branch.name}'
    try:
        if ref:
            repo.remote('origin').push(active_branch).raise_if_error()
            repo.remote('origin').push(ref).raise_if_error()
        else:
            repo.remote('origin').push(active_branch).raise_if_error()
    # pylint: disable=no-member
    except gitexc.CommandError as exc:
        raise err.GitPushError('Unable to push commit to remote') from exc

def tag(repo, tag_name:str, message: str):
    """
    make a tag with message
    """
    ref = repo.create_tag(tag_name, message=message)
    return ref

def lsremote(url):
    """
    Helps check if a repo exists, and if it does, return references. If not,
    return None and assume it doesn't exist.
    """
    remote_refs = {}
    git_cmd = rawgit.cmd.Git()
    try:
        git_cmd.ls_remote(url)
    # pylint: disable=no-member
    except gitexc.CommandError as exc:
        print(f'Repo does not exist or is not accessible: {exc.stderr}')
        return None

    for ref in git_cmd.ls_remote(url).split('\n'):
        hash_ref_list = ref.split('\t')
        remote_refs[hash_ref_list[1]] = hash_ref_list[0]
    return remote_refs
