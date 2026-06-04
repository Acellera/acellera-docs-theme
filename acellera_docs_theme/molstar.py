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
from molviewspec.nodes import ComponentExpression

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

#: Above this many nonzero-formal-charge atoms, skip labels (avoids thousands
#: of ion labels on a solvated box).
MAX_FORMAL_CHARGE_LABELS = 200

# Hetero selectors rendered as ball-and-stick alongside the polymer cartoon
# (bond orders render automatically from the BinaryCIF bond table; element
# coloring via the molstar color theme).
_BALL_AND_STICK_SELECTORS = ("ligand", "ion", "water", "branched")

# Ball-and-stick atom/bond thickness. MVS's size_factor default of 1 gives
# oversized spheres; 0.5 yields a balanced ball-and-stick close to moleculekit's.
BALL_AND_STICK_SIZE_FACTOR = 0.6

# molstar's cartoon needs a standard polymer backbone trace. Structures with
# fewer cartoon-able standard residues than this (small molecules, ligands,
# non-standard / cyclic peptides like cyclosporin) are drawn entirely as
# ball-and-stick so every atom is visible.
MIN_CARTOON_RESIDUES = 6

# Residues molstar can trace as a cartoon: standard amino acids (incl. common
# protonation-state variants) and nucleotides.
STANDARD_POLYMER_RESNAMES = frozenset({
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "HID", "HIE", "HIP", "HSD", "HSE", "HSP", "CYX", "CYM", "ASH", "GLH",
    "LYN", "ARN", "TYM",
    "A", "U", "G", "C", "T", "DA", "DT", "DG", "DC", "DU", "RA", "RU",
    "RG", "RC",
})


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


def _count_standard_polymer_residues(mol) -> int:
    """Count residues whose resname is a standard (cartoon-able) amino acid or
    nucleotide. Residues are grouped by (resid, insertion, chain, segid)."""
    seen: dict = {}
    for resid, ins, chain, segid, resname in zip(
        mol.resid.tolist(),
        mol.insertion.tolist(),
        mol.chain.tolist(),
        mol.segid.tolist(),
        mol.resname.tolist(),
    ):
        seen[(resid, ins, chain, segid)] = resname
    return sum(1 for rn in seen.values() if rn in STANDARD_POLYMER_RESNAMES)


