import unittest

from .orchestrator import ALLOWED_TOOLS, _validate_args
from .prompt_agent import parse_json_object


class PromptParsingTests(unittest.TestCase):
    def test_parse_plain_json(self):
        self.assertEqual(parse_json_object('{"allowed": true}'), {"allowed": True})

    def test_parse_fenced_json(self):
        self.assertEqual(parse_json_object('```json\n{"allowed": false}\n```'), {"allowed": False})


class ToolAllowlistTests(unittest.TestCase):
    def test_only_data_gov_tools_are_allowlisted(self):
        self.assertEqual(
            ALLOWED_TOOLS,
            {"search_datasets", "inspect_dataset_structure", "download_dataset", "download_filtered_dataset"},
        )

    def test_rejects_unknown_tool(self):
        with self.assertRaises(ValueError):
            _validate_args("update_config", {})

    def test_search_queries_are_bounded(self):
        with self.assertRaises(ValueError):
            _validate_args("search_datasets", {"queries": ["x"] * 6})

    def test_download_limit_is_bounded(self):
        with self.assertRaises(ValueError):
            _validate_args(
                "download_dataset",
                {"resource_id": "8a3761be-1b0b-423d-a907-1f99870b365a", "limit": 1001},
            )
