import os
import uuid
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from bson.decimal128 import Decimal128

from core.auth import db
from services.school_data_service import SchoolDataService
from services.school_agent.graph import graph
from services.school_agent.tools import resolve_student_id, resolve_class_id
from langgraph.types import Command

class TestSchoolAgent(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncio
        from core.auth import client
        client.get_io_loop = asyncio.get_running_loop

        # Set feature flag for write actions during test
        self.old_write_flag = os.environ.get("SCHOOL_WRITE_ACTIONS_ENABLED")
        os.environ["SCHOOL_WRITE_ACTIONS_ENABLED"] = "True"

        self.tenant_id = "test_tenant_123"
        self.session_id = f"test_session_{uuid.uuid4()}"
        self.service = SchoolDataService()

        # Seed data matching strict MongoDB Atlas JSON Schema validator rules
        await db.school_classes.insert_one({
            "class_id": 10,
            "class_name": "Class 3",
            "school_id": 1,
            "tenant_id": self.tenant_id
        })
        await db.school_sections.insert_one({
            "section_id": 20,
            "section_name": "A",
            "class_id": 10,
            "school_id": 1,
            "tenant_id": self.tenant_id
        })
        await db.school_students.insert_one({
            "student_id": 1,
            "admission_no": "ADM001",
            "student_name": "Ansh Sharma",
            "father_name": "Father Sharma",
            "mother_name": "Mother Sharma",
            "gender": "Male",
            "blood_group": "O+",
            "category": "General",
            "address": "123 Main St",
            "class_id": 10,
            "section_id": 20,
            "school_id": 1,
            "tenant_id": self.tenant_id
        })
        await db.school_applied_fees.insert_one({
            "applied_fee_id": 100,
            "student_id": 1,
            "fee_head": "Tuition Fee",
            "amount": Decimal128(Decimal("5000.00")),
            "concession": Decimal128(Decimal("0.00")),
            "status": "Pending",
            "due_date": "2026-08-01",
            "school_id": 1,
            "tenant_id": self.tenant_id
        })
        await db.school_payments.insert_one({
            "payment_id": 200,
            "student_id": 1,
            "applied_fee_id": 100,
            "paid_amount": Decimal128(Decimal("0.00")),
            "balance": Decimal128(Decimal("5000.00")),
            "payment_date": "2026-07-01",
            "payment_mode": "UPI",
            "receipt_no": "REC001",
            "school_id": 1,
            "tenant_id": self.tenant_id
        })
        await db.school_routes.insert_one({
            "route_id": 400,
            "route_name": "Mansarovar",
            "route_code": "R400",
            "school_id": 1,
            "tenant_id": self.tenant_id
        })
        await db.school_stops.insert_one({
            "stop_id": 500,
            "stop_name": "Gandhi Path",
            "route_id": 400,
            "school_id": 1,
            "tenant_id": self.tenant_id
        })
        await db.school_transport_assign.insert_one({
            "transport_id": 300,
            "student_id": 1,
            "route_id": 400,
            "stop_id": 500,
            "vehicle_no": "BUS09",
            "transport_status": "Active",
            "school_id": 1,
            "tenant_id": self.tenant_id
        })
        await db.school_hostel_assign.insert_one({
            "hostel_id": 600,
            "student_id": 1,
            "hostel_name": "Main Hostel",
            "room_no": "101",
            "bed_no": 1,
            "hostel_status": "Active",
            "school_id": 1,
            "tenant_id": self.tenant_id
        })

    async def asyncTearDown(self):
        # Restore feature flag
        if self.old_write_flag is not None:
            os.environ["SCHOOL_WRITE_ACTIONS_ENABLED"] = self.old_write_flag
        else:
            del os.environ["SCHOOL_WRITE_ACTIONS_ENABLED"]

        # Clean up database
        await db.school_students.delete_many({"tenant_id": self.tenant_id})
        await db.school_classes.delete_many({"tenant_id": self.tenant_id})
        await db.school_sections.delete_many({"tenant_id": self.tenant_id})
        await db.school_applied_fees.delete_many({"tenant_id": self.tenant_id})
        await db.school_payments.delete_many({"tenant_id": self.tenant_id})
        await db.school_transport_assign.delete_many({"tenant_id": self.tenant_id})
        await db.school_routes.delete_many({"tenant_id": self.tenant_id})
        await db.school_stops.delete_many({"tenant_id": self.tenant_id})
        await db.school_hostel_assign.delete_many({"tenant_id": self.tenant_id})
        await db.school_data_query_log.delete_many({"tenant_id": self.tenant_id})
        await db.school_audit_log.delete_many({"tenant_id": self.tenant_id})

    async def test_resolve_student_id_tool(self):
        config = {"configurable": {"tenant_id": self.tenant_id, "session_id": self.session_id}}
        result_str = await resolve_student_id.ainvoke({"name": "Ansh"}, config=config)
        self.assertIn("Ansh Sharma", result_str)
        self.assertIn("student_id", result_str)

    async def test_resolve_class_id_tool(self):
        config = {"configurable": {"tenant_id": self.tenant_id, "session_id": self.session_id}}
        result_str = await resolve_class_id.ainvoke({"class_name": "Class 3"}, config=config)
        self.assertIn("Class 3", result_str)
        self.assertIn("class_id", result_str)

    async def test_multi_hop_query(self):
        # Querying for transport status by student name
        result = await self.service.query(
            tenant_id=self.tenant_id,
            session_id=self.session_id,
            question="what is the transport status for student Ansh?"
        )
        self.assertIn("Active", result)
        self.assertIn("Mansarovar", result)

    async def test_write_approval_interception_and_resume(self):
        # Make a write request
        config = {
            "configurable": {
                "thread_id": self.session_id,
                "tenant_id": self.tenant_id,
                "session_id": self.session_id,
                "question": "change transport status for transport_id 300 to Inactive"
            }
        }
        
        # Invoke the graph directly so we can inspect the interrupt
        from langchain_core.messages import HumanMessage
        initial_state = {
            "messages": [HumanMessage(content="change transport status for transport_id 300 to Inactive")],
            "tenant_id": self.tenant_id,
            "school_session_id": self.session_id,
            "original_question": "change transport status for transport_id 300 to Inactive"
        }
        
        res = await graph.ainvoke(initial_state, config=config)
        
        # 1. Assert we were interrupted
        self.assertIn("__interrupt__", res)
        self.assertTrue(len(res["__interrupt__"]) > 0)
        
        # 2. Assert MongoDB document is still Active (not written to yet)
        doc = await db.school_transport_assign.find_one({"transport_id": 300})
        self.assertEqual(doc["transport_status"], "Active")
        
        # 3. Resume the graph with approval
        res2 = await graph.ainvoke(Command(resume={"approved": True}), config=config)
        
        # 4. Assert MongoDB document has been updated to Inactive
        doc = await db.school_transport_assign.find_one({"transport_id": 300})
        self.assertEqual(doc["transport_status"], "Inactive")

    async def test_audit_logging_writes_to_collections(self):
        # Call query which invokes tools
        await self.service.query(
            tenant_id=self.tenant_id,
            session_id=self.session_id,
            question="show all students in class 3"
        )
        
        # Check logs
        log_count_1 = await db.school_data_query_log.count_documents({"tenant_id": self.tenant_id})
        log_count_2 = await db.school_audit_log.count_documents({"tenant_id": self.tenant_id})
        
        self.assertTrue(log_count_1 > 0)
        self.assertTrue(log_count_2 > 0)
        
        # Verify a specific log entry fields
        log_doc = await db.school_data_query_log.find_one({"tenant_id": self.tenant_id})
        self.assertEqual(log_doc["tenant_id"], self.tenant_id)
        self.assertEqual(log_doc["session_id"], self.session_id)
        self.assertIn("tool_name", log_doc)
