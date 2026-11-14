"""Loaded only in the isolated benchmark subprocess environment."""
import os

if os.environ.get("CONKY_BENCH_ROOT"):
    from fixtures import install

    install()
