"""PDC Policy Generator — reads the Glossary Generator's Classification
Registry and manages PDC Data Identification: author, reconcile, deploy,
drift-check."""
import os


def _app_version():
    """Single source of truth for the app version: the VERSION file beside
       this module, falling back to the literal below if it's missing."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION"),
                  encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except Exception:
        pass
    return "1.5.1"


__version__ = _app_version()
