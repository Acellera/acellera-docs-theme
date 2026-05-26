# acellera-docs-theme

Shared Sphinx branding for Acellera docs sites
(`software.acellera.com`, `moleculekit`, `htmd`, `acemd`, `playmolecule`).

Bundles:

- Acellera logo PNGs (`_static/img/`)
- Brand-coloured CSS (`_static/custom.css`)
- Navbar override that splits the logo link (→ `software.acellera.com`)
  from the project-name text link (→ docs root): `_templates/navbar-logo.html`
- A `theme_options` set with the standard icon links (Twitter / GitHub /
  LinkedIn / YouTube), light-mode default, etc.

## Usage

Add it to your docs dependency group:

```toml
[dependency-groups]
docs = [
  "acellera-docs-theme @ git+https://github.com/Acellera/acellera-docs-theme.git",
  "sphinx>=7",
  "pydata-sphinx-theme>=0.16",
  # ...your other docs tools
]
```

In `conf.py`:

```python
from acellera_docs_theme import apply

apply(
    globals(),
    project_name="MoleculeKit",          # shown next to the logo
    github_repo="Acellera/moleculekit",  # used for the GitHub icon link
)

# Project-specific config follows (extensions, source_suffix, MyST-NB, etc.).
project = "MoleculeKit"
copyright = "2026, Acellera"
author = "Acellera"

extensions = [
    "sphinx.ext.autodoc",
    # ...
]
```

`apply()` only sets defaults — any value you assign in `conf.py`
*after* the call wins. `html_theme_options` is merged: keys you set
yourself override the corresponding defaults, the rest are preserved.

## Updating the look

Edit the CSS / template / logos here, bump the version in `pyproject.toml`,
tag, push. Re-run each consumer repo's docs CI and they pick up the new
branding on next install.
