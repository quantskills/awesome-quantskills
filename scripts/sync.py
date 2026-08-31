from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import quote


REGISTRY_REPOSITORY = "https://github.com/quantskills/registry"
SOURCE_BASE = "https://raw.githubusercontent.com/quantskills/registry/main/evaluations"
CATALOG_URL = "https://raw.githubusercontent.com/quantskills/registry/main/catalog.snapshot.json"
SOURCE_FILES = (
    "current-scores.json",
    "recommended.snapshot.json",
    "selection-policy.v1.json",
)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "awesome-quantskills-sync/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def parse_json(content: bytes, name: str) -> dict:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON source: {name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"source must be a JSON object: {name}")
    return value


def verify_source_bundle(
    manifest: dict,
    files: dict[str, bytes],
    current: dict,
    recommended: dict,
    policy: dict,
    catalog: dict,
) -> None:
    for name in SOURCE_FILES:
        expected = manifest.get("files", {}).get(name)
        if expected != sha256_bytes(files[name]):
            raise ValueError(f"source digest mismatch: {name}")

    unsigned_manifest = {key: value for key, value in manifest.items() if key != "snapshot_digest"}
    if manifest.get("snapshot_digest") != sha256_bytes(canonical_bytes(unsigned_manifest)):
        raise ValueError("source manifest digest mismatch")

    unsigned_policy = {key: value for key, value in policy.items() if key != "policy_digest"}
    if policy.get("policy_digest") != sha256_bytes(canonical_bytes(unsigned_policy)):
        raise ValueError("selection policy digest mismatch")

    snapshot_ids = {
        manifest.get("catalog_snapshot_id"),
        current.get("catalog_snapshot_id"),
        recommended.get("catalog_snapshot_id"),
        catalog.get("snapshot_id"),
    }
    if len(snapshot_ids) != 1 or None in snapshot_ids:
        raise ValueError("catalog snapshot mismatch")
    if recommended.get("score_dataset_sha256") != sha256_bytes(files["current-scores.json"]):
        raise ValueError("recommendation/score dataset mismatch")
    if recommended.get("policy_id") != policy.get("policy_id"):
        raise ValueError("recommendation/policy id mismatch")
    if recommended.get("policy_digest") != policy.get("policy_digest"):
        raise ValueError("recommendation/policy digest mismatch")

    expected_policy = {
        "status": "shadow",
        "selection": "top_25_percent_by_core",
        "minimum_reliability": 100,
        "requires_active_registry_listing": True,
        "exclude_material_core_regression": True,
        "affects_registry": False,
        "endorsement": False,
    }
    for key, expected in expected_policy.items():
        if policy.get(key) != expected:
            raise ValueError(f"unsupported selection policy: {key}")
    if policy.get("grouping") != ["kind", "category"]:
        raise ValueError("unsupported selection grouping")

    score_records = current.get("records", [])
    selected_records = recommended.get("records", [])
    if current.get("record_count") != len(score_records):
        raise ValueError("current score count mismatch")
    if recommended.get("record_count") != len(selected_records):
        raise ValueError("recommended score count mismatch")

    scores = {row.get("asset_id"): row for row in score_records}
    assets = {row.get("name"): row for row in catalog.get("assets", [])}
    if None in scores or len(scores) != len(score_records):
        raise ValueError("duplicate or invalid score asset id")
    selected_ids = [row.get("asset_id") for row in selected_records]
    if None in selected_ids or len(set(selected_ids)) != len(selected_ids):
        raise ValueError("duplicate or invalid recommended asset id")

    for selected in selected_records:
        asset_id = selected["asset_id"]
        score = scores.get(asset_id)
        asset = assets.get(asset_id)
        if score is None or asset is None:
            raise ValueError(f"recommended asset missing from source: {asset_id}")
        if selected.get("score_record_sha256") != sha256_bytes(canonical_bytes(score)):
            raise ValueError(f"recommended score record mismatch: {asset_id}")
        if selected.get("core") != score.get("scores", {}).get("total"):
            raise ValueError(f"recommended Core mismatch: {asset_id}")
        if selected.get("source_publication") != score.get("source_publication"):
            raise ValueError(f"recommended publication mismatch: {asset_id}")
        if selected.get("kind") != score.get("kind") or selected.get("category") != score.get("category"):
            raise ValueError(f"recommended group mismatch: {asset_id}")


