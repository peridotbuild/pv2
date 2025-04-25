# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Git Utilities and Accessories
"""

import os
import pathlib
import git as rawgit
from git import Repo
from git import exc as gitexc
from pv2.util import error as err
from pv2.util import log as pvlog

__all__ = [
        'add_all',
        'apply',
        'clone',
        'commit',
        'init',
        'lsremote',
        'obj',
        'push',
        'tag',
        'get_current_commit',
        'get_current_tag'
]

def add_all(repo):
    """
    Add all files to repo
    """
    try:
        repo.git.add(all=True)
    except Exception as exc:
        raise err.GitCommitError('Unable to add files') from exc

def apply(repo, patch):
    """
    Applies a given patch file to a repo
    """
    actpatch = patch
    if isinstance(patch, pathlib.PosixPath):
        actpatch = patch.as_posix()
    patch_command = ["git", "apply", actpatch]
    try:
        repo.git.execute(patch_command)
    except Exception as exc:
        raise err.GitApplyError('Unable to apply patch') from exc

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
        branch: str = None,
        single_branch: bool = False
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
                branch=branch,
                single_branch=single_branch
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

def obj(git_url_path: str):
    """
    Gets a repo object based on the path name
    """
    path_way = git_url_path
    if not os.path.exists(path_way):
        raise err.GenericError('Path does not exist, are you sure this is a git repo?')

    repo = Repo(path_way)
    return repo

def push(repo, ref=None, force=False):
    """
    push what we want

    if ref is not none (aka an object), we'll push the commit first and
    then the tag ref, this way the commits and tags are in sync.
    """
    active_branch = f'{repo.active_branch.name}:{repo.active_branch.name}'
    try:
        if ref:
            repo.remote('origin').push(active_branch, force=force).raise_if_error()
            repo.remote('origin').push(ref, force=force).raise_if_error()
        else:
            repo.remote('origin').push(active_branch, force=force).raise_if_error()
    # pylint: disable=no-member
    except gitexc.CommandError as exc:
        raise err.GitPushError('Unable to push commit to remote') from exc

def tag(repo, tag_name:str, message: str, force=False):
    """
    make a tag with message
    """
    ref = repo.create_tag(tag_name, message=message, force=force)
    return ref

def get_current_commit(repo: Repo):
    """
    Gets the current commit hash given the current state of the repo.
    """
    current_commit = repo.head.commit
    return current_commit

def get_current_tag(repo: Repo):
    """
    Gets the current tag if possible given the current state of the repo
    object. Otherwise it'll be none
    """
    current_commit = repo.head.commit
    current_tag = next((tag for tag in repo.tags if tag.commit == current_commit), None)
    if not current_tag:
        return None

    return current_tag

def lsremote(url):
    """
    Helps check if a repo exists.

    If repo exists: return references
    If repo exists and is completely empty: return empty dict
    If repo does not exist: raise an error
    """
    remote_refs = {}
    # this gets around a forgejo and gitlab thing of asking for creds on repos
    # that are private or don't even exist.
    os.environ['GIT_ASKPASS'] = '/bin/echo'
    git_cmd = rawgit.cmd.Git()
    try:
        git_cmd.ls_remote(url)
    # pylint: disable=no-member
    except (gitexc.CommandError, gitexc.GitCommandError) as exc:
        pvlog.logger.exception('Repo does not exist or is not accessible: %s', exc.stderr)
        raise err.GitInitError('Repo does not exist or is not accessible')

    for ref in git_cmd.ls_remote(url).split('\n'):
        hash_ref_list = ref.split('\t')
        if len(hash_ref_list) > 1:
            remote_refs[hash_ref_list[1]] = hash_ref_list[0]
    return remote_refs
