# Awesome Quantskills data

`awesome-quantskills.json` is the machine-readable public selection generated from the verified Quantskills Registry Shadow snapshot.

## Main fields

- `generated_at`: timestamp inherited from the recommendation snapshot.
- `catalog_snapshot_id`: exact Registry catalog binding.
- `source`: upstream repository, manifest, and SHA-256 provenance.
- `policy`: the complete public selection boundary.
- `items`: enriched selected assets.
- `core`: primary score used for ranking.
- `behavior`, `quality`, `token`: Core score components B/Q/T.
- `featured_*`: supplemental assessment; it does not affect Core.
- `rank` / `group_size`: position inside the same `kind + category` eligible group.
- `source_publication`: immutable evaluation publication supplying the current score.

Use the raw URL with an AI or data tool:

```text
https://raw.githubusercontent.com/quantskills/awesome-quantskills/main/data/awesome-quantskills.json
```

The collection is Shadow-only, does not affect Registry admission, and is not an investment endorsement.
