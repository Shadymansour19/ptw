"""helper/OcrConfig.py: pointing pytesseract at a bundled Tesseract without one being installed.

`resource_path()` is redirected at a temp directory standing in for the frozen build's
resource root, so every branch (no bundle / bundle / bundle with libs / Windows exe name /
tessdata override) is exercised on real directories, never the developer's machine.
"""

import os
import sys

import pytest
import pytesseract

import helper.OcrConfig as ocr
from helper.OcrConfig import configureTesseract, tessdataConfig

SENTINEL_CMD = 'tesseract-from-before-the-test'


@pytest.fixture
def resources(tmp_path, monkeypatch):
    """Redirect resource_path() at tmp_path and isolate the process-wide state the module touches."""
    monkeypatch.setattr(ocr, 'resource_path', lambda name: str(tmp_path / name))
    monkeypatch.setattr(pytesseract.pytesseract, 'tesseract_cmd', SENTINEL_CMD)
    monkeypatch.delenv('LD_LIBRARY_PATH', raising=False)
    monkeypatch.setattr(ocr.platform, 'system', lambda: 'Linux')
    return tmp_path


class TestConfigureTesseract:
    def test_dev_environment_without_a_bundle_is_a_no_op(self, resources):
        configureTesseract()
        assert pytesseract.pytesseract.tesseract_cmd == SENTINEL_CMD
        assert 'LD_LIBRARY_PATH' not in os.environ

    def test_bundle_found_on_linux(self, resources):
        (resources / 'tesseract-bin').mkdir()
        configureTesseract()
        assert pytesseract.pytesseract.tesseract_cmd == str(resources / 'tesseract-bin' / 'tesseract')
        assert 'LD_LIBRARY_PATH' not in os.environ          # no lib/ shipped -> loader path untouched

    def test_bundle_found_on_windows_uses_the_exe_name(self, resources, monkeypatch):
        (resources / 'tesseract-bin').mkdir()
        monkeypatch.setattr(ocr.platform, 'system', lambda: 'Windows')
        configureTesseract()
        assert pytesseract.pytesseract.tesseract_cmd == str(resources / 'tesseract-bin' / 'tesseract.exe')

    def test_bundled_libs_are_prepended_to_the_loader_path(self, resources, monkeypatch):
        lib = resources / 'tesseract-bin' / 'lib'
        lib.mkdir(parents=True)
        monkeypatch.setenv('LD_LIBRARY_PATH', '/opt/existing')
        configureTesseract()
        assert os.environ['LD_LIBRARY_PATH'] == f'{lib}{os.pathsep}/opt/existing'

    def test_bundled_libs_with_no_prior_loader_path(self, resources):
        lib = resources / 'tesseract-bin' / 'lib'
        lib.mkdir(parents=True)
        configureTesseract()
        assert os.environ['LD_LIBRARY_PATH'] == f'{lib}{os.pathsep}'

    def test_frozen_build_resolves_the_bundle_under_meipass(self, tmp_path, monkeypatch):
        # the real resource_path(): frozen builds set sys._MEIPASS and everything resolves under it
        monkeypatch.setattr(pytesseract.pytesseract, 'tesseract_cmd', SENTINEL_CMD)
        monkeypatch.delenv('LD_LIBRARY_PATH', raising=False)
        monkeypatch.setattr(ocr.platform, 'system', lambda: 'Linux')
        monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
        (tmp_path / 'tesseract-bin').mkdir()
        configureTesseract()
        assert pytesseract.pytesseract.tesseract_cmd == os.path.join(str(tmp_path), 'tesseract-bin', 'tesseract')


class TestTessdataConfig:
    def test_empty_in_dev(self, resources):
        assert tessdataConfig() == ''

    def test_bundle_without_tessdata_is_still_empty(self, resources):
        (resources / 'tesseract-bin').mkdir()
        assert tessdataConfig() == ''

    def test_points_at_the_bundled_tessdata(self, resources):
        tessdata = resources / 'tesseract-bin' / 'tessdata'
        tessdata.mkdir(parents=True)
        assert tessdataConfig() == f'--tessdata-dir "{tessdata}"'
