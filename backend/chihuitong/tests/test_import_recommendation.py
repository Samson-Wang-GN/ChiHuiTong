import io
import zipfile
from xml.etree import ElementTree

from django.test import TestCase
from openpyxl import Workbook

from chihuitong.models import Card, Customer, ImportFormat
from chihuitong.errors import BusinessError
from chihuitong.services import files, imports, jobs

from .support import api_client
from .test_sales import sales_setup


class ImportRecommendationTests(TestCase):
    def setUp(self):
        sales_setup(self)

    def inspect(self, headers, rows=None, prefix=0, extra_sheet=False, dimension="original"):
        book = Workbook()
        sheet = book.active
        sheet.title = "客户"
        if extra_sheet:
            sheet.title = "说明"
            sheet.append(["这是合成测试，不含真实客户"])
            sheet = book.create_sheet("客户")
        for _ in range(prefix):
            sheet.append(["测试说明"])
        sheet.append(headers)
        for row in rows or [["合成客户", "13900000101", 2]]:
            sheet.append(row)
        output = io.BytesIO()
        book.save(output)
        data = output.getvalue()
        if dimension != "original":
            rewritten = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(rewritten, "w", zipfile.ZIP_DEFLATED) as target:
                for info in source.infolist():
                    content = source.read(info.filename)
                    if info.filename.startswith("xl/worksheets/") and info.filename.endswith(".xml"):
                        root = ElementTree.fromstring(content)
                        element = root.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}dimension")
                        if element is not None:
                            if dimension is None:
                                root.remove(element)
                            else:
                                element.set("ref", dimension)
                        content = ElementTree.tostring(root)
                    target.writestr(info, content)
            data = rewritten.getvalue()
        asset = files.upload_file(
            self.resource, data=data, filename="自动匹配.xlsx", purpose="sales_excel"
        )
        batch = imports.create_import(self.resource, asset.id)
        jobs.run_one()
        batch.refresh_from_db()
        return batch

    def test_optional_or_incorrect_dimensions_do_not_change_real_data(self):
        for dimension in [None, "A1:A1", "A1:XFD1048576"]:
            with self.subTest(dimension=dimension):
                batch = self.inspect(["客户姓名", "手机号", "数量", "客户编号"],
                    [["合成甲", "13900000101", 2, "001"], ["合成乙", "13900000102", 3, "002"]],
                    dimension=dimension)
                self.assertEqual(batch.sheets, [{"name": "客户", "rows": 3, "columns": 4}])
                suggestion = imports.recommend_import(batch)
                self.assertEqual(suggestion["header_row"], 1)
                response = api_client(self.resource).post(f"/api/v1/imports/{batch.id}/mapping", {
                    "version": batch.version, "sheet": suggestion["sheet"],
                    "header_row": suggestion["header_row"], "mapping": suggestion["mapping"],
                    "quantity_mode": "column",
                }, format="json", HTTP_IDEMPOTENCY_KEY=f"dimension-{batch.id}")
                self.assertEqual(response.status_code, 200, response.content)
                jobs.run_one()
                batch.refresh_from_db()
                self.assertEqual((batch.status, batch.total_rows, batch.total_cards, batch.error_rows),
                                 ("validated", 2, 5, 0))

    def test_legacy_zero_shape_heals_on_next_without_reupload(self):
        batch = self.inspect(["姓名", "手机号", "数量"], dimension=None)
        batch.sheets = [{"name": "客户", "rows": 0, "columns": 0}]
        batch.save(update_fields=["sheets"])
        batch = imports.configure_import(self.resource, batch.id, version=batch.version,
            sheet="客户", header_row=1, mapping={"name": 0, "phone": 1, "quantity": 2}, quantity_mode="column")
        self.assertEqual(batch.sheets[0]["rows"], 2)
        jobs.run_one()
        batch.refresh_from_db()
        self.assertEqual(batch.total_cards, 2)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Card.objects.count(), 0)

    def test_actual_shape_limits_apply_even_without_dimensions(self):
        for content in [b'<worksheet><row r="10021"><c r="A10021"/></row></worksheet>',
                        b'<worksheet><row r="1"><c r="GS1"/></row></worksheet>']:
            with self.assertRaises(BusinessError):
                imports.worksheet_shape(io.BytesIO(content))
        self.assertEqual(imports.worksheet_shape(io.BytesIO(b'<worksheet><sheetData/></worksheet>')),
                         {"rows": 0, "columns": 0})

    def test_sheet_header_twenty_and_ten_raw_rows(self):
        rows = [[f"合成客户{i}", f"13900000{i:03d}", 2] for i in range(12)]
        batch = self.inspect(
            ["客户 姓名：", "ＰＨＯＮＥ＿ＮＵＭＢＥＲ", "购卡张数"], rows, 19, True
        )
        response = api_client(self.resource).get(f"/api/v1/imports/{batch.id}")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        suggestion = result["recommendation"]
        self.assertEqual((suggestion["sheet"], suggestion["header_row"]), ("客户", 20))
        self.assertEqual(suggestion["mapping"], {"name": 0, "phone": 1, "quantity": 2})
        self.assertEqual(len(result["preview"]["客户"][20:]), 10)
        self.assertEqual(result["preview"]["客户"][29], rows[9])
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Card.objects.count(), 0)
        self.assertEqual(api_client(self.other).get(f"/api/v1/imports/{batch.id}").status_code, 404)

    def test_ambiguous_identity_not_guessed_and_quantity_not_defaulted(self):
        batch = self.inspect(["姓名", "手机号", "客户手机号", "业务员手机"])
        result = imports.recommend_import(batch)
        self.assertEqual(result["mapping"], {"name": 0})
        self.assertEqual(result["ambiguous"]["phone"], [1, 2])
        self.assertNotIn("quantity", result["mapping"])
        self.assertNotIn("uniform_quantity", result)

    def test_same_institution_format_reordered_and_conflicts_are_visible(self):
        structure = {
            "headers": ["称呼", "联络号码", "采购张数"],
            "field_headers": {"name": "称呼", "phone": "联络号码", "quantity": "采购张数"},
        }
        ImportFormat.objects.create(
            organization=self.other.organization, name="其他机构格式", structure=structure
        )
        batch = self.inspect(["采购张数", "称呼", "联络号码"], [[2, "合成客户", "13900000101"]])
        self.assertEqual(imports.recommend_import(batch)["mapping"], {})
        ImportFormat.objects.create(
            organization=self.resource.organization, name="本机构格式", structure=structure
        )
        result = imports.recommend_import(batch)
        self.assertEqual(result["mapping"], {"name": 1, "phone": 2, "quantity": 0})
        self.assertTrue(result["saved_format"])
        ImportFormat.objects.create(
            organization=self.resource.organization,
            name="冲突格式",
            structure={
                **structure,
                "field_headers": {"name": "联络号码", "phone": "称呼", "quantity": "采购张数"},
            },
        )
        result = imports.recommend_import(batch)
        self.assertNotIn("phone", result["mapping"])
        self.assertEqual(result["ambiguous"]["phone"], [1, 2])

    def test_no_recognized_headers_and_duplicate_header_remain_manual(self):
        batch = self.inspect(["列一", "列二", "列三"])
        self.assertEqual(imports.recommend_import(batch)["mapping"], {})
        result = imports.suggest_mapping(["姓 名", "手机号码", "手机号码", "开卡数量"])
        self.assertNotIn("phone", result["mapping"])
        self.assertEqual(result["ambiguous"]["phone"], [1, 2])
