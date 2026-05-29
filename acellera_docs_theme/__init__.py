"""Acellera unified Sphinx docs branding.

Drop-in helper that wires the Acellera logo, brand colours, navbar override,
and standard icon-link set into a Sphinx ``conf.py``.

Usage in ``conf.py``::

    from acellera_docs_theme import apply
    apply(globals(), project_name="MoleculeKit", github_repo="Acellera/moleculekit")

After the call, the calling conf.py can still override anything in
``html_theme_options`` by reassigning the dict, and add to
``html_static_path`` / ``templates_path`` / ``html_css_files`` freely.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["apply", "__version__"]
__version__ = "0.1.0"

_THIS_DIR = Path(__file__).parent
_STATIC_DIR = str(_THIS_DIR / "_static")
_TEMPLATES_DIR = str(_THIS_DIR / "_templates")
_FAVICON = str(_THIS_DIR / "_static" / "acellera-logo-16x16.png")

# pydata-sphinx-theme renders the navbar logo as ``<img src="_static/<basename>">``
# regardless of any subdirectory in the configured path, so the bundled
# images live directly under ``_static/`` (no ``img/`` subdir) for the
# rendered URL to match the on-disk location.
_LOGO_REL = "_static/acellera_new_web.png"
_ACELLERA_ICON_REL = "_static/acellera-logo-white.png"


def _append_unique(seq: list, item: str) -> list:
    if item not in seq:
        seq.append(item)
    return seq


def apply(
    ns: dict[str, Any],
    *,
    project_name: str,
    github_repo: str,
    extra_icon_links: list[dict[str, str]] | None = None,
) -> None:
    """Wire the Acellera branding into the conf.py namespace ``ns``.

    Parameters
    ----------
    ns
        The conf.py module globals. Always pass ``globals()``.
    project_name
        The text rendered next to the Acellera logo in the navbar
        (e.g. ``"MoleculeKit"``). Pass an empty string to render only
        the logo with no title link.
    github_repo
        ``owner/repo`` string used for the GitHub icon link
        (e.g. ``"Acellera/moleculekit"``).
    extra_icon_links
        Extra icon-link dicts appended after the standard
        Twitter / GitHub / LinkedIn / YouTube set.
    """
    ns.setdefault("html_theme", "pydata_sphinx_theme")
    ns.setdefault("html_context", {"default_mode": "light"})
    ns.setdefault("html_show_sourcelink", True)
    ns.setdefault("html_favicon", _FAVICON)

    # Make bundled assets discoverable by Sphinx.
    ns["html_static_path"] = _append_unique(
        list(ns.get("html_static_path") or []), _STATIC_DIR
    )
    ns["templates_path"] = _append_unique(
        list(ns.get("templates_path") or []), _TEMPLATES_DIR
    )
    ns["html_css_files"] = _append_unique(
        list(ns.get("html_css_files") or []), "custom.css"
    )

    # Mol* 3D viewer assets + extension.
    ns["html_css_files"] = _append_unique(
        ns["html_css_files"], "molstar/molstar.css"
    )
    js_files = list(ns.get("html_js_files") or [])
    # Order matters: the molstar global must exist before the bootstrap runs.
    _append_unique(js_files, "molstar/molstar.js")
    _append_unique(js_files, "molstar/molstar-embed.js")
    ns["html_js_files"] = js_files

    ns["extensions"] = _append_unique(
        list(ns.get("extensions") or []), "acellera_docs_theme.molstar"
    )

    icon_links: list[dict[str, str]] = [
        {
            "name": "Acellera",
            "url": "https://www.acellera.com",
            "icon": _ACELLERA_ICON_REL,
            "type": "local",
        },
        {
            "name": "Twitter",
            "url": "https://twitter.com/acellera",
            "icon": "fab fa-twitter",
            "type": "fontawesome",
        },
        {
            "name": "GitHub",
            "url": f"https://github.com/{github_repo}",
            "icon": "fab fa-github-square",
            "type": "fontawesome",
        },
        {
            "name": "LinkedIn",
            "url": "https://www.linkedin.com/company/acellera/",
            "icon": "fab fa-linkedin",
            "type": "fontawesome",
        },
        {
            "name": "Youtube",
            "url": "https://www.youtube.com/user/acelleralive",
            "icon": "fab fa-youtube",
            "type": "fontawesome",
        },
        {
            "name": "Medium",
            "url": "https://medium.com/playmolecule",
            "icon": "fab fa-medium",
            "type": "fontawesome",
        },
    ]
    if extra_icon_links:
        icon_links.extend(extra_icon_links)

    user_options = ns.get("html_theme_options") or {}
    defaults: dict[str, Any] = {
        "logo": {
            "image_light": _LOGO_REL,
            "image_dark": _LOGO_REL,
            "text": project_name,
        },
        "header_links_before_dropdown": 5,
        "show_toc_level": 2,
        "navigation_depth": 3,
        "use_edit_page_button": False,
        "navigation_with_keys": False,
        "footer_start": ["copyright"],
        "footer_end": [],
        "icon_links": icon_links,
    }
    defaults.update(user_options)
    ns["html_theme_options"] = defaults

    ns.setdefault("html_sidebars", {"**": ["sidebar-nav-bs.html"]})
