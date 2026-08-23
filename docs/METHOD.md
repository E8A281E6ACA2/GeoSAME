# Method

## Research problem

GeoSAME rewrites the text of a geometry problem while keeping its fixed diagram and intended solution semantics unchanged. The central risk is that a fluent paraphrase can silently alter an object, relation, number, unit, target, or answer.

## Audit-first pipeline

### 1. Controlled generation

A candidate is constructed under explicit preservation constraints. The released prompt templates show the main rewrite families, while the offline example uses a hand-authored synthetic candidate so it can run without an external service.

### 2. Comparable evidence extraction

The source and candidate are represented through the same text-grounded evidence schema. The released implementation includes lightweight target, numeric, point, terminology, answer, and predicate-vocabulary handling. The parser modules expose the interface used for optional model-assisted predicate extraction.

### 3. Typed verification

Checks are returned independently instead of being collapsed into an unexplained score. A caller can therefore distinguish hard inconsistencies, unavailable checks, and softer risks. The public minimal example requires:

- predicate vocabulary consistency;
- no newly introduced point labels;
- numeric multiset consistency;
- target consistency;
- preservation of detected geometry terms;
- answer consistency.

The broader research protocol also evaluated output quality, semantic-boundary risks, and within-item diversity.

### 4. Bounded revision and terminal decision

A failed candidate can receive typed feedback and one bounded corrective attempt. The protocol does not use an unbounded self-revision loop. It terminates as accepted, rejected, or—under narrow conditions—safe abstention.

## Evaluation boundary

Runtime gates and post-hoc teacher evaluation are separate layers. Human semantic labels do not retroactively become runtime inputs. Main-study, rejection-diagnostic, challenge, and external-replication denominators remain separate.

The Challenge60 values in this repository describe deterministic text-only available checks. They must not be presented as performance of the full model-assisted verifier.

## Implementation naming

The public research name is GeoSAME. The import package remains `geosynq` for backward compatibility with frozen experiment identifiers and historical scripts.
