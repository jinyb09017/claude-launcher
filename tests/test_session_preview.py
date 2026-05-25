import json
import tempfile
import unittest
from pathlib import Path

import workspace


class SessionPreviewTests(unittest.TestCase):
    def test_session_preview_uses_last_user_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_claude_dir = workspace.CLAUDE_DIR
            try:
                workspace.CLAUDE_DIR = Path(tmp) / '.claude'
                encoded = '-tmp-project'
                project_dir = workspace.CLAUDE_DIR / 'projects' / encoded
                project_dir.mkdir(parents=True)
                session_file = project_dir / 'session-1.jsonl'

                rows = [
                    {'message': {'role': 'user', 'content': [{'type': 'text', 'text': 'first user message'}]}},
                    {'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'assistant reply'}]}},
                    {'message': {'role': 'user', 'content': [{'type': 'tool_result', 'content': 'ignore tool result'}]}},
                    {'message': {'role': 'user', 'content': [{'type': 'text', 'text': 'last user message'}]}},
                ]
                session_file.write_text('\n'.join(json.dumps(row) for row in rows))

                sessions = workspace.get_project_sessions(encoded)

                self.assertEqual(len(sessions), 1)
                self.assertEqual(sessions[0]['preview'], 'last user message')
            finally:
                workspace.CLAUDE_DIR = original_claude_dir


if __name__ == '__main__':
    unittest.main()
