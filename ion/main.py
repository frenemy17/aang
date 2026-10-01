"""Backward-compatibility entrypoint for ion.main, pointing to aang.main."""
from aang.main import main

if __name__ == "__main__":
    main()
