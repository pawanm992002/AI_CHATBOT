"""Unit tests for registry-backed School ERP query safety."""

import unittest

from services.school_data_engine import (
    MAX_REGEX_LENGTH,
    build_entity_filter,
    validate_filter_condition,
)
from services.school_data_registry import SAFE_OPERATORS, SCHOOL_ENTITY_REGISTRY, get_entity_spec


class TestRegistryQuerySafety(unittest.TestCase):
    def setUp(self):
        self.student = get_entity_spec("student")

    def test_rejects_unknown_entity(self):
        with self.assertRaises(ValueError):
            get_entity_spec("nonexistent_entity")

    def test_rejects_sensitive_or_unknown_fields(self):
        for field in ("password_hash", "api_key", "tenant_id"):
            with self.assertRaises(ValueError):
                validate_filter_condition(self.student, {"field": field, "op": "$eq", "value": "x"})

    def test_rejects_dangerous_operators(self):
        for operator in ("$where", "$expr", "$function", "$accumulator"):
            with self.assertRaises(ValueError):
                validate_filter_condition(self.student, {"field": "student_name", "op": operator, "value": "x"})

    def test_rejects_long_regex(self):
        with self.assertRaises(ValueError):
            validate_filter_condition(
                self.student,
                {"field": "student_name", "op": "$regex", "value": "a" * (MAX_REGEX_LENGTH + 1)},
            )

    def test_accepts_valid_filter_conditions(self):
        self.assertEqual(
            validate_filter_condition(self.student, {"field": "class_id", "op": "$eq", "value": 5}),
            {"class_id": {"$eq": 5}},
        )
        self.assertEqual(
            validate_filter_condition(self.student, {"field": "class_id", "op": "$in", "value": [1, 2]}),
            {"class_id": {"$in": [1, 2]}},
        )

    def test_build_filter_injects_tenant_id(self):
        result = build_entity_filter(
            self.student,
            [{"field": "student_name", "op": "$regex", "value": "Ansh"}],
            "tenant_abc",
        )
        self.assertIn({"tenant_id": "tenant_abc"}, result["$and"])
        self.assertIn({"student_name": {"$regex": "Ansh", "$options": "i"}}, result["$and"])

    def test_tenant_override_is_rejected(self):
        with self.assertRaises(ValueError):
            build_entity_filter(
                self.student,
                [{"field": "tenant_id", "op": "$eq", "value": "other_tenant"}],
                "tenant_abc",
            )

    def test_registry_has_only_safe_fields_and_operators(self):
        suspicious = {"password", "secret", "token", "key", "hash", "session", "tenant"}
        dangerous_ops = {"$where", "$expr", "$accumulator", "$function", "$regexMatch"}
        for spec in SCHOOL_ENTITY_REGISTRY.values():
            for field_name, field_spec in spec.fields.items():
                self.assertFalse(any(term in field_name.lower() for term in suspicious))
                self.assertTrue(set(field_spec.operators).issubset(SAFE_OPERATORS))
                self.assertFalse(set(field_spec.operators) & dangerous_ops)


if __name__ == "__main__":
    unittest.main()
