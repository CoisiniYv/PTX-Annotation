import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP_ROOT = ROOT / "test" / "_tmp"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

from tools import mask_audit


class TestMaskAudit(unittest.TestCase):
    def _touch(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n")

    def test_audit_and_correct(self):
        with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmp:
            root = Path(tmp)
            self._touch(root / "caseA" / "IM0.png")
            self._touch(root / "caseB" / "IMG.dcm.png")

            mapping = {
                "caseA/IM0": 1,
                "caseA/IM1": 1,  # 缺失掩码
                "caseB/IMG.dcm": 0,  # 有掩码但标为 0
                "caseC/IM2": 0,
            }

            report = mask_audit.audit_masks(root, mapping)
            summary = report["summary"]

            self.assertEqual(summary["total_cases"], 4)
            self.assertEqual(summary["label_1_cases"], 2)
            self.assertEqual(summary["label_0_cases"], 2)
            self.assertEqual(summary["actual_has_mask_cases"], 2)
            self.assertEqual(summary["label_1_and_found_mask"], 1)
            self.assertEqual(summary["label_1_but_missing_mask"], 1)
            self.assertEqual(summary["label_0_but_found_mask"], 1)
            self.assertEqual(summary["label_0_and_no_mask"], 1)

            corrected, stats = mask_audit.build_corrected_mapping(
                original_mapping=mapping,
                report=report,
                sync_both_ways=False,
            )
            self.assertEqual(corrected["caseA/IM1"], 0)
            self.assertEqual(corrected["caseA/IM0"], 1)
            self.assertEqual(stats["changed_1_to_0"], 1)

    def test_quarantine_and_restore(self):
        with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmp:
            root = Path(tmp)
            self._touch(root / "caseB" / "IMG.dcm.png")

            mapping = {
                "caseB/IMG.dcm": 0,
            }
            report = mask_audit.audit_masks(root, mapping)

            quarantine_dir = root / "quarantine"
            manifest, errors = mask_audit.quarantine_wrong_zero_masks(
                report,
                root,
                quarantine_dir,
                mode="move",
            )

            self.assertEqual(errors, [])
            self.assertEqual(len(manifest["operations"]), 1)

            original_path = Path(manifest["operations"][0]["src_original"])
            quarantine_path = Path(manifest["operations"][0]["dst_quarantine"])

            self.assertFalse(original_path.exists())
            self.assertTrue(quarantine_path.exists())

            manifest_path = quarantine_dir / "manifest_test.json"
            mask_audit.save_json(manifest, manifest_path)

            restored, restored_items, restore_errors = mask_audit.restore_from_manifest(
                manifest_path,
                overwrite=True,
            )

            self.assertEqual(restore_errors, [])
            self.assertEqual(restored, 1)
            self.assertTrue(original_path.exists())
            self.assertFalse(quarantine_path.exists())


if __name__ == "__main__":
    unittest.main()