def build_collection(manifest: dict, current: dict, recommended: dict, policy: dict, catalog: dict) -> dict:
    scores = {row["asset_id"]: row for row in current["records"]}
    assets = {row["name"]: row for row in catalog["assets"]}
    categories = catalog["taxonomy"]["categories"]
    items = []
    for selected in recommended["records"]:
        score = scores[selected["asset_id"]]
        asset = assets[selected["asset_id"]]
        category = categories[selected["category"]]
        items.append({
            "asset_id": selected["asset_id"],
            "url": asset["url"],
            "kind": selected["kind"],
            "category": selected["category"],
            "category_zh": category["label_zh"],
            "category_en": category["label_en"],
            "subcategory": asset.get("subcategory"),
            "summary_zh": asset.get("summary_zh") or asset.get("description") or "",
            "summary_en": asset.get("summary_en") or asset.get("description") or "",
            "core": score["scores"]["total"],
            "behavior": score["scores"]["behavior"],
            "quality": score["scores"]["quality"],
            "token": score["scores"]["token"],
            "featured_status": score["featured"]["status"],
            "featured_score": score["featured"].get("score"),
            "featured_reason": score["featured"].get("reason"),
            "security_status": score["security"]["status"],
            "reliability": score["metrics"]["reliability"],
            "rank": selected["rank"],
            "group": selected["group"],
            "group_size": selected["group_size"],
            "source_publication": selected["source_publication"],
            "score_record_sha256": selected["score_record_sha256"],
        })
    items.sort(key=lambda row: (row["category"], row["kind"], row["rank"], row["asset_id"]))
    counts = Counter(row["kind"] for row in items)
    category_ids = sorted({row["category"] for row in items})
    return {
        "schema": "awesome-quantskills.collection.v1",
        "generated_at": recommended["generated_at"],
        "record_count": len(items),
        "skill_count": counts["skill"],
        "agent_count": counts["agent"],
        "category_count": len(category_ids),
        "catalog_snapshot_id": catalog["snapshot_id"],
        "source": {
            "repository": REGISTRY_REPOSITORY,
            "evaluation_manifest": f"{REGISTRY_REPOSITORY}/blob/main/evaluations/manifest.json",
            "recommendation_snapshot": f"{REGISTRY_REPOSITORY}/blob/main/evaluations/recommended.snapshot.json",
            "score_dataset_sha256": recommended["score_dataset_sha256"],
            "public_evaluation_snapshot_digest": manifest["snapshot_digest"],
        },
        "policy": {
            "policy_id": policy["policy_id"],
            "policy_digest": policy["policy_digest"],
            "status": policy["status"],
            "grouping": policy["grouping"],
            "selection": policy["selection"],
            "minimum_reliability": policy["minimum_reliability"],
            "requires_active_registry_listing": policy["requires_active_registry_listing"],
            "exclude_material_core_regression": policy["exclude_material_core_regression"],
            "affects_registry": policy["affects_registry"],
            "endorsement": policy["endorsement"],
        },
        "items": items,
    }


