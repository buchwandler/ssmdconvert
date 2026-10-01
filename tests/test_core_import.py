import subprocess
import sys


def test_core_import_does_not_load_optional_speech_or_enrichment() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, ssmdconvert; "
                "assert 'ssmdconvert.speech' not in sys.modules; "
                "assert 'spokenform' not in sys.modules; "
                "assert 'pyjev' not in sys.modules"
            ),
        ],
        check=True,
    )
