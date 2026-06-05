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


# --- type cross-referencing (stdlib + numpy intersphinx, napoleon) ----------


def test_apply_wires_stdlib_and_numpy_intersphinx():
    ns = _run("MoleculeKit", "Acellera/moleculekit")
    assert ns["intersphinx_mapping"]["python"] == ("https://docs.python.org/3", None)
    assert ns["intersphinx_mapping"]["numpy"] == ("https://numpy.org/doc/stable", None)


def test_apply_enables_napoleon_type_preprocessing():
    ns = _run("MoleculeKit", "Acellera/moleculekit")
    assert ns["napoleon_preprocess_types"] is True
    assert ns["python_use_unqualified_type_names"] is True
    assert ns["napoleon_type_aliases"]["np.ndarray"] == "numpy.ndarray"


def test_apply_wires_common_acellera_class_aliases():
    # Classes shared across moleculekit/htmd/acemd resolve everywhere.
    ns = _run("HTMD", "Acellera/htmd")
    assert ns["napoleon_type_aliases"]["Molecule"] == "moleculekit.molecule.Molecule"
    assert ns["napoleon_type_aliases"]["SmallMol"] == "moleculekit.smallmol.smallmol.SmallMol"


def test_apply_lets_projects_extend_type_aliases():
    ns = {"napoleon_type_aliases": {"MyClass": "mypkg.MyClass"}}
    apply(ns, project_name="MoleculeKit", github_repo="Acellera/moleculekit")
    # project-supplied alias preserved, generic ones added alongside
    assert ns["napoleon_type_aliases"]["MyClass"] == "mypkg.MyClass"
    assert ns["napoleon_type_aliases"]["np.ndarray"] == "numpy.ndarray"
    assert ns["napoleon_type_aliases"]["Molecule"] == "moleculekit.molecule.Molecule"


def test_apply_does_not_override_user_napoleon_settings():
    ns = {"napoleon_preprocess_types": False}
    apply(ns, project_name="MoleculeKit", github_repo="Acellera/moleculekit")
    assert ns["napoleon_preprocess_types"] is False
