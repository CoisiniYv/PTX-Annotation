import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP_ROOT = ROOT / "test" / "_tmp"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

from tools import pa_filter

try:
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid, PYDICOM_IMPLEMENTATION_UID
    PYDICOM_AVAILABLE = True
except Exception:
    PYDICOM_AVAILABLE = False


@unittest.skipUnless(PYDICOM_AVAILABLE, "pydicom 未安装，跳过 PA 筛选测试")
class TestPAFilter(unittest.TestCase):
    def _make_dicom(
        self,
        path: Path,
        view_position: str | None = None,
        protocol: str | None = None,
        series: str | None = None,
        study: str | None = None,
        comments: str | None = None,
    ):
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = generate_uid()
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

        ds = FileDataset(
            str(path),
            {},
            file_meta=file_meta,
            preamble=b"\0" * 128,
        )
        ds.is_little_endian = True
        ds.is_implicit_VR = False
        ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        ds.PatientName = "Test^Patient"
        ds.Rows = 1
        ds.Columns = 1
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 0
        ds.PixelData = b"\x00\x00"

        if view_position:
            ds.ViewPosition = view_position
        if protocol:
            ds.ProtocolName = protocol
        if series:
            ds.SeriesDescription = series
        if study:
            ds.StudyDescription = study
        if comments:
            ds.ImageComments = comments

        ds.save_as(path)

    def test_is_pa_view_basic(self):
        self.assertTrue(pa_filter.is_pa_view("PA"))
        self.assertTrue(pa_filter.is_pa_view("CHEST PA"))
        self.assertFalse(pa_filter.is_pa_view("AP"))
        self.assertFalse(pa_filter.is_pa_view("LAT"))

    def test_filter_pa_views(self):
        with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmp:
            root = Path(tmp)
            pa_path = root / "case1" / "pa1.dcm"
            ap_path = root / "case1" / "ap1.dcm"
            proto_path = root / "case2" / "proto_pa.dcm"
            noext_path = root / "case2" / "noext"

            pa_path.parent.mkdir(parents=True, exist_ok=True)
            proto_path.parent.mkdir(parents=True, exist_ok=True)

            self._make_dicom(pa_path, view_position="PA")
            self._make_dicom(ap_path, view_position="AP")
            self._make_dicom(proto_path, protocol="CHEST PA")
            self._make_dicom(noext_path, series="CHEST PA")

            dicom_files = pa_filter.scan_dicom_files(root)
            self.assertEqual(len(dicom_files), 4)

            pa_files, all_files_info = pa_filter.filter_pa_views(dicom_files)
            pa_names = {p.name for p in pa_files}

            self.assertIn("pa1.dcm", pa_names)
            self.assertIn("proto_pa.dcm", pa_names)
            self.assertIn("noext", pa_names)
            self.assertNotIn("ap1.dcm", pa_names)

            report_path = root / "report.txt"
            pa_filter.generate_report(all_files_info, pa_files, report_path, root)
            content = report_path.read_text(encoding="utf-8")
            self.assertIn("[PA]", content)

    def test_copy_and_move(self):
        with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmp:
            root = Path(tmp)
            source = root / "src"
            target = root / "dst"
            excluded = root / "excluded"
            source.mkdir()

            pa_file = source / "case" / "pa.dcm"
            other_file = source / "case" / "ap.dcm"
            pa_file.parent.mkdir(parents=True, exist_ok=True)
            self._make_dicom(pa_file, view_position="PA")
            self._make_dicom(other_file, view_position="AP")

            pa_filter.copy_pa_files([pa_file], source, target)
            copied = target / "case" / "pa.dcm"
            self.assertTrue(copied.exists())

            pa_filter.move_files_preserving_structure([other_file], source, excluded)
            moved = excluded / "case" / "ap.dcm"
            self.assertTrue(moved.exists())
            self.assertFalse(other_file.exists())


if __name__ == "__main__":
    unittest.main()
