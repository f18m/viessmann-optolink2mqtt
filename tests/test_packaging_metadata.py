import importlib
import os
import sys

import pytest

tomllib = pytest.importorskip("tomllib")  # Python 3.11+

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

PYPROJECT = os.path.realpath(THIS_SCRIPT_DIR + "/../pyproject.toml")
LICENSE = os.path.realpath(THIS_SCRIPT_DIR + "/../LICENSE")


def load_pyproject():
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)


def test_console_script_entry_point_resolves():
    # resolve the entry point like importlib.metadata.EntryPoint.load() does:
    # import the module part, then walk the attribute part
    value = load_pyproject()["project"]["scripts"]["optolink2mqtt"]
    module_name, _, attrs = value.partition(":")
    obj = importlib.import_module(module_name)
    for attr in attrs.split("."):
        obj = getattr(obj, attr)
    assert callable(obj)


def test_license_classifier_matches_license_file():
    with open(LICENSE, encoding="utf-8") as f:
        assert "GNU GENERAL PUBLIC LICENSE" in f.read(200)
    classifiers = load_pyproject()["project"]["classifiers"]
    licenses = [c for c in classifiers if c.startswith("License ::")]
    assert licenses == [
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)"
    ]
