"""Tests for acellera_docs_theme.apply() — branding + cross-project wiring."""

from acellera_docs_theme import apply


def _run(project_name, github_repo, **kw):
    ns = {}
    apply(ns, project_name=project_name, github_repo=github_repo, **kw)
    return ns


# --- intersphinx cross-project wiring ---------------------------------------


def test_apply_wires_sibling_intersphinx_mappings():
    ns = _run("MoleculeKit", "Acellera/moleculekit")
    mapping = ns["intersphinx_mapping"]
    assert mapping["htmd"] == ("https://software.acellera.com/htmd/", None)
    assert mapping["acemd"] == ("https://software.acellera.com/acemd/", None)


def test_apply_does_not_link_a_project_to_itself():
    ns = _run("MoleculeKit", "Acellera/moleculekit")
    assert "moleculekit" not in ns["intersphinx_mapping"]


def test_apply_sets_html_baseurl_to_own_site():
    ns = _run("HTMD", "Acellera/htmd")
    assert ns["html_baseurl"] == "https://software.acellera.com/htmd/"


def test_apply_enables_intersphinx_extension():
    ns = _run("ACEMD", "Acellera/htmd")
    assert "sphinx.ext.intersphinx" in ns["extensions"]


def test_apply_preserves_user_supplied_intersphinx_mapping():
    ns = {"intersphinx_mapping": {"python": ("https://docs.python.org/3/", None)}}
    apply(ns, project_name="HTMD", github_repo="Acellera/htmd")
    assert ns["intersphinx_mapping"]["python"] == ("https://docs.python.org/3/", None)
    assert "moleculekit" in ns["intersphinx_mapping"]


def test_apply_intersphinx_slug_override_excludes_self():
    # project_name need not match the published slug; the explicit slug wins.
    ns = _run("ACEMD Molecular Dynamics", "Acellera/htmd", intersphinx_slug="acemd")
    assert "acemd" not in ns["intersphinx_mapping"]
    assert "htmd" in ns["intersphinx_mapping"]
    assert ns["html_baseurl"] == "https://software.acellera.com/acemd/"
