import pytest
import sys

if __name__ == "__main__":
    # Run tests and capture output
    retcode = pytest.main(["-v", "tests/test_signal_scoring.py", "tests/test_exit_manager.py"])
    sys.exit(retcode)
