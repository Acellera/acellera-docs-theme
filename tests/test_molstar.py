import hashlib
import html as htmllib
import json
from pathlib import Path

import numpy as np

from acellera_docs_theme.molstar import (
    show3d,
    reset_staging,
    publish_structures,
    STAGING_ENV_VAR,
    PUBLISH_SUBDIR,
    MAX_FORMAL_CHARGE_LABELS,
    MIN_CARTOON_RESIDUES,
)


class FakeMol:
    """Duck-typed Molecule stand-in. show3d() uses .write(), .coords,
    .formalcharge, and the residue fields (.resname/.resid/.insertion/
    .chain/.segid) - so tests need no moleculekit."""

    def __init__(self, payload, coords, formalcharge, resname=None, resid=None):
        self.payload = payload
        self.coords = np.asarray(coords, dtype=np.float32)         # (natoms, 3, nframes)
        self.formalcharge = np.asarray(formalcharge, dtype=int)    # (natoms,)
        n = self.coords.shape[0]
        self.resname = np.asarray(resname if resname is not None else ["ALA"] * n)
        self.resid = np.asarray(resid if resid is not None else list(range(n)))
        self.insertion = np.asarray([""] * n)
        self.chain = np.asarray(["A"] * n)
        self.segid = np.asarray(["P"] * n)

    def write(self, path):
        Path(path).write_bytes(self.payload)

    def atomselect(self, sel, indexes=False):
        # Minimal stand-in: select every atom (enough to verify that an
        # overlay representation is emitted for a non-empty selection).
        mask = np.ones(self.coords.shape[0], dtype=bool)
        return mask.nonzero()[0] if indexes else mask


def _std_protein(n_res=8, payload=b"PROT"):
    """A molecule of n_res standard (cartoon-able) residues, 1 atom each."""
    coords = [[[float(i)], [0.0], [0.0]] for i in range(n_res)]
    return FakeMol(payload, coords=coords, formalcharge=[0] * n_res,
                   resname=["ALA"] * n_res, resid=list(range(n_res)))


def _mvs_from_html(html: str) -> dict:
    start = html.index('data-mvs="') + len('data-mvs="')
    end = html.index('"', start)
    return json.loads(htmllib.unescape(html[start:end]))


# --- structure file + marker div -------------------------------------------

