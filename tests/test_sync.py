import hashlib
import json
import unittest

from scripts.sync import build_collection, canonical_bytes, render_readme, verify_source_bundle


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.score = {
            "asset_id": "skill-example",
            "kind": "skill",
            "category": "03",
            "source_publication": "publication.v12.13",
            "scores": {"behavior": 90.0, "quality": 80.0, "token": 70.0, "total": 82.0},
            "featured": {"status": "eligible", "score": 88.0, "reason": None},
            "security": {"status": "pass"},
            "metrics": {"reliability": 100.0},
        }
        self.current = {
            "catalog_snapshot_id": "sha256:catalog",
            "record_count": 1,
            "records": [self.score],
        }
        self.policy = {
            "policy_id": "shadow-category-quartile.v1",
            "status": "shadow",
            "grouping": ["kind", "category"],
            "selection": "top_25_percent_by_core",
            "minimum_reliability": 100,
            "requires_active_registry_listing": True,
            "exclude_material_core_regression": True,
            "affects_registry": False,
            "endorsement": False,
        }
        self.policy["policy_digest"] = hashlib.sha256(canonical_bytes(self.policy)).hexdigest()
        self.recommended = {
            "catalog_snapshot_id": "sha256:catalog",
            "generated_at": "2026-08-31T14:05:07+08:00",
            "policy_id": self.policy["policy_id"],
            "policy_digest": self.policy["policy_digest"],
            "record_count": 1,
            "score_dataset_sha256": hashlib.sha256(encoded(self.current)).hexdigest(),
            "records": [{
                "asset_id": "skill-example",
                "kind": "skill",
                "category": "03",
                "group": "skill:03",
                "group_size": 4,
                "rank": 1,
                "core": 82.0,
                "source_publication": "publication.v12.13",
                "score_record_sha256": hashlib.sha256(canonical_bytes(self.score)).hexdigest(),
            }],
        }
        self.catalog = {
            "snapshot_id": "sha256:catalog",
            "taxonomy": {"categories": {"03": {"label_zh": "市场与标的分析", "label_en": "Market & Instrument Analysis"}}},
            "assets": [{
                "name": "skill-example",
                "url": "https://github.com/quantskills/skill-example",
                "summary_zh": "示例量化研究工具。",
                "summary_en": "Example quantitative research tool.",
                "subcategory": "03.a-share-equity",
            }],
        }
        files = {
            "current-scores.json": encoded(self.current),
            "recommended.snapshot.json": encoded(self.recommended),
            "selection-policy.v1.json": encoded(self.policy),
        }
        self.manifest = {
            "catalog_snapshot_id": "sha256:catalog",
            "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
        }
        unsigned = dict(self.manifest)
        self.manifest["snapshot_digest"] = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
        self.files = files

    def test_verifies_and_builds_enriched_collection(self):
        verify_source_bundle(self.manifest, self.files, self.current, self.recommended, self.policy, self.catalog)
        collection = build_collection(self.manifest, self.current, self.recommended, self.policy, self.catalog)
        self.assertEqual(collection["record_count"], 1)
        self.assertEqual(collection["items"][0]["core"], 82.0)
        self.assertEqual(collection["items"][0]["summary_zh"], "示例量化研究工具。")
        self.assertFalse(collection["policy"]["affects_registry"])

    def test_rejects_tampered_score_bytes(self):
        self.files["current-scores.json"] += b" "
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            verify_source_bundle(self.manifest, self.files, self.current, self.recommended, self.policy, self.catalog)

    def test_readme_explains_shadow_status_and_renders_asset(self):
        collection = build_collection(self.manifest, self.current, self.recommended, self.policy, self.catalog)
        readme = render_readme(collection, language="zh")
        self.assertIn("skill-example", readme)
        self.assertIn("Shadow", readme)
        self.assertIn("不构成投资建议", readme)
        self.assertIn("前 25%", readme)


if __name__ == "__main__":
    unittest.main()
