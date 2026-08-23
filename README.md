# GeoSAME

> **Status:** Manuscript under review · Public research preview · 2026-08-24

**GeoSAME** is an audit-first framework for generating semantically faithful rewrites of fixed-diagram geometry problems. It combines controlled candidate construction, text-grounded parsing, typed consistency checks, and one bounded corrective path.

<p align="center">
  <img src="assets/overview.png" alt="GeoSAME system overview" width="100%">
</p>

## What this repository provides

This public preview is intentionally small. It is designed so that readers can:

1. understand the paper's main method and evaluation boundary;
2. run an offline minimal example without an API key or benchmark download;
3. recompute the principal aggregate metrics reported by the manuscript.

The repository does **not** include third-party benchmark questions or images, raw model responses, private review material, annotator identities, or internal experiment archives.

## Method at a glance

GeoSAME treats rewriting as a constrained, auditable pipeline rather than unconstrained paraphrasing:

1. **Generate** — construct a candidate using a method-specific prompt and explicit preservation constraints.
2. **Parse** — extract comparable text-grounded evidence from the source and candidate.
3. **Verify** — check objects/relations, numbers and units, target, terminology, answer consistency, output quality, and within-item diversity.
4. **Revise / decide** — accept a passing candidate, perform at most one typed corrective revision, or terminate with rejection/safe abstention.
5. **Audit separately** — teacher review and stress-test evaluation are kept separate from the runtime gate; denominators are reported explicitly.

See [`docs/METHOD.md`](docs/METHOD.md) for the method boundary and [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for what the released checks do not establish.

> **Compatibility note:** the Python package keeps its historical import name, `geosynq`, so frozen experiment artifacts and earlier scripts remain interpretable. The public project and manuscript name is **GeoSAME**.

## Installation

GeoSAME's released deterministic core uses only the Python standard library.

```bash
git clone https://github.com/E8A281E6ACA2/GeoSAME.git
cd GeoSAME
python -m venv .venv
```

Activate the environment and install the package:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

python -m pip install -e .
```

Python 3.10 or later is required.

## Quick start: offline minimal example

```bash
python examples/minimal_example.py
```

The example compares a source geometry problem with one synthetic rewrite and prints a typed verification report. No external model, dataset, image, or credential is used.

Expected top-level result:

```json
{
  "passed": true
}
```

The full output also exposes every component check and diagnostic note.