def test_show3d_writes_bcif_and_emits_marker_div(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    html = show3d(_std_protein(payload=b"FAKE-BCIF"), height=480)._repr_html_()

    name = f"{hashlib.sha1(b'FAKE-BCIF').hexdigest()}.bcif"
    assert (tmp_path / name).read_bytes() == b"FAKE-BCIF"
    assert 'class="acellera-molstar"' in html
    assert f'data-structure="molstar-structures/{name}"' in html
    assert "height:480px" in html
    assert "<script" not in html

    blob = json.dumps(_mvs_from_html(html))
    assert "__STRUCTURE_URL__" in blob            # bootstrap substitutes this
    assert "cartoon" in blob                       # standard polymer -> cartoon
    assert "ball_and_stick" in blob                # hetero reps
    assert "element-symbol" in blob
    assert "secondary-structure" in blob


def test_show3d_dedupes_identical_structures(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    show3d(_std_protein(payload=b"SAME"))
    show3d(_std_protein(payload=b"SAME"))
    assert len(list(tmp_path.glob("*.bcif"))) == 1


# --- representation policy (the cyclosporin bug) ---------------------------

def test_standard_polymer_renders_as_cartoon(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    blob = json.dumps(_mvs_from_html(show3d(_std_protein(n_res=20))._repr_html_()))
    assert "cartoon" in blob


def test_nonstandard_peptide_renders_as_ball_and_stick_only(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    # Cyclosporin-like: enough residues, but none cartoon-able -> ball-and-stick all.
    nonstd = ["DAL", "MLE", "MVA", "BMT", "ABA", "33X", "34E", "MLE"]
    coords = [[[float(i)], [0.0], [0.0]] for i in range(len(nonstd))]
    mol = FakeMol(b"CSA", coords=coords, formalcharge=[0] * len(nonstd),
                  resname=nonstd, resid=list(range(len(nonstd))))
    blob = json.dumps(_mvs_from_html(show3d(mol)._repr_html_()))
    assert "cartoon" not in blob          # no cartoon trace attempted
    assert "ball_and_stick" in blob       # every atom shown
    assert blob.count('"selector": "all"') == 1


def test_few_standard_residues_uses_ball_and_stick(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    blob = json.dumps(_mvs_from_html(show3d(_std_protein(n_res=MIN_CARTOON_RESIDUES - 1))._repr_html_()))
    assert "cartoon" not in blob
    assert "ball_and_stick" in blob


# --- overlay representations -------------------------------------------------

def test_show3d_representations_render_as_requested_type(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    blob = json.dumps(_mvs_from_html(show3d(
        _std_protein(n_res=20),
        representations=[{"sel": "resname ALA", "type": "spacefill"}],
    )._repr_html_()))
    assert "spacefill" in blob          # the requested overlay type
    assert "cartoon" in blob            # base cartoon still present


def test_show3d_representations_apply_color_and_opacity(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    blob = json.dumps(_mvs_from_html(show3d(
        _std_protein(n_res=20),
        representations=[{"sel": "resname ALA", "type": "spacefill",
                          "color": "green", "opacity": 0.4}],
    )._repr_html_()))
    assert "green" in blob              # uniform color applied
    assert "opacity" in blob and "0.4" in blob   # opacity applied


def test_show3d_representations_pass_through_extra_params(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    # 0.33 is a distinctive value the default view never emits (its hetero
    # ball-and-stick uses 0.6), so finding it proves the dict's size_factor
    # was passed through to the overlay representation.
    blob = json.dumps(_mvs_from_html(show3d(
        _std_protein(n_res=20),
        representations=[{"sel": "resname ALA", "type": "ball_and_stick", "size_factor": 0.33}],
    )._repr_html_()))
    assert "0.33" in blob   # extra MVS kwargs (size_factor) pass through


def test_show3d_default_has_no_spacefill(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    blob = json.dumps(_mvs_from_html(show3d(_std_protein(n_res=20))._repr_html_()))
    assert "spacefill" not in blob


def test_show3d_ball_and_stick_renders_selection(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    blob = json.dumps(_mvs_from_html(show3d(_std_protein(n_res=20), ball_and_stick="resname ALA")._repr_html_()))
    assert "ball_and_stick" in blob


# --- formal-charge labels + cap --------------------------------------------

def test_show3d_adds_one_label_per_charged_atom(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    mol = FakeMol(
        b"L",
        coords=[[[0.0], [0.0], [0.0]],
                [[1.0], [1.0], [1.0]],
                [[2.0], [2.0], [2.0]]],
        formalcharge=[1, 0, -2],
    )
    blob = json.dumps(_mvs_from_html(show3d(mol)._repr_html_()))
    assert blob.count('"+1"') == 1
    assert blob.count('"-2"') == 1


def test_show3d_skips_labels_over_cap(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    n = MAX_FORMAL_CHARGE_LABELS + 1
    coords = [[[float(i)], [0.0], [0.0]] for i in range(n)]
    mol = FakeMol(b"BIG", coords=coords, formalcharge=[1] * n)  # n standard ALA -> cartoon path

    with caplog.at_level("WARNING"):
        blob = json.dumps(_mvs_from_html(show3d(mol)._repr_html_()))

    assert '"+1"' not in blob          # labels skipped
    assert "cartoon" in blob           # representations still present
    assert any("formal charge label" in r.message.lower() for r in caplog.records)


# --- staging helpers -------------------------------------------------------

def test_reset_staging_clears_old_files(tmp_path):
    staging = tmp_path / "molstar-staging"
    staging.mkdir()
    (staging / "stale.bcif").write_bytes(b"old")
    result = reset_staging(str(staging))
    assert Path(result) == staging
    assert staging.is_dir()
    assert list(staging.glob("*.bcif")) == []


def test_publish_structures_copies_into_static(tmp_path):
    staging = tmp_path / "molstar-staging"
    staging.mkdir()
    (staging / "abc.bcif").write_bytes(b"data")
    outdir = tmp_path / "html"
    (outdir / "_static").mkdir(parents=True)
    publish_structures(str(staging), str(outdir))
    assert (outdir / "_static" / PUBLISH_SUBDIR / "abc.bcif").read_bytes() == b"data"


def test_publish_structures_noop_when_staging_missing(tmp_path):
    outdir = tmp_path / "html"
    outdir.mkdir()
    publish_structures(str(tmp_path / "missing"), str(outdir))
    assert not (outdir / "_static" / PUBLISH_SUBDIR).exists()
