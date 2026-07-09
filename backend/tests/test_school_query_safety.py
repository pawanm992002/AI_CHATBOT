"""
Unit tests for SchoolDataService query safety.

Verifies that malicious/broken LLM outputs cannot escape tenant scoping
or inject dangerous Mongo operators.
"""

import unittest
from services.school_data_filter import build_safe_filter, validate_condition, FIELD_ALLOWLIST


class TestValidateCondition(unittest.TestCase):
    """Tests that validate_condition rejects dangerous or invalid inputs."""

    def test_rejects_unknown_collection(self):
        cond = {"field": "student_name", "op": "$eq", "value": "Ansh"}
        result = validate_condition("nonexistent_collection", cond)
        self.assertIsNone(result)

    def test_rejects_disallowed_field(self):
        cond = {"field": "password_hash", "op": "$eq", "value": "hunter2"}
        result = validate_condition("school_students", cond)
        self.assertIsNone(result)

    def test_rejects_disallowed_operator(self):
        cond = {"field": "student_name", "op": "$where", "value": "1==1"}
        result = validate_condition("school_students", cond)
        self.assertIsNone(result)

    def test_rejects_tenant_id_field(self):
        """LLM must NOT be able to specify tenant_id as a filter field."""
        for coll, allow in FIELD_ALLOWLIST.items():
            cond = {"field": "tenant_id", "op": "$eq", "value": "some_other_tenant"}
            result = validate_condition(coll, cond)
            self.assertIsNone(result, f"{coll} allowed tenant_id filter!")

    def test_rejects_expr_operator(self):
        cond = {"field": "student_name", "op": "$expr", "value": "1"}
        result = validate_condition("school_students", cond)
        self.assertIsNone(result)

    def test_rejects_long_regex(self):
        """Regex longer than 200 chars should be rejected."""
        cond = {"field": "student_name", "op": "$regex", "value": "a" * 250}
        result = validate_condition("school_students", cond)
        self.assertIsNone(result)

    def test_accepts_valid_eq_condition(self):
        cond = {"field": "class_id", "op": "$eq", "value": 5}
        result = validate_condition("school_students", cond)
        self.assertEqual(result, {"class_id": {"$eq": 5}})

    def test_accepts_valid_regex_condition(self):
        cond = {"field": "student_name", "op": "$regex", "value": "Ansh"}
        result = validate_condition("school_students", cond)
        self.assertIn("$regex", result["student_name"])

    def test_accepts_valid_in_condition(self):
        cond = {"field": "class_id", "op": "$in", "value": [1, 2, 3]}
        result = validate_condition("school_students", cond)
        self.assertEqual(result, {"class_id": {"$in": [1, 2, 3]}})

    def test_all_collections_have_allowlist(self):
        """Every collection in FIELD_ALLOWLIST must have allowed_fields and allowed_ops."""
        for coll, rules in FIELD_ALLOWLIST.items():
            self.assertIn("allowed_fields", rules, f"{coll} missing allowed_fields")
            self.assertIn("allowed_ops", rules, f"{coll} missing allowed_ops")
            self.assertNotIn("tenant_id", rules["allowed_fields"],
                             f"{coll} must NOT allow filtering on tenant_id")


class TestBuildSafeFilter(unittest.TestCase):
    """Tests that build_safe_filter always injects tenant_id server-side."""

    def test_injects_tenant_id(self):
        conditions = [{"field": "student_name", "op": "$eq", "value": "Ansh"}]
        result = build_safe_filter("school_students", conditions, "tenant_abc")
        self.assertIn("$and", result)
        self.assertIn({"tenant_id": "tenant_abc"}, result["$and"])

    def test_rejects_tenant_id_via_conditions(self):
        """Even if LLM sends a tenant_id condition, it gets filtered out."""
        conditions = [
            {"field": "tenant_id", "op": "$eq", "value": "malicious_tenant"},
            {"field": "student_name", "op": "$eq", "value": "Ansh"},
        ]
        result = build_safe_filter("school_students", conditions, "tenant_abc")
        self.assertIn("$and", result)
        # The $and should have exactly 2 items: tenant_id (server-side) + student_name condition
        # The malicious tenant_id condition from LLM must NOT appear
        self.assertEqual(len(result["$and"]), 2)
        self.assertIn({"tenant_id": "tenant_abc"}, result["$and"])
        self.assertIn({"student_name": {"$eq": "Ansh"}}, result["$and"])
        # Verify the malicious tenant_id value is NOT present
        self.assertNotIn({"tenant_id": "malicious_tenant"}, result["$and"])

    def test_falls_back_to_tenant_only_filter(self):
        """When all conditions are rejected, only tenant_id remains."""
        result = build_safe_filter("school_students", [], "tenant_abc")
        self.assertEqual(result, {"tenant_id": "tenant_abc"})

    def test_injection_attempt_with_where(self):
        """$where injection attempt must be scrubbed."""
        conditions = [{"field": "student_name", "op": "$where", "value": "sleep(5000)"}]
        result = build_safe_filter("school_students", conditions, "tenant_abc")
        self.assertEqual(result, {"tenant_id": "tenant_abc"})


class TestMaliciousLLMOutput(unittest.TestCase):
    """End-to-end tests simulating malicious LLM outputs."""

    def test_all_allowed_fields_are_innocuous(self):
        """Verify each allowed field is actually a safe school data field."""
        suspicious_keywords = ["password", "secret", "token", "key", "hash", "session"]
        for coll, rules in FIELD_ALLOWLIST.items():
            for field in rules["allowed_fields"]:
                for kw in suspicious_keywords:
                    self.assertNotIn(kw, field.lower(),
                                     f"{coll}.{field} looks like a sensitive field")

    def test_all_allowed_ops_are_safe(self):
        """Verify only safe operators are in the allowlist."""
        dangerous_ops = {"$where", "$expr", "$accumulator", "$function", "$regexMatch"}
        for coll, rules in FIELD_ALLOWLIST.items():
            for op in rules["allowed_ops"]:
                self.assertNotIn(op, dangerous_ops,
                                 f"{coll} allows dangerous operator {op}")


if __name__ == "__main__":
    unittest.main()
