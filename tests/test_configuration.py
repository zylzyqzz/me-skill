from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import configure
import me
import onboard
import validate_package
import submit_pr


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'me-skill'
        shutil.copytree(ROOT,self.root,ignore=shutil.ignore_patterns('.git','.local','__pycache__'))

    def configure(self, repo='example-owner/private-assistant', write=True):
        return configure.configure(self.root,repo,'Synthetic','UTC',write)

    def test_unconfigured_template_is_empty_and_cannot_initialize(self):
        self.assertTrue(validate_package.validate(self.root,template=True)['empty_template'])
        with self.assertRaisesRegex(ValueError,'Configure your own'):
            me.init(self.root)

    def test_configuration_preview_is_read_only(self):
        before=(self.root/'me.json').read_bytes()
        self.assertFalse(self.configure(write=False)['configured'])
        self.assertEqual((self.root/'me.json').read_bytes(),before)

    def test_reject_public_template_destination_and_invalid_repo(self):
        for name in ('zylzyqzz/me-skill','owner/repo?redirect=other','https://example.invalid/repo'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.configure(name)

    def test_initialized_installation_cannot_reroute_evidence(self):
        self.configure()
        identity=me.init(self.root)
        with self.assertRaisesRegex(ValueError,'migrate explicitly'):
            self.configure('another-owner/private-assistant')
        self.assertEqual(me.state(self.root)[0],identity)

    def test_blank_profile_cannot_claim_onboarding(self):
        self.configure()
        me.init(self.root)
        with self.assertRaisesRegex(ValueError,'Blank template'):
            onboard.install(self.root,Path(self.temp.name)/'AGENTS.md',True)
        self.assertFalse((Path(self.temp.name)/'AGENTS.md').exists())

    def test_public_template_validation_rejects_personalization(self):
        self.configure()
        with self.assertRaisesRegex(ValueError,'must not be configured'):
            validate_package.validate(self.root,template=True)

    def test_api_destination_guard_precedes_authentication(self):
        with patch.object(submit_pr,'credential') as auth:
            with self.assertRaisesRegex(ValueError,'outside configured repository'):
                submit_pr.api('/repos/another-owner/repo',repository='example-owner/private-assistant')
            auth.assert_not_called()

    def test_two_people_keep_distinct_configuration(self):
        other=Path(self.temp.name)/'other'
        shutil.copytree(self.root,other)
        self.configure()
        configure.configure(other,'another-owner/personal','Another synthetic','Asia/Shanghai',True)
        self.assertNotEqual(me.config(self.root)['repository'],me.config(other)['repository'])
        self.assertNotEqual(me.init(self.root)['agent_id'],me.init(other)['agent_id'])


if __name__=='__main__':
    unittest.main()
