import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import workspace


class DeleteProjectLogsTest(unittest.TestCase):
    def test_deletes_only_encoded_claude_project_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_dir = workspace.CLAUDE_DIR
            try:
                workspace.CLAUDE_DIR = Path(tmp) / ".claude"
                log_dir = workspace.CLAUDE_DIR / "projects" / "-tmp-real-project"
                real_dir = Path(tmp) / "real-project"
                log_dir.mkdir(parents=True)
                real_dir.mkdir()
                (log_dir / "session.jsonl").write_text("{}\n")
                (real_dir / "keep.txt").write_text("do not delete")

                self.assertTrue(workspace.delete_project_logs("-tmp-real-project"))

                self.assertFalse(log_dir.exists())
                self.assertTrue(real_dir.exists())
                self.assertTrue((real_dir / "keep.txt").exists())
            finally:
                workspace.CLAUDE_DIR = old_dir

    def test_rejects_path_traversal_encoded_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_dir = workspace.CLAUDE_DIR
            try:
                workspace.CLAUDE_DIR = Path(tmp) / ".claude"
                (workspace.CLAUDE_DIR / "projects").mkdir(parents=True)

                self.assertFalse(workspace.delete_project_logs("../outside"))
            finally:
                workspace.CLAUDE_DIR = old_dir


if __name__ == "__main__":
    unittest.main()
