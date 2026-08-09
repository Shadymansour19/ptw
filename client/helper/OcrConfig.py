"""Points pytesseract at the Tesseract binary bundled with the frozen (Nuitka) build
(`client/tesseract-bin/`, staged in `.github/workflows/build.yml`), since a frozen build
can't rely on Tesseract being installed and on PATH the way a dev environment can. Both
functions here are no-ops in dev, where Tesseract is expected to already be on the system.
"""

import os
import platform
import pytesseract

from helper.utils import resource_path


def configureTesseract():
    """Points pytesseract at the Tesseract binary bundled by the CI build (client/tesseract-bin,
    staged in .github/workflows/build.yml) instead of relying on it being on PATH. No-op in dev,
    where Tesseract is expected to already be installed system-wide."""
    bundleDir = resource_path('tesseract-bin')
    if not os.path.isdir(bundleDir):
        return

    exeName = 'tesseract.exe' if platform.system() == 'Windows' else 'tesseract'
    pytesseract.pytesseract.tesseract_cmd = os.path.join(bundleDir, exeName)

    libDir = os.path.join(bundleDir, 'lib')
    if os.path.isdir(libDir):
        os.environ['LD_LIBRARY_PATH'] = libDir + os.pathsep + os.environ.get('LD_LIBRARY_PATH', '')


def tessdataConfig() -> str:
    """--tessdata-dir override for pytesseract calls, so OCR doesn't depend on TESSDATA_PREFIX
    being set correctly for whatever Tesseract version is in use. Empty string in dev (rely on
    the system installation's own tessdata)."""
    tessdataDir = os.path.join(resource_path('tesseract-bin'), 'tessdata')
    return f'--tessdata-dir "{tessdataDir}"' if os.path.isdir(tessdataDir) else ''