def short_summary(value: str, limit: int = 150) -> str:
    value = " ".join(value.replace("|", "\\|").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def badge(label: str, value: str, color: str) -> str:
    def segment(text: str) -> str:
        return quote(text.replace("_", "__").replace("-", "--"), safe="")

    return f'<img alt="{label}: {value}" src="https://img.shields.io/badge/{segment(label)}-{segment(value)}-{color}">'


def render_category(item_group: list[dict], language: str) -> str:
    first = item_group[0]
    title = first["category_zh"] if language == "zh" else first["category_en"]
    if language == "zh":
        header = "项目 | 类型 | Core | B / Q / T | 组内排名 | 简介"
        divider = "--- | --- | ---: | --- | ---: | ---"
    else:
        header = "Project | Type | Core | B / Q / T | Group rank | Summary"
        divider = "--- | --- | ---: | --- | ---: | ---"
    lines = [f'<a id="category-{first["category"]}"></a>', "", f"### {first['category']} · {title}", "", header, divider]
    for item in item_group:
        summary = short_summary(item["summary_zh"] if language == "zh" else item["summary_en"])
        kind = "Agent" if item["kind"] == "agent" else "Skill"
        lines.append(
            f'[{item["asset_id"]}]({item["url"]}) | {kind} | **{item["core"]:.2f}** | '
            f'{item["behavior"]:.2f} / {item["quality"]:.2f} / {item["token"]:.2f} | '
            f'{item["rank"]}/{item["group_size"]} | {summary}'
        )
    return "\n".join(lines)


def render_readme(collection: dict, language: str = "zh") -> str:
    zh = language == "zh"
    items = collection["items"]
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(item["category"], []).append(item)
    nav = "\n".join(
        f'- [{category} {group[0]["category_zh" if zh else "category_en"]}](#category-{category})'
        f' · {len(group)} {"项" if zh else ("item" if len(group) == 1 else "items")}'
        for category, group in groups.items()
    )
    title = "由可验证 Shadow 评分自动生成的量化 Skill 与 Agent 精选" if zh else "A verified Shadow-scored selection of quantitative Skills and Agents"
    language_link = '<a href="README.en.md">English</a>' if zh else '<a href="README.md">中文</a>'
    important = (
        "本库是研究用途的 **Shadow 精选视图**。它不改变 Registry 准入状态，不代表官方认证，也不构成投资建议。"
        if zh else
        "This repository is a research-only **Shadow selection view**. It does not change Registry admission, imply certification, or constitute investment advice."
    )
    facts = (
        f"**{collection['record_count']}** 项精选 · **{collection['skill_count']}** Skills · "
        f"**{collection['agent_count']}** Agents · **{collection['category_count']}** 个分类"
        if zh else
        f"**{collection['record_count']}** selected · **{collection['skill_count']}** Skills · "
        f"**{collection['agent_count']}** Agents · **{collection['category_count']}** categories"
    )
    date = collection["generated_at"][:10]
    badges = " ".join((
        '<img alt="Awesome" src="https://awesome.re/badge-flat.svg">',
        badge("selected", str(collection["record_count"]), "0f766e"),
        badge("policy", "category top 25%", "2563eb"),
        badge("mode", "Shadow", "64748b"),
        badge("updated", date, "334155"),
    ))
    category_sections = "\n\n".join(render_category(group, language) for group in groups.values())
    if zh:
        body = f"""<h1 align="center">Awesome Quantskills</h1>

<p align="center"><strong>{title}</strong></p>

<p align="center">{badges}</p>

<p align="center">{language_link} · <a href="https://www.quantskills.ai/">Quantskills 官网</a> · <a href="https://github.com/quantskills/registry">完整 Registry</a> · <a href="data/awesome-quantskills.json">AI 数据</a></p>

> [!IMPORTANT]
> {important}

{facts}。当前快照：`{collection['catalog_snapshot_id']}`。

## 快速导航

{nav}

## 怎么进入精选

```mermaid
flowchart LR
  A[进入有效 Registry] --> B[完成签名 Shadow 评分]
  B --> C{{Security pass 或 pass_with_warning}}
  C --> D{{Reliability = 100}}
  D --> E{{无材料性 Core 回归}}
  E --> F[按 Skill/Agent + 一级分类分组]
  F --> G[Core 排名前 25%]
  G --> H[进入 Shadow 精选]
```

- 排名使用 **Core**，不是 Featured；同分按 `asset_id` 排序。
- 每组取 `ceil(合格数量 × 25%)`，最少 1 项。
- Featured 为 N/A 不会自动淘汰；存在材料性 Core 回归才会被门禁排除。
- 精选随评分和 Registry 快照重新计算，项目可能进入或退出。

## 精选目录

**评分速读**

- `Core = 50% B + 25% Q + 25% T`，满分 100，越高越好。
- `B` 是行为表现，`Q` 是产出质量，`T` 是 Token 效率。
- “组内排名”只在同类型、同一级分类内比较；不同分类不直接横向排名。

{category_sections}

## 给 AI 使用

机器可读精选数据：[`data/awesome-quantskills.json`](data/awesome-quantskills.json)

```text
请读取 https://raw.githubusercontent.com/quantskills/awesome-quantskills/main/data/awesome-quantskills.json
按 category 分组分析精选项目。以 core 为主评分，behavior/quality/token 为分项；
Featured 只作附加评价。说明组内排名、来源 publication 和 Shadow 限制，不作投资建议。
```

## 数据来源与完整性

- 权威来源：[`quantskills/registry/evaluations`](https://github.com/quantskills/registry/tree/main/evaluations)
- 精选策略：`{collection['policy']['policy_id']}`
- 公开评分快照摘要：`{collection['source']['public_evaluation_snapshot_digest']}`
- 精选策略摘要：`{collection['policy']['policy_digest']}`
- 本仓库只保存公开脱敏字段，不保存凭据、完整签名信封、模型轨迹或详细安全发现。

自动同步会先验证 manifest、文件 SHA-256、评分数据绑定、策略摘要和 catalog snapshot；任一不一致都会停止生成。

## 贡献

不能通过直接编辑本 README 进入精选。请先让项目进入 [Quantskills Registry](https://github.com/quantskills/registry)，完成当前 Shadow 评分并满足同组前 25% 条件。流程详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可

本仓库的整理、脚本和展示采用 [MIT License](LICENSE)。各项目仍遵循其各自仓库中的许可证。
"""
    else:
        body = f"""<h1 align="center">Awesome Quantskills</h1>

<p align="center"><strong>{title}</strong></p>

<p align="center">{badges}</p>

<p align="center">{language_link} · <a href="https://www.quantskills.ai/">Quantskills website</a> · <a href="https://github.com/quantskills/registry">Full Registry</a> · <a href="data/awesome-quantskills.json">AI data</a></p>

> [!IMPORTANT]
> {important}

{facts}. Current snapshot: `{collection['catalog_snapshot_id']}`.

## Quick navigation

{nav}

## How selection works

```mermaid
flowchart LR
  A[Active Registry listing] --> B[Signed Shadow evaluation]
  B --> C{{Security pass or pass_with_warning}}
  C --> D{{Reliability = 100}}
  D --> E{{No material Core regression}}
  E --> F[Group by Skill/Agent + category]
  F --> G[Top 25% by Core]
  G --> H[Shadow selection]
```

- Ranking uses **Core**, not Featured; ties are resolved by `asset_id`.
- Each group selects `ceil(eligible count × 25%)`, with a minimum of one.
- Featured N/A does not automatically exclude an item; a material Core regression does.
- The collection is recalculated with new scores and Registry snapshots, so entries may move in or out.

## Selected projects

**Score guide**

- `Core = 50% B + 25% Q + 25% T`, on a 0–100 scale where higher is better.
- `B` is behavior, `Q` is output quality, and `T` is token efficiency.
- Group rank compares only projects of the same type and top-level category; ranks are not directly comparable across categories.

{category_sections}

## Use with AI

Machine-readable collection: [`data/awesome-quantskills.json`](data/awesome-quantskills.json)

```text
Read https://raw.githubusercontent.com/quantskills/awesome-quantskills/main/data/awesome-quantskills.json
and analyze the selected projects by category. Treat core as the primary score and
behavior/quality/token as components. Treat Featured as supplemental. Explain group rank,
source publication, and Shadow limitations. Do not provide investment advice.
```

## Provenance and integrity

- Authoritative source: [`quantskills/registry/evaluations`](https://github.com/quantskills/registry/tree/main/evaluations)
- Selection policy: `{collection['policy']['policy_id']}`
- Public evaluation snapshot digest: `{collection['source']['public_evaluation_snapshot_digest']}`
- Selection policy digest: `{collection['policy']['policy_digest']}`
- This repository stores only public redacted fields, never credentials, full signed envelopes, model traces, or detailed security findings.

Automated sync verifies the manifest, file SHA-256 values, score dataset binding, policy digest, and catalog snapshot before generating any output.

## Contributing

Direct README edits cannot add a project. A project must first enter the [Quantskills Registry](https://github.com/quantskills/registry), complete the current Shadow evaluation, and rank in its group's top quartile. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

The curation, scripts, and presentation in this repository use the [MIT License](LICENSE). Each listed project retains its own repository license.
"""
    return body.rstrip() + "\n"


def load_sources(source_base: str, catalog_url: str) -> tuple[dict, dict[str, bytes], dict, dict, dict, dict]:
    manifest_bytes = fetch(f"{source_base}/manifest.json")
    files = {name: fetch(f"{source_base}/{name}") for name in SOURCE_FILES}
    manifest = parse_json(manifest_bytes, "manifest.json")
    current = parse_json(files["current-scores.json"], "current-scores.json")
    recommended = parse_json(files["recommended.snapshot.json"], "recommended.snapshot.json")
    policy = parse_json(files["selection-policy.v1.json"], "selection-policy.v1.json")
    catalog = parse_json(fetch(catalog_url), "catalog.snapshot.json")
    return manifest, files, current, recommended, policy, catalog


def expected_outputs(collection: dict) -> dict[Path, bytes]:
    return {
        Path("data/awesome-quantskills.json"): json_bytes(collection),
        Path("README.md"): render_readme(collection, "zh").encode("utf-8"),
        Path("README.en.md"): render_readme(collection, "en").encode("utf-8"),
    }


def apply_outputs(root: Path, outputs: dict[Path, bytes], check: bool) -> bool:
    changed = []
    for relative, content in outputs.items():
        path = root / relative
        if not path.exists() or path.read_bytes() != content:
            changed.append(relative.as_posix())
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
    if check and changed:
        print(json.dumps({"ok": False, "stale": changed}, ensure_ascii=False))
        return False
    print(json.dumps({"ok": True, "changed": changed}, ensure_ascii=False))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync the verified Quantskills Shadow selection.")
    parser.add_argument("--source-base", default=SOURCE_BASE)
    parser.add_argument("--catalog-url", default=CATALOG_URL)
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    manifest, files, current, recommended, policy, catalog = load_sources(args.source_base, args.catalog_url)
    verify_source_bundle(manifest, files, current, recommended, policy, catalog)
    collection = build_collection(manifest, current, recommended, policy, catalog)
    return 0 if apply_outputs(args.output_root, expected_outputs(collection), args.check) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
