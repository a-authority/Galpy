"""支持 `python -m galpy` 调用。"""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main() or 0)
