"""Permission matrix integrity tests."""

from __future__ import annotations

import unittest


class TestRoleMatrix(unittest.TestCase):
    def test_read_only_cannot_write_system_in_matrix(self) -> None:
        from zatgo_core.constants.roles import ROLE_PERMISSION_MATRIX, ROLES

        matrix = ROLE_PERMISSION_MATRIX[ROLES["READ_ONLY"]]
        self.assertFalse(matrix["system"])
        self.assertFalse(matrix["security"])
        self.assertTrue(matrix["audit"])

    def test_application_admin_can_manage_features(self) -> None:
        from zatgo_core.constants.roles import ROLE_PERMISSION_MATRIX, ROLES

        matrix = ROLE_PERMISSION_MATRIX[ROLES["APPLICATION_ADMIN"]]
        self.assertTrue(matrix["features"])
        self.assertTrue(matrix["apps"])
        self.assertFalse(matrix["security"])


if __name__ == "__main__":
    unittest.main()