def build_mvs(
    mol,
    *,
    ball_and_stick_sel: str | None = None,
    representations: list[dict] | None = None,
    highlight_bonds: list[tuple[str, str]] | None = None,
    focus_sel: str | None = None,
) -> str:
    """Build the MVS (mvsj) string for ``mol``.

    A structure with enough standard polymer residues is drawn as a cartoon
    with ball-and-stick hetero (the clean protein/nucleic view). Anything else
    - small molecules, ligands, non-standard or cyclic peptides - is drawn
    entirely as ball-and-stick so every atom stays visible.

    ``ball_and_stick_sel`` is an optional moleculekit atom selection string.
    Atoms matching it are added on top of the default representation as
    ball-and-stick - useful for spotlighting a binding site or a specific
    side chain that otherwise lives inside the protein cartoon.

    ``representations`` is an optional list of overlay dicts, each with a
    required ``sel`` (moleculekit atom selection) plus optional ``type``
    (default ``"ball_and_stick"``; any MVS type, e.g. ``"spacefill"`` for van
    der Waals spheres), ``color`` (SVG name or hex; defaults to element
    coloring), and ``opacity`` (0-1). Any other keys (``size_factor``,
    ``custom``, ...) pass straight through to the MVS representation node.
    Each is drawn on top of the default representation - a green translucent
    ``spacefill`` makes a halo-like highlight, for example.

    ``highlight_bonds`` is an optional list of ``(sel1, sel2)`` atom-selection
    pairs. Each pair is drawn as a fat orange tube between the two atoms -
    useful for pointing out a custom bond (isopeptide, crosslink, ...) over
    the underlying representation. Each selection must resolve to exactly
    one atom.

    The download URL is the sentinel; the bootstrap substitutes the real URL.
    """
    builder = mvs.create_builder()
    structure = (
        builder.download(url=STRUCTURE_URL_SENTINEL)
        .parse(format="bcif")
        .model_structure()
    )
    if _count_standard_polymer_residues(mol) >= MIN_CARTOON_RESIDUES:
        structure.component(selector="polymer").representation(
            type="cartoon"
        ).color(custom={"molstar_color_theme_name": "secondary-structure"})
        for selector in _BALL_AND_STICK_SELECTORS:
            structure.component(selector=selector).representation(
                type="ball_and_stick", size_factor=BALL_AND_STICK_SIZE_FACTOR
            ).color(custom={"molstar_color_theme_name": "element-symbol"})
        # Catch any non-polymer residues the built-in selectors don't pick up
        # (lipids in particular - molstar's ligand/ion/water selectors don't
        # classify POPC/POPE/CHL1/... as ligand, so without this they'd
        # render as nothing). Match by residue name against everything in
        # `mol` that's not a standard polymer residue.
        other_resnames = sorted(
            set(mol.resname.tolist()) - STANDARD_POLYMER_RESNAMES
        )
        if other_resnames:
            extra = [ComponentExpression(label_comp_id=rn) for rn in other_resnames]
            structure.component(selector=extra).representation(
                type="ball_and_stick", size_factor=BALL_AND_STICK_SIZE_FACTOR
            ).color(custom={"molstar_color_theme_name": "element-symbol"})
    else:
        structure.component(selector="all").representation(
            type="ball_and_stick", size_factor=BALL_AND_STICK_SIZE_FACTOR
        ).color(custom={"molstar_color_theme_name": "element-symbol"})

    if ball_and_stick_sel is not None:
        mask = mol.atomselect(ball_and_stick_sel)
        if mask.any():
            indices = [int(i) for i in mask.nonzero()[0]]
            extra = [ComponentExpression(atom_index=i) for i in indices]
            structure.component(selector=extra).representation(
                type="ball_and_stick", size_factor=BALL_AND_STICK_SIZE_FACTOR
            ).color(custom={"molstar_color_theme_name": "element-symbol"})

    for rep in representations or []:
        spec = dict(rep)
        sel = spec.pop("sel")
        color = spec.pop("color", None)
        opacity = spec.pop("opacity", None)
        spec.setdefault("type", "ball_and_stick")
        mask = mol.atomselect(sel)
        if not mask.any():
            continue
        indices = [int(i) for i in mask.nonzero()[0]]
        extra = [ComponentExpression(atom_index=i) for i in indices]
        # Remaining keys (type, custom, size_factor, ...) pass straight through
        # to the MVS representation node.
        component = structure.component(selector=extra).representation(**spec)
        if color is not None:
            component.color(color=color)
        else:
            component.color(custom={"molstar_color_theme_name": "element-symbol"})
        if opacity is not None:
            component.opacity(opacity=opacity)

    if highlight_bonds:
        bonds_group = structure.primitives(color="orange")
        for sel_a, sel_b in highlight_bonds:
            ia = mol.atomselect(sel_a, indexes=True)
            ib = mol.atomselect(sel_b, indexes=True)
            if len(ia) != 1 or len(ib) != 1:
                raise ValueError(
                    "highlight_bonds selections must each pick exactly one "
                    f"atom; got {len(ia)} for {sel_a!r} and {len(ib)} for "
                    f"{sel_b!r}"
                )
            sa = mol.coords[int(ia[0]), :, 0]
            sb = mol.coords[int(ib[0]), :, 0]
            bonds_group.tube(
                start=(float(sa[0]), float(sa[1]), float(sa[2])),
                end=(float(sb[0]), float(sb[1]), float(sb[2])),
                radius=0.3,
            )

    if focus_sel is not None:
        mask = mol.atomselect(focus_sel)
        if mask.any():
            indices = [int(i) for i in mask.nonzero()[0]]
            # Invisible component (no .representation() call) used only as
            # a focus target so the viewer centers on these atoms.
            structure.component(
                selector=[ComponentExpression(atom_index=i) for i in indices]
            ).focus()

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
            position=position,
            text=text,
            label_size=0.7,
            label_color="black",
            # Push the label toward the camera so it doesn't sit inside the
            # ball-and-stick atom sphere at the atom's exact coordinate.
            label_offset=1.0,
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
