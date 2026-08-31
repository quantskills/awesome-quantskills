from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from scripts.sync import expected_outputs
except ModuleNotFoundError:
    from sync import expected_outputs


ROOT = Path(__file__).resolve().parents[1]


def verify_collection(root: Path = ROOT) -> dict:
    path = root / "data" / "awesome-quantskills.json"
    collection = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema", "generated_at", "record_count", "skill_count", "agent_count", "category_count",
        "catalog_snapshot_id", "source", "policy", "items",
    }
    if set(collection) != required:
        raise ValueError("collection root fields are not closed")
    if collection["schema"] != "awesome-quantskills.collection.v1":
        raise ValueError("unsupported collection schema")
    if collection["record_count"] != len(collection["items"]):
        raise ValueError("collection count mismatch")
    ids = [item.get("asset_id") for item in collection["items"]]
    if None in ids or len(set(ids)) != len(ids):
        raise ValueError("duplicate or invalid collection asset id")
    if collection["skill_count"] != sum(item["kind"] == "skill" for item in collection["items"]):
        raise ValueError("skill count mismatch")
    if collection["agent_count"] != sum(item["kind"] == "agent" for item in collection["items"]):
        raise ValueError("agent count mismatch")
    if collection["category_count"] != len({item["category"] for item in collection["items"]}):
        raise ValueError("category count mismatch")
    if collection["policy"].get("status") != "shadow" or collection["policy"].get("affects_registry") is not False:
        raise ValueError("collection is not Shadow-only")
    if collection["policy"].get("endorsement") is not False:
        raise ValueError("collection endorsement boundary is missing")
    for item in collection["items"]:
        if item["security_status"] not in {"pass", "pass_with_warning"}:
            raise ValueError(f"ineligible security status: {item['asset_id']}")
        if item["reliability"] != 100:
            raise ValueError(f"ineligible reliability: {item['asset_id']}")
        if not item["url"].startswith("https://github.com/quantskills/"):
            raise ValueError(f"unexpected repository URL: {item['asset_id']}")

    outputs = expected_outputs(collection)
    for relative, expected in outputs.items():
        if relative == Path("data/awesome-quantskills.json"):
            continue
        if (root / relative).read_bytes() != expected:
            raise ValueError(f"generated file is stale: {relative.as_posix()}")
    return {"ok": True, "records": collection["record_count"], "snapshot": collection["catalog_snapshot_id"]}


if __name__ == "__main__":
    try:
        print(json.dumps(verify_collection(), ensure_ascii=False, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
