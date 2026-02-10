import unittest
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

from tests.test_signal_scoring import *
from tests.test_exit_manager import *

if __name__ == "__main__":
    unittest.main()
