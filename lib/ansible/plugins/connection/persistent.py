# (c) 2016 Red Hat Inc.
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

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import pty
import subprocess
import sys
from pprint import pformat

from ansible.module_utils._text import to_bytes
from ansible.module_utils.six.moves import cPickle
from ansible.plugins.connection import ConnectionBase

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class Connection(ConnectionBase):
    ''' Local based connections '''

    transport = 'persistent'
    has_pipelining = False

    def _connect(self):

        self._connected = True
        return self

    def _do_it(self, action):

	display.display("ansible-connection start")
        master, slave = pty.openpty()
        p = subprocess.Popen(["ansible-connection"], stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdin = os.fdopen(master, 'wb', 0)
        os.close(slave)

        # Need to force a protocol that is compatible with both py2 and py3.
        # That would be protocol=2 or less.
        # Also need to force a protocol that excludes certain control chars as
        # stdin in this case is a pty and control chars will cause problems.
        # that means only protocol=0 will work.
	display.display("self._play_context.serialize()")
	display.display(pformat(self._play_context.serialize()))
        src = cPickle.dumps(self._play_context.serialize(), protocol=0)
        stdin.write(src)

        stdin.write(b'\n#END_INIT#\n')
        stdin.write(to_bytes(action))
        stdin.write(b'\n\n')

        (stdout, stderr) = p.communicate()
        stdin.close()
	display.display("ansible-connection end")
	display.display("ansible-connection rc {0}".format(p.returncode))
	display.display("ansible-connection stdout {0}".format(stdout))
	display.display("ansible-connection stderr {0}".format(stdout))

        return (p.returncode, stdout, stderr)

    def exec_command(self, cmd, in_data=None, sudoable=True):
        super(Connection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)
        return self._do_it('EXEC: ' + cmd)

    def put_file(self, in_path, out_path):
        super(Connection, self).put_file(in_path, out_path)
        self._do_it('PUT: %s %s' % (in_path, out_path))

    def fetch_file(self, in_path, out_path):
        super(Connection, self).fetch_file(in_path, out_path)
        self._do_it('FETCH: %s %s' % (in_path, out_path))

    def close(self):
        self._connected = False
