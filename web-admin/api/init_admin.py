"""Compatibility wrapper for `scripts.init_admin`."""

from scripts.init_admin import *  # noqa: F401,F403

if __name__ == "__main__":
    from scripts.init_admin import main
    main()
