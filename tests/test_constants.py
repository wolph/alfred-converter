import os
import pickle
import subprocess
import sys
from pathlib import Path

from converter import constants, convert, main


def test_units_xml_file_loads_outside_repo_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    units = convert.Units()
    units.load(constants.UNITS_XML_FILE)

    assert units.get('m').name == 'metre'


def test_units_xml_file_falls_back_to_package_data(tmp_path, monkeypatch):
    package_dir = tmp_path / 'converter'
    package_dir.mkdir()
    package_xml = package_dir / 'poscUnits22.xml'
    package_xml.touch()

    constants_file = package_dir / 'constants.py'
    monkeypatch.setattr(constants, '__file__', str(constants_file))

    assert constants._resolve_units_xml_file() == package_xml


def test_units_xml_file_prefers_env_override(tmp_path, monkeypatch):
    override_xml = tmp_path / 'custom-units.xml'
    monkeypatch.setenv('UNITS_XML_FILE', str(override_xml))

    assert constants._resolve_units_xml_file() == override_xml


def test_load_units_rejects_stale_pickle(tmp_path, monkeypatch):
    pickle_file = tmp_path / 'units.pickle'
    stale_units = convert.Units()
    stale_units.load(constants.UNITS_XML_FILE)
    stale_units.cache_version = constants.UNITS_CACHE_VERSION - 1
    stale_units.stale_marker = True

    with pickle_file.open('wb') as fh:
        pickle.dump(stale_units, fh, -1)

    monkeypatch.setattr(constants, 'UNITS_PICKLE_FILE', str(pickle_file))

    units = main.load_units()

    assert (
        getattr(units, 'cache_version', None)
        == constants.UNITS_CACHE_VERSION
    )
    assert not hasattr(units, 'stale_marker')


def test_load_units_rejects_stale_pickle_under_optimized_python(tmp_path):
    pickle_file = tmp_path / 'units.pickle'
    stale_units = convert.Units()
    stale_units.load(constants.UNITS_XML_FILE)
    stale_units.cache_version = constants.UNITS_CACHE_VERSION - 1
    stale_units.stale_marker = True

    with pickle_file.open('wb') as fh:
        pickle.dump(stale_units, fh, -1)

    env = os.environ.copy()
    env['TEST_UNITS_PICKLE_FILE'] = str(pickle_file)
    result = subprocess.run(
        [
            sys.executable,
            '-O',
            '-c',
            (
                'import os\n'
                'from converter import constants, main\n'
                'constants.UNITS_PICKLE_FILE = '
                'os.environ["TEST_UNITS_PICKLE_FILE"]\n'
                'units = main.load_units()\n'
                'print(getattr(units, "cache_version", None))\n'
                'print(hasattr(units, "stale_marker"))\n'
            ),
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == [
        str(constants.UNITS_CACHE_VERSION),
        'False',
    ]
