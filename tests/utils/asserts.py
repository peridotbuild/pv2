from pathlib import Path
import difflib

def assert_files_match(result_file: Path, expected_file: Path):
    """
    Compares two text files
    """
    result_lines = result_file.read_text().splitlines()
    expected_lines = expected_file.read_text().splitlines()

    if result_lines != expected_lines:
        diff = '\n'.join(difflib.unified_diff(
            expected_lines,
            result_lines,
            fromfile=str(expected_file),
            tofile=str(result_file),
            lineterm=''
        ))
        raise AssertionError(f"Mismatch between {result_file.name} and expected result:\n{diff}")
