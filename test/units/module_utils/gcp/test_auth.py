# -*- coding: utf-8 -*-
# (c) 2016, Tom Melendez (@supertom) <tom@supertom.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
import os
import sys

import pytest

from ansible.compat.tests import mock, unittest
from ansible.module_utils.gcp import (_get_gcp_ansible_credentials, _get_gcp_credentials, _get_gcp_environ_var,
                                      _get_gcp_libcloud_credentials, _get_gcp_environment_credentials,
                                      _validate_credentials_file)

# Fake data/function used for testing
fake_env_data = {'GCE_EMAIL': 'gce-email'}


def fake_get_gcp_environ_var(var_name, default_value):
    if var_name not in fake_env_data:
        return default_value
    else:
        return fake_env_data[var_name]

# Fake AnsibleModule for use in tests


class FakeModule(object):
    class Params():
        data = {}

        def get(self, key, alt=None):
            if key in self.data:
                return self.data[key]
            else:
                return alt

    def __init__(self, data={}):
        self.params = FakeModule.Params()
        self.params.data = data

    def fail_json(self, **kwargs):
        raise ValueError("fail_json")

    def deprecate(self, **kwargs):
        return None


class GCPAuthTestCase(unittest.TestCase):
    """Tests to verify different Auth mechanisms."""

    def setup_method(self, method):
        global fake_env_data
        fake_env_data = {'GCE_EMAIL': 'gce-email'}

    def test_get_gcp_ansible_credentials(self):
        input_data = {'service_account_email': 'mysa',
                      'credentials_file': 'path-to-file.json',
                      'project_id': 'my-cool-project'}

        module = FakeModule(input_data)
        actual = _get_gcp_ansible_credentials(module)
        expected = tuple(input_data.values())
        self.assertEqual(sorted(expected), sorted(actual))

    def test_get_gcp_environ_var(self):
        # Chose not to mock this so we could really verify that it
        # works as expected.
        existing_var_name = 'gcp_ansible_auth_test_54321'
        non_existing_var_name = 'doesnt_exist_gcp_ansible_auth_test_12345'
        os.environ[existing_var_name] = 'foobar'
        self.assertEqual('foobar', _get_gcp_environ_var(
            existing_var_name, None))
        del os.environ[existing_var_name]
        self.assertEqual('default_value', _get_gcp_environ_var(
            non_existing_var_name, 'default_value'))

    def test_get_gcp_libcloud_credentials_no_import(self):
        """No secrets imported.  Whatever is sent in should come out."""
        module = FakeModule()
        actual = _get_gcp_libcloud_credentials(module,
                                               service_account_email=None,
                                               credentials_file=None,
                                               project_id=None)
        expected = (None, None, None)
        self.assertEqual(expected, actual)
        # no libcloud, with values
        actual = _get_gcp_libcloud_credentials(module,
                                               service_account_email='sa-email',
                                               credentials_file='creds-file',
                                               project_id='proj-id')
        expected = ('sa-email', 'creds-file', 'proj-id')
        self.assertEqual(expected, actual)

    def test_get_gcp_libcloud_credentials_import(self):
        """secrets is imported and those values should be used."""
        # Note: Opted for a real class here rather than MagicMock as
        # __getitem__ comes for free.
        class FakeSecrets:
            def __init__(self):
                # 2 element list, service account email and creds file
                self.GCE_PARAMS = ['secrets-sa', 'secrets-file.json']
                # dictionary with project_id, optionally auth_type
                self.GCE_KEYWORD_PARAMS = {}
                self.__file__ = 'THIS_IS_A_FAKEFILE_FOR_TESTING'

        # patch in module
        fake_secrets = FakeSecrets()
        patcher = mock.patch.dict(sys.modules, {'secrets': fake_secrets})
        patcher.start()

        # obtain sa and creds from secrets
        module = FakeModule()
        actual = _get_gcp_libcloud_credentials(module,
                                               service_account_email=None,
                                               credentials_file=None,
                                               project_id='proj-id')
        expected = ('secrets-sa', 'secrets-file.json', 'proj-id')
        self.assertEqual(expected, actual)

        # fetch project id.  Current logic requires sa-email or creds to be
        # set.
        fake_secrets.GCE_KEYWORD_PARAMS['project'] = 'new-proj-id'
        fake_secrets.GCE_PARAMS[1] = 'my-creds.json'
        module = FakeModule()
        actual = _get_gcp_libcloud_credentials(module,
                                               service_account_email='my-sa',
                                               credentials_file=None,
                                               project_id=None)
        expected = ('my-sa', 'my-creds.json', 'new-proj-id')
        self.assertEqual(expected, actual)

        # stop patching
        patcher.stop()

    def test_validate_credentials_file(self):
        # TODO(supertom): Only dealing with p12 here, check the other states
        # of this function
        module = mock.MagicMock()
        with mock.patch("ansible.module_utils.gcp.open",
                        mock.mock_open(read_data='foobar'), create=True) as m:
            # pem condition, warning is surpressed with the return_value
            credentials_file = '/foopath/pem.pem'
            is_valid = _validate_credentials_file(module,
                                                  credentials_file=credentials_file,
                                                  require_valid_json=False,
                                                  check_libcloud=False)
            self.assertTrue(is_valid)

    @mock.patch('ansible.module_utils.gcp._get_gcp_environ_var',
                side_effect=fake_get_gcp_environ_var)
    def test_get_gcp_environment_credentials(self, mockobj):
        global fake_env_data

        actual = _get_gcp_environment_credentials(None, None, None)
        expected = tuple(['gce-email', None, None])
        self.assertEqual(expected, actual)

        fake_env_data = {'GCE_PEM_FILE_PATH': '/path/to/pem.pem'}
        expected = tuple([None, '/path/to/pem.pem', None])
        actual = _get_gcp_environment_credentials(None, None, None)
        self.assertEqual(expected, actual)

        # pem and creds are set, expect creds
        fake_env_data = {'GCE_PEM_FILE_PATH': '/path/to/pem.pem',
                         'GCE_CREDENTIALS_FILE_PATH': '/path/to/creds.json'}
        expected = tuple([None, '/path/to/creds.json', None])
        actual = _get_gcp_environment_credentials(None, None, None)
        self.assertEqual(expected, actual)

        # expect GOOGLE_APPLICATION_CREDENTIALS over PEM
        fake_env_data = {'GCE_PEM_FILE_PATH': '/path/to/pem.pem',
                         'GOOGLE_APPLICATION_CREDENTIALS': '/path/to/appcreds.json'}
        expected = tuple([None, '/path/to/appcreds.json', None])
        actual = _get_gcp_environment_credentials(None, None, None)
        self.assertEqual(expected, actual)

        # project tests
        fake_env_data = {'GCE_PROJECT': 'my-project'}
        expected = tuple([None, None, 'my-project'])
        actual = _get_gcp_environment_credentials(None, None, None)
        self.assertEqual(expected, actual)

        fake_env_data = {'GOOGLE_CLOUD_PROJECT': 'my-cloud-project'}
        expected = tuple([None, None, 'my-cloud-project'])
        actual = _get_gcp_environment_credentials(None, None, None)
        self.assertEqual(expected, actual)

        # data passed in, picking up project id only
        fake_env_data = {'GOOGLE_CLOUD_PROJECT': 'my-project'}
        expected = tuple(['my-sa-email', '/path/to/creds.json', 'my-project'])
        actual = _get_gcp_environment_credentials(
            'my-sa-email', '/path/to/creds.json', None)
        self.assertEqual(expected, actual)

    @mock.patch('ansible.module_utils.gcp._get_gcp_environ_var',
                side_effect=fake_get_gcp_environ_var)
    def test_get_gcp_credentials(self, mockobj):
        global fake_env_data

        fake_env_data = {}
        module = FakeModule()
        module.params.data = {}
        # Nothing is set, calls fail_json
        with pytest.raises(ValueError):
            _get_gcp_credentials(module)

        # project_id (only) is set from Ansible params.
        module.params.data['project_id'] = 'my-project'
        actual = _get_gcp_credentials(
            module, require_valid_json=True, check_libcloud=False)
        expected = {'service_account_email': '',
                    'project_id': 'my-project',
                    'credentials_file': ''}
        self.assertEqual(expected, actual)
