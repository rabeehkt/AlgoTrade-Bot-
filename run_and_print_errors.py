import subprocess
import sys

try:
    result = subprocess.run([sys.executable, "run_backtest.py"], capture_output=True, text=True)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
except Exception as e:
    print(e)
