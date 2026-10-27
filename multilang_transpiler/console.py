"""Console helpers that keep CLI output working on legacy Windows code pages."""
import codecs
import sys

_ERROR_HANDLER = "multilang_ascii_fallback"
_FALLBACKS = {
    "\u2192": "->",   # → arrow used in route and dry-run listings
    "\u2014": "-",    # — em dash used in status messages
    "\u2013": "-",    # – en dash
    "\u00d7": "x",    # × multiplication sign
    "\u2026": "...",  # … ellipsis
}


def _fallback(error: UnicodeEncodeError):
    text = error.object[error.start:error.end]
    return "".join(_FALLBACKS.get(char, "?") for char in text), error.end


def configure_console() -> None:
    """Replace characters the active stdout/stderr encoding cannot represent.

    UTF-8 terminals are unaffected. On encodings such as cp1252 (the default for
    redirected output on many Windows machines) unsupported symbols degrade to
    ASCII equivalents instead of crashing with UnicodeEncodeError.
    """
    try:
        codecs.lookup_error(_ERROR_HANDLER)
    except LookupError:
        codecs.register_error(_ERROR_HANDLER, _fallback)
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None or stream.errors not in ("strict", "surrogateescape", None):
            continue
        try:
            reconfigure(errors=_ERROR_HANDLER)
        except (ValueError, OSError):
            pass
