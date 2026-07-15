import unittest
import uuid
from decimal import Decimal

from bson.decimal128 import Decimal128

from core.auth import db
from services.school_data_engine import (
    build_entity_filter,
    school_data_engine,
    validate_filter_condition,
)
from services.school_data_registry import get_entity_spec


class TestSchoolDataRegistryValidation(unittest.TestCase):
    def test_rejects_unknown_entity(self):
        with self.assertRaises(ValueError):
            get_entity_spec("unknown_table")

    def test_rejects_invalid_field(self):
        spec = get_entity_spec("student")
        with self.assertRaises(ValueError):
            validate_filter_condition(spec, {"field": "password_hash", "op": "$eq", "value": "x"})

    def test_rejects_invalid_operator(self):
        spec = get_entity_spec("student")
        with self.assertRaises(ValueError):
            validate_filter_condition(spec, {"field": "student_name", "op": "$where", "value": "1==1"})

    def test_injects_tenant_id(self):
        spec = get_entity_spec("student")
        result = build_entity_filter(
            spec,
            [{"field": "student_name", "op": "$regex", "value": "Ansh"}],
            "tenant_abc",
        )
        self.assertIn("$and", result)
        self.assertIn({"tenant_id": "tenant_abc"}, result["$and"])

    def test_rejects_tenant_id_as_user_filter(self):
        spec = get_entity_spec("student")
        with self.assertRaises(ValueError):
            build_entity_filter(
                spec,
                [{"field": "tenant_id", "op": "$eq", "value": "other_tenant"}],
                "tenant_abc",
            )


class TestSchoolDataEngineReports(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncio
        from core.auth import client

        client.get_io_loop = asyncio.get_running_loop
        self.tenant_id = f"engine_tenant_{uuid.uuid4()}"
        self.other_tenant_id = f"engine_other_{uuid.uuid4()}"

        await db.school_students.insert_many([
            {
                "student_id": 1,
                "admission_no": "ADM001",
                "student_name": "Ansh Sharma",
                "father_name": "Father Sharma",
                "mother_name": "Mother Sharma",
                "gender": "Male",
                "blood_group": "O+",
                "category": "General",
                "address": "A",
                "class_id": 10,
                "section_id": 20,
                "school_id": 1,
                "tenant_id": self.tenant_id,
            },
            {
                "student_id": 2,
                "admission_no": "ADM002",
                "student_name": "Aryan Nagar",
                "father_name": "Father Nagar",
                "mother_name": "Mother Nagar",
                "gender": "Male",
                "blood_group": "A+",
                "category": "General",
                "address": "B",
                "class_id": 10,
                "section_id": 21,
                "school_id": 1,
                "tenant_id": self.tenant_id,
            },
            {
                "student_id": 1,
                "admission_no": "OTHER001",
                "student_name": "Other Tenant Student",
                "father_name": "Other Father",
                "mother_name": "Other Mother",
                "gender": "Male",
                "blood_group": "B+",
                "category": "General",
                "address": "C",
                "class_id": 10,
                "section_id": 20,
                "school_id": 1,
                "tenant_id": self.other_tenant_id,
            },
        ])
        await db.school_applied_fees.insert_many([
            {
                "applied_fee_id": 100,
                "student_id": 1,
                "fee_head": "Tuition Fee",
                "amount": Decimal128("5000.00"),
                "concession": Decimal128("500.00"),
                "status": "Pending",
                "due_date": "2026-08-01",
                "school_id": 1,
                "tenant_id": self.tenant_id,
            },
            {
                "applied_fee_id": 101,
                "student_id": 1,
                "fee_head": "Exam Fee",
                "amount": Decimal128("1000.00"),
                "concession": Decimal128("0.00"),
                "status": "Partial",
                "due_date": "2026-08-02",
                "school_id": 1,
                "tenant_id": self.tenant_id,
            },
            {
                "applied_fee_id": 102,
                "student_id": 2,
                "fee_head": "Transport Fee",
                "amount": Decimal128("2500.00"),
                "concession": Decimal128("0.00"),
                "status": "Pending",
                "due_date": "2026-08-03",
                "school_id": 1,
                "tenant_id": self.tenant_id,
            },
            {
                "applied_fee_id": 103,
                "student_id": 2,
                "fee_head": "Tuition Fee",
                "amount": Decimal128("7000.00"),
                "concession": Decimal128("0.00"),
                "status": "Paid",
                "due_date": "2026-08-04",
                "school_id": 1,
                "tenant_id": self.tenant_id,
            },
            {
                "applied_fee_id": 900,
                "student_id": 1,
                "fee_head": "Tuition Fee",
                "amount": Decimal128("9999.00"),
                "concession": Decimal128("0.00"),
                "status": "Pending",
                "due_date": "2026-08-01",
                "school_id": 1,
                "tenant_id": self.other_tenant_id,
            },
        ])
        await db.school_payments.insert_one({
            "payment_id": 500,
            "student_id": 1,
            "applied_fee_id": 101,
            "paid_amount": Decimal128("400.00"),
            "balance": Decimal128("600.00"),
            "payment_date": "2026-08-02",
            "payment_mode": "UPI",
            "receipt_no": "REC500",
            "school_id": 1,
            "tenant_id": self.tenant_id,
        })

    async def asyncTearDown(self):
        await db.school_students.delete_many({"tenant_id": {"$in": [self.tenant_id, self.other_tenant_id]}})
        await db.school_applied_fees.delete_many({"tenant_id": {"$in": [self.tenant_id, self.other_tenant_id]}})
        await db.school_payments.delete_many({"tenant_id": {"$in": [self.tenant_id, self.other_tenant_id]}})

    async def test_due_report_total_matches_rows(self):
        result = await school_data_engine.get_report(
            tenant_id=self.tenant_id,
            report_id="due_fees_by_student",
            filters={"statuses": ["Pending", "Partial"]},
        )
        row_total = sum(Decimal(row["due_amount"]) for row in result["rows"])

        self.assertEqual(Decimal(result["total_due"]), Decimal("7600.00"))
        self.assertEqual(row_total, Decimal(result["total_due"]))
        self.assertEqual(result["student_count"], 2)
        self.assertEqual(result["fee_record_count"], 3)
        self.assertFalse(result["has_more"])

    async def test_due_report_pending_only(self):
        result = await school_data_engine.get_report(
            tenant_id=self.tenant_id,
            report_id="due_fees_by_student",
            filters={"statuses": ["Pending"]},
        )

        self.assertEqual(Decimal(result["total_due"]), Decimal("7000.00"))
        self.assertEqual(result["fee_record_count"], 2)

    async def test_due_report_enforces_tenant_isolation(self):
        result = await school_data_engine.get_report(
            tenant_id=self.tenant_id,
            report_id="due_fees_by_student",
            filters={"statuses": ["Pending", "Partial"]},
        )
        names = {row["student_name"] for row in result["rows"]}

        self.assertNotIn("Other Tenant Student", names)
        self.assertEqual(Decimal(result["total_due"]), Decimal("7600.00"))

    async def test_search_entity_returns_limit_metadata(self):
        result = await school_data_engine.search_entity(
            tenant_id=self.tenant_id,
            entity="student",
            filters=[{"field": "class_id", "op": "$eq", "value": 10}],
            limit=1,
        )

        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["returned_count"], 1)
        self.assertTrue(result["has_more"])


if __name__ == "__main__":
    unittest.main()
