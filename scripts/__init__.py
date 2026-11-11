"""Maintenance scripts, run as modules from the repo root.

For example::

    python -m scripts.audit_pollo_models --help

Being a package is what lets them import `web.*` and each other with plain
top-level imports — no sys.path juggling, no imports after code.
"""
