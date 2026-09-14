"""Root conftest so pytest adds the repo root to sys.path.

Without this, `tests/` has no __init__.py so pytest treats it as its own
rootpath and never inserts the repo root - `custom_components` would be
unimportable from test modules (ModuleNotFoundError).
"""
