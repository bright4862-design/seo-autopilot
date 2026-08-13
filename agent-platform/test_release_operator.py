from __future__ import annotations

import unittest

import release_operator as r


class _FakeTasks:
    @staticmethod
    def queue_path(project, location, queue):
        return f"projects/{project}/locations/{location}/queues/{queue}"


class ReleaseOperatorSafetyTests(unittest.TestCase):
    def setUp(self):
        self.operator = r.FixListReleaseOperator()
        self.operator.set_up()
        self.operator._tasks = _FakeTasks()

    def test_release_surface_is_hard_allowlisted(self):
        self.assertEqual(
            r.ALLOWED_SERVICES,
            {"fixlist-standard150-worker", "fixlist-dispatch-gateway"},
        )
        self.assertEqual(r.QUEUE, "fixlist-standard150")
        self.assertEqual(r.QUEUE_LOCATION, "europe-west1")

    def test_service_allowlist_refuses_unrelated_service(self):
        allowed = self.operator._service_name("fixlist-standard150-worker")
        self.assertTrue(allowed.endswith("/services/fixlist-standard150-worker"))
        with self.assertRaises(PermissionError):
            self.operator._service_name("unrelated-production-service")

    def test_queue_allowlist_refuses_other_queue(self):
        allowed = self.operator._queue_name("fixlist-standard150", "europe-west1")
        self.assertTrue(allowed.endswith("/queues/fixlist-standard150"))
        with self.assertRaises(PermissionError):
            self.operator._queue_name("other-queue", "europe-west1")

    def test_mutations_require_exact_confirmation(self):
        with self.assertRaises(PermissionError):
            self.operator._require_confirm("")
        with self.assertRaises(PermissionError):
            self.operator._require_confirm("yes")
        self.operator._require_confirm("FIXLIST_RELEASE_MUTATION")


if __name__ == "__main__":
    unittest.main()
