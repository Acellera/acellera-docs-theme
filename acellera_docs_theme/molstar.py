"""Mol* 3D viewer integration for Acellera Sphinx docs.

``show3d(mol)`` (used inside remove-input MyST cells) writes the molecule to
BinaryCIF in a build-tree staging dir, builds a MolViewSpec scene mirroring
moleculekit's viewer (polymer cartoon, hetero ball-and-stick with bond orders,
element coloring, and formal-charge labels), and emits a marker div. The Sphinx
``setup(app)`` stages and publishes the structure files.

The MVS scene builder itself lives in moleculekit
(``moleculekit.viewer.molstar.mvs``) so the docs and the inline notebook viewer
share one implementation; here we only add the docs-specific staging, the
URL-sentinel indirection, and the Sphinx wiring.
"""

from __future__ import annotations

import hashlib
import html as _html
import logging
import os
import shutil
import tempfile
from pathlib import Path

from moleculekit.viewer.molstar.mvs import (
    build_mvs,
    MAX_FORMAL_CHARGE_LABELS,
    MIN_CARTOON_RESIDUES,
    STANDARD_POLYMER_RESNAMES,
)

__all__ = [
    "show3d",
    "MolstarView",
    "build_mvs",
    "setup",
    "STAGING_ENV_VAR",
    "PUBLISH_SUBDIR",
    "MAX_FORMAL_CHARGE_LABELS",
    "MIN_CARTOON_RESIDUES",
    "STANDARD_POLYMER_RESNAMES",
    "reset_staging",
    "publish_structures",
]

logger = logging.getLogger(__name__)

#: Env var the extension exports so show3d() (running in myst-nb's temp dir)
#: knows where to stage BinaryCIF files.
STAGING_ENV_VAR = "ACELLERA_MOLSTAR_STAGING"

#: Subdir under built _static/ where structures are published; also the URL
#: prefix the bootstrap uses to fetch them.
PUBLISH_SUBDIR = "molstar-structures"

#: Placeholder the bootstrap replaces with the depth-correct absolute URL.
STRUCTURE_URL_SENTINEL = "__STRUCTURE_URL__"


def _staging_dir() -> Path:
    env = os.environ.get(STAGING_ENV_VAR)
    target = Path(env) if env else Path(tempfile.gettempdir()) / "acellera-molstar"
    target.mkdir(parents=True, exist_ok=True)
    return target


class MolstarView:
    """Cell output whose ``_repr_html_`` myst-nb bakes into the page."""

    def __init__(self, structure_name: str, mvsj: str, height: int):
        self._structure_name = structure_name
        self._mvsj = mvsj
        self._height = height

    def _repr_html_(self) -> str:
        mvs_attr = _html.escape(self._mvsj, quote=True)
        return (
            '<div class="acellera-molstar" '
            f'data-structure="{PUBLISH_SUBDIR}/{self._structure_name}" '
            f'data-mvs="{mvs_attr}" '
            f'style="width:100%;height:{self._height}px;position:relative"></div>'
        )


def show3d(
    mol,
    *,
    sel: str | None = None,
    height: int = 420,
    name: str | None = None,
    ball_and_stick: str | None = None,
    representations: list[dict] | None = None,
    highlight_bonds: list[tuple[str, str]] | None = None,
    focus: str | None = None,
) -> MolstarView:
    """Render ``mol`` as an interactive Mol* viewer in the docs.

    Parameters
    ----------
    mol
        A moleculekit ``Molecule`` (needs ``.write(path)`` writing BinaryCIF for
        a ``.bcif`` path, plus ``.coords`` and ``.formalcharge``).
    sel
        Optional moleculekit atom selection. When given, only the matching
        atoms are shown: the molecule is filtered to ``sel`` (via
        ``mol.copy(sel=sel)``) before anything is drawn, so it also subsets
        what the ``representations``/``focus`` selections can match. Use it to
        hide bulk solvent, e.g. ``sel="not water"``.
    height
        Viewer height in pixels.
    name
        Reserved for a future on-screen label; unused in v1.
    ball_and_stick
        Optional moleculekit atom selection string. Atoms matching it are
        rendered as ball-and-stick on top of the default representation -
        useful for spotlighting a binding site or a specific residue.
    representations
        Optional list of overlay dicts for full control. Each dict needs a
        ``sel`` (moleculekit atom selection) and may set ``type`` (default
        ``"ball_and_stick"``; e.g. ``"spacefill"`` for van der Waals spheres),
        ``color`` (SVG name or hex), and ``opacity`` (0-1). Any other keys
        (``size_factor``, ``custom``, ...) pass straight through to the MVS
        representation node. Drawn on top of the default representation; a
        translucent green ``spacefill`` gives a halo-like highlight.
    highlight_bonds
        Optional list of ``(sel1, sel2)`` atom-selection pairs. Each pair
        is drawn as a fat orange tube between the two atoms - useful for
        pointing out a custom bond (isopeptide, crosslink, ...). Each
        selection must resolve to exactly one atom.
    focus
        Optional moleculekit atom selection string. The viewer opens
        zoomed in on the matching atoms - handy when the interesting
        feature is buried inside a large system.
    """
    if sel is not None:
        mol = mol.copy(sel=sel)
    staging = _staging_dir()
    tmp = staging / f".tmp-{os.getpid()}-{id(mol)}.bcif"
    mol.write(str(tmp))
    digest = hashlib.sha1(tmp.read_bytes()).hexdigest()
    final = staging / f"{digest}.bcif"
    if final.exists():
        tmp.unlink()
    else:
        tmp.rename(final)

    return MolstarView(
        final.name,
        build_mvs(
            mol,
            structure_url=STRUCTURE_URL_SENTINEL,
            ball_and_stick_sel=ball_and_stick,
            representations=representations,
            highlight_bonds=highlight_bonds,
            focus_sel=focus,
        ),
        height,
    )


def reset_staging(path: str) -> str:
    """Delete and recreate the staging dir so a build carries no stale files."""
    target = Path(path)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    return str(target)


def publish_structures(staging: str, outdir: str) -> None:
    """Copy staged .bcif files into ``<outdir>/_static/<PUBLISH_SUBDIR>/``."""
    src = Path(staging)
    if not src.is_dir():
        return
    dest = Path(outdir) / "_static" / PUBLISH_SUBDIR
    dest.mkdir(parents=True, exist_ok=True)
    for bcif in src.glob("*.bcif"):
        shutil.copy2(bcif, dest / bcif.name)


def _on_builder_inited(app):
    staging = Path(app.outdir).parent / "molstar-staging"
    reset_staging(str(staging))
    os.environ[STAGING_ENV_VAR] = str(staging)


def _on_build_finished(app, exception):
    if exception is not None:
        return
    staging = os.environ.get(STAGING_ENV_VAR)
    if staging:
        publish_structures(staging, str(app.outdir))


def setup(app):
    app.connect("builder-inited", _on_builder_inited)
    app.connect("build-finished", _on_build_finished)
    return {"version": "0.1.0", "parallel_read_safe": True}
