import unittest

from app.auth import hash_password, verify_password


class AuthTests(unittest.TestCase):
    def test_password_hash_is_not_plaintext_and_verifies(self):
        stored = hash_password("safe-test-password")
        self.assertNotEqual(stored, "safe-test-password")
        self.assertTrue(verify_password("safe-test-password", stored))
        self.assertFalse(verify_password("wrong-password", stored))


if __name__ == "__main__":
    unittest.main()
