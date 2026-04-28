from pathlib import Path
import plistlib


def test_readme_documents_currency_and_log_behavior():
    readme = Path("README.rst").read_text(encoding="utf-8")

    assert "Python 3.8+" in readme
    assert "2000 isk eur" in readme
    assert "currency-update isk" in readme
    assert "log() is the natural logarithm" in readme
    assert "log10()" in readme


def test_workflow_readme_documents_currency_update():
    with Path("info.plist").open("rb") as fh:
        info = plistlib.load(fh)

    workflow_readme = info["readme"]

    assert "2000 isk eur" in workflow_readme
    assert "currency-update isk" in workflow_readme
    assert "log() is the natural logarithm" in workflow_readme
