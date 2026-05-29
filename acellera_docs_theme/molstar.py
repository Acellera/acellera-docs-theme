"""Mol* 3D viewer integration for Acellera Sphinx docs.

``show3d(mol)`` (used inside remove-input MyST cells) writes the molecule to
BinaryCIF in a build-tree staging dir, builds a MolViewSpec scene mirroring
moleculekit's viewer (polymer cartoon, hetero ball-and-stick with bond orders,
element coloring, and formal-charge labels), and emits a marker div. The Sphinx
``setup(app)`` stages and publishes the structure files.
"""

from __future__ import annotations

import hashlib
import html as _html
import logging
import os
import shutil
import tempfile
from pathlib import Path

import molviewspec as mvs

__all__ = [
    "show3d",
    "MolstarView",
    "build_mvs",
    "setup",
    "STAGING_ENV_VAR",
    "PUBLISH_SUBDIR",
    "MAX_FORMAL_CHARGE_LABELS",
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

#: Above this many nonzero-formal-charge atoms, skip labels (avoids thousands
#: of ion labels on a solvated box).
MAX_FORMAL_CHARGE_LABELS = 200

# Hetero selectors rendered as ball-and-stick (bond orders render automatically
# from the BinaryCIF bond table; element coloring via the molstar color theme).
_BALL_AND_STICK_SELECTORS = ("ligand", "ion", "water")


def _staging_dir() -> Path:
    env = os.environ.get(STAGING_ENV_VAR)
    target = Path(env) if env else Path(tempfile.gettempdir()) / "acellera-molstar"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _serialize(state) -> str:
    return (
        state.dumps()
        if hasattr(state, "dumps")
        else state.model_dump_json(exclude_none=True)
    )


def build_mvs(mol) -> str:
    """Build the MVS (mvsj) string for ``mol``.

    The download URL is the sentinel; the bootstrap substitutes the real URL.
    """
    builder = mvs.create_builder()
    structure = (
        builder.download(url=STRUCTURE_URL_SENTINEL)
        .parse(format="bcif")
        .model_structure()
    )
    structure.component(selector="polymer").representation(type="cartoon").color(
        custom={"molstar_color_theme_name": "secondary-structure"}
    )
    for selector in _BALL_AND_STICK_SELECTORS:
        structure.component(selector=selector).representation(
            type="ball_and_stick"
        ).color(custom={"molstar_color_theme_name": "element-symbol"})

    _add_formal_charge_labels(builder, mol)
    return _serialize(builder.get_state())


def _add_formal_charge_labels(builder, mol) -> None:
    """Add one MVS label primitive per nonzero-formal-charge atom, at the
    atom's frame-0 coordinate. Skips entirely above the cap."""
    charges = mol.formalcharge
    coords = mol.coords  # (natoms, 3, nframes)
    charged = [i for i in range(len(charges)) if int(charges[i]) != 0]
    if not charged:
        return
    if len(charged) > MAX_FORMAL_CHARGE_LABELS:
        logger.warning(
            "Skipping formal charge labels: %d charged atoms exceeds cap %d "
            "(likely a solvated/ionised system; show a prepared structure to "
            "keep labels meaningful).",
            len(charged),
            MAX_FORMAL_CHARGE_LABELS,
        )
        return

    primitives = builder.primitives()
    for i in charged:
        q = int(charges[i])
        text = f"+{q}" if q > 0 else f"{q}"
        position = [
            float(coords[i, 0, 0]),
            float(coords[i, 1, 0]),
            float(coords[i, 2, 0]),
        ]
        primitives.label(
            position=position, text=text, label_size=1.0, label_color="black"
        )


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


def show3d(mol, *, height: int = 420, name: str | None = None) -> MolstarView:
    """Render ``mol`` as an interactive Mol* viewer in the docs.

    Parameters
    ----------
    mol
        A moleculekit ``Molecule`` (needs ``.write(path)`` writing BinaryCIF for
        a ``.bcif`` path, plus ``.coords`` and ``.formalcharge``).
    height
        Viewer height in pixels.
    name
        Reserved for a future on-screen label; unused in v1.
    """
    staging = _staging_dir()
    tmp = staging / f".tmp-{os.getpid()}-{id(mol)}.bcif"
    mol.write(str(tmp))
    digest = hashlib.sha1(tmp.read_bytes()).hexdigest()
    final = staging / f"{digest}.bcif"
    if final.exists():
        tmp.unlink()
    else:
        tmp.rename(final)

    return MolstarView(final.name, build_mvs(mol), height)


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
