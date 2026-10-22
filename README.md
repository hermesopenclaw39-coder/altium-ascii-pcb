# altium-ascii-pcb

**English** | [简体中文](README.zh-CN.md)

> Read and write Altium Designer ASCII schematics (`.SchDoc`) and PCBs (`.PcbDoc`) with plain Python: batch-assign footprints, place components by block, audit connectivity, and diagnose the record-structure bugs that make AD crash on open.
>
> It also ships as an **Agent Skill**. Drop it into Claude Code / WorkBuddy and an agent can edit your EDA files directly, with the file-format rules baked in so it does not corrupt the document.

---

## Why this exists

Altium's ASCII export is plain text: `|KEY=VALUE|KEY=VALUE`. It looks trivial to edit. It is not. Record order and index rules are extremely brittle: one wrong field and AD does not complain, it dies with an `Access Violation` and all you get is an address inside `AdvSch.dll`.

Every row below is a bug reproduced on a real machine:

| Symptom | What it actually was |
|---|---|
| `Access violation ... Exception Occurred In OpenObject` | Footprint records `45/46/48` appended at the end of the file, detached from their component's child-record block |
| `List index out of bounds (N)` | `INDEXINSHEET` collided with AD's internal list. Files saved by AD itself do not contain this field at all |
| PCB opens with empty shells, ECO says `Unknown Pin: Pin C1-1` | Schematic components had no footprint model, so AD created pad-less components |
| Diff dialog shows `No Change` everywhere, but the board is empty | Comparing the wrong SchDoc, or comparing in the wrong direction (PCB → schematic) |
| `Match Nets` dialog appears | The target PCB already has other nets, so AD suspects a net rename. Update into a blank board instead |

This repo turns those rules into scripts and notes, so nobody has to rediscover them.

## What's inside

| Script | Purpose |
|---|---|
| `scripts/sch_inspect.py` | Schematic audit: component count, duplicate designators, **footprint-chain completeness**, floating pins, wire count |
| `scripts/sch_add_footprints.py` | **Batch footprint assignment**: inserts `45/46/48` after the component's `44` and remaps `OWNERINDEX` across the whole table |
| `scripts/pcb_inspect.py` | PCB audit: off-board parts, overlapping courtyards, **whether each net is fully connected**, same-layer shorts |
| `scripts/pcb_place.py` | Place parts by `Designator,Block` region, avoiding real courtyards, designator auto-moved above the part |

Standard library only (plus `olefile` if you want to read `.IntLib`).

> Console output is currently Chinese. The numbers and structure are still readable, and localisation is welcome.

## Install

This repository follows the standard Agent Skill layout (`SKILL.md` + `scripts/` + `references/`) and works with any agent that supports skills. Clone it first:

```bash
git clone https://github.com/hermesopenclaw39-coder/altium-ascii-pcb.git
```

| Tool | Skill directory |
|---|---|
| Claude Code | `~/.claude/skills/altium-ascii-pcb/` (project-only: `.claude/skills/altium-ascii-pcb/`) |
| WorkBuddy | `~/.workbuddy-ai/skills/altium-ascii-pcb/` |
| Claude app | Zip the repo and upload it under Skills |

```bash
mkdir -p ~/.claude/skills && cp -r altium-ascii-pcb ~/.claude/skills/
```

You can also use the scripts directly, without installing anything:

```bash
python scripts/sch_inspect.py schematic.SchDoc
```

## Quick start

### 1. Audit a schematic

```bash
python scripts/sch_inspect.py schematic.SchDoc
```

Reports: record count and `WEIGHT` consistency, designator duplicates, how many components carry a footprint, floating pins with coordinates, wire segments.

### 2. Batch-assign footprints

Write a `footprint_map.json` keyed by the component's `LIBREFERENCE`:

```json
{
  "Resistor": "AXIAL-0.4",
  "Capacitor": "RAD-0.1",
  "741_DIP8": "DIP-8",
  "Header3": "HDR1X3"
}
```

```bash
python scripts/sch_add_footprints.py schematic.SchDoc --map footprint_map.json
```

The script backs up to `*.bak_fp` first. Re-running `sch_inspect.py` should then report `footprints complete: 94 / 94`.

### 3. Audit a PCB

```bash
python scripts/pcb_inspect.py board.PcbDoc
```

Reports record/component/pad/net/track counts, off-board parts, overlapping courtyards, per-net connectivity (including which pads form each fragment), and same-layer crossings between different nets.

### 4. Place parts by region

`blocks.csv`:

```csv
Designator,Block
R1,A
R2,A
U1,B
```

```bash
python scripts/pcb_place.py board.PcbDoc --blocks blocks.csv --cols 3 --rows 3
```

`Block` is `A..I`, mapped to a `cols × rows` grid in reading order (top→bottom, left→right). Tall parts get their own column strips; the rest adapt, and nothing is allowed to fall off the board outline.

## Three hard rules

1. **Child records must stay adjacent to their parent.** In a SchDoc a component is one contiguous run: `component(1) → designator(34) → parameter(41) → implementation list(44) → footprint(45) → 46 → 48 → following primitives`. Appending `45` at end of file = AD crashes in `OpenObject`.

2. **After inserting records, remap `OWNERINDEX` across the whole table.** The convention is `OWNERINDEX = parent position + off`; positions start at 0 right after the header, and `off` is constant within a file (`0` for files exported by AD itself, possibly `-1` for hand-built files). The scripts probe it automatically.

3. **AD converts ASCII to binary as soon as it saves.** Do all scripted edits on the unsaved ASCII copy. Once AD has saved the file, re-export with `Save As → ASCII`.

## What not to try

- **Do not script AD's menus.** When AD runs elevated, simulated keys and mouse clicks are blocked by UIPI and the menus simply ignore them; only standard modal dialogs accept `{ENTER}`.
- **Do not hand-write `RECORD=Polygon` (copper pour).** Without a real sample, a guessed field will short GND into other nets. Pour in AD via `Place → Polygon Pour` and let the clearance rules do the work.
- **Do not chase 100% connectivity with a custom router.** A maze router tops out around 70% on dense boards. Route part of it yourself and let `Route → Auto Route → All` finish.

<!-- TODO: add docs/demo.gif — 30s: run sch_add_footprints.py, then open the result in AD -->

## Self-test

```bash
python tests/test_examples.py
```

On a GBK console (the default on Chinese Windows) run `set PYTHONIOENCODING=utf-8` first, otherwise the UTF-8 output is mangled.

Runs all four scripts against the minimal fixtures in `examples/` in a temp directory, then asserts that the batch footprint pass makes the schematic *complete* and that a second run does not insert duplicates.

**Caveat:** the two files in `examples/` are hand-written minimal fixtures used to exercise the parsers. They are not guaranteed to open in AD — for real work, always export your own file with `File → Save As → Advanced Schematic ascii (*.SchDoc)`.

## Supported versions

Tested mainly on **Altium Designer 6.7** (Protel 5.0 format). Record numbers are the common Protel/AD numbering; newer versions are probably compatible but fields may be added or removed. If something breaks, open an issue with the first two lines of the file header.

## Docs

- `references/schdoc-format.md` — schematic record format, index rules, SchLib differences
- `references/pcbdoc-format.md` — PCB record format, footprint geometry, listing footprint names from an IntLib
- `references/pitfalls.md` — six ways to crash AD, and the order to debug them in

## License

MIT
