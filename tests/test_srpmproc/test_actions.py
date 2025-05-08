# -*-:python; coding:utf-8; -*-
# author: Louis Abel <label@resf.org>
"""
Actions Tester
"""

#import shutil
from pathlib import Path
#import os
import pytest
from pv2.srpmproc.editor import Config
from tests.utils.asserts import assert_files_match

CASES = Path(__file__).parent / "cases"

def get_cases(base_dir):
    """
    Get all test cases
    """
    base_path = Path(base_dir)
    cases = []

    for pkg_dir in base_path.iterdir():
        if not pkg_dir.is_dir():
            continue

        patch_dir = pkg_dir / "PATCH"
        if not patch_dir.is_dir():
            continue

        for branch_dir in pkg_dir.iterdir():
            if not branch_dir.is_dir() or branch_dir.name == "PATCH":
                continue

            specs_dir = branch_dir / "SPECS"
            if not specs_dir.is_dir() or not any(specs_dir.glob("*.spec")):
                continue

            cases.append((pkg_dir.name, branch_dir.name, specs_dir))

    return cases

test_cases = get_cases(CASES)

@pytest.mark.parametrize(
        "package, branch, specs_dir",
        get_cases(CASES),
        ids=[f"{pkg}-{branch}" for pkg, branch, _ in test_cases])
def test_actions(package, branch, specs_dir):
    """
    Run through general tests cases
    """
    print(f'Running editor for {package} on {branch}')
    pkg = Path(CASES) / package / branch
    main_yaml = Path(CASES) / package / "PATCH" / "main.yml"
    branch_yaml = Path(CASES) / package / "PATCH" / f"{branch}.yml"
    clean_spec = Path(specs_dir) / f"{package}.spec"
    expected_spec = Path(specs_dir) / f"{package}.spec.expected"
    if main_yaml.exists():
        Config(config=main_yaml).run(pkg)

    if branch_yaml.exists():
        Config(config=branch_yaml).run(pkg)

    assert_files_match(clean_spec, expected_spec)
