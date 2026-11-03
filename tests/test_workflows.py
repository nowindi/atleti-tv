from pathlib import Path
import subprocess
import unittest
import yaml


class WorkflowTests(unittest.TestCase):
    def test_every_bash_step_has_valid_syntax(self):
        for path in Path('.github/workflows').glob('*.yml'):
            workflow = yaml.safe_load(path.read_text())
            for job in workflow['jobs'].values():
                for step in job.get('steps', []):
                    if 'run' not in step:
                        continue
                    with self.subTest(workflow=path.name, step=step.get('name', step['run'])):
                        result = subprocess.run(['bash', '-n'], input=step['run'], text=True, capture_output=True)
                        self.assertEqual(result.returncode, 0, result.stderr)

    def test_scheduled_updates_explicitly_deploy_after_commit(self):
        workflow = yaml.safe_load(Path('.github/workflows/update.yml').read_text())
        self.assertEqual(workflow['jobs']['deploy']['needs'], 'update')
        self.assertEqual(workflow['jobs']['deploy']['uses'], './.github/workflows/pages.yml')
        self.assertTrue(workflow['jobs']['update']['steps'][0]['with']['ref'] == 'main')


if __name__ == '__main__':
    unittest.main()
