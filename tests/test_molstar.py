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
)


class FakeMol:
    """Duck-typed Molecule stand-in. show3d() uses .write(), .coords,
    .formalcharge only - so tests need no moleculekit."""

    def __init__(self, payload: bytes, coords, formalcharge):
        self.payload = payload
        self.coords = np.asarray(coords, dtype=np.float32)        # (natoms, 3, nframes)
        self.formalcharge = np.asarray(formalcharge, dtype=int)   # (natoms,)

    def write(self, path):
        Path(path).write_bytes(self.payload)


def _mvs_from_html(html: str) -> dict:
    start = html.index('data-mvs="') + len('data-mvs="')
    end = html.index('"', start)
    return json.loads(htmllib.unescape(html[start:end]))


# --- Task 4: structure file, representations, marker div -------------------

def test_show3d_writes_bcif_and_emits_marker_div(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    mol = FakeMol(b"FAKE-BCIF", coords=[[[1.0], [2.0], [3.0]]], formalcharge=[0])

    html = show3d(mol, height=480)._repr_html_()

    name = f"{hashlib.sha1(b'FAKE-BCIF').hexdigest()}.bcif"
    assert (tmp_path / name).read_bytes() == b"FAKE-BCIF"
    assert 'class="acellera-molstar"' in html
    assert f'data-structure="molstar-structures/{name}"' in html
    assert "height:480px" in html
    assert "<script" not in html

    tree = _mvs_from_html(html)
    blob = json.dumps(tree)
    assert "__STRUCTURE_URL__" in blob            # bootstrap substitutes this
    assert "cartoon" in blob
    assert "ball_and_stick" in blob
    assert "element-symbol" in blob               # element coloring on hetero
    assert "secondary-structure" in blob          # cartoon coloring


def test_show3d_dedupes_identical_structures(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    mol = FakeMol(b"SAME", coords=[[[0.0], [0.0], [0.0]]], formalcharge=[0])
    show3d(mol)
    show3d(mol)
    assert len(list(tmp_path.glob("*.bcif"))) == 1


# --- Task 5: formal-charge labels + cap ------------------------------------

def test_show3d_adds_one_label_per_charged_atom(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    # 3 atoms: charges +1, 0, -2  -> expect labels "+1" and "-2" only.
    mol = FakeMol(
        b"L",
        coords=[[[0.0], [0.0], [0.0]],
                [[1.0], [1.0], [1.0]],
                [[2.0], [2.0], [2.0]]],
        formalcharge=[1, 0, -2],
    )
    tree = _mvs_from_html(show3d(mol)._repr_html_())
    blob = json.dumps(tree)
    assert blob.count('"+1"') == 1
    assert blob.count('"-2"') == 1


def test_show3d_skips_labels_over_cap(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(STAGING_ENV_VAR, str(tmp_path))
    n = MAX_FORMAL_CHARGE_LABELS + 1
    coords = [[[float(i)], [0.0], [0.0]] for i in range(n)]
    mol = FakeMol(b"BIG", coords=coords, formalcharge=[1] * n)

    with caplog.at_level("WARNING"):
        tree = _mvs_from_html(show3d(mol)._repr_html_())

    blob = json.dumps(tree)
    assert '"+1"' not in blob          # labels skipped
    assert "cartoon" in blob           # representations still present
    assert any("formal charge label" in r.message.lower() for r in caplog.records)


# --- Task 6: staging helpers -----------------------------------------------

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
