import os
import sys
import time
import signal
import unittest
import socket
from subprocess import Popen

import rpclite as rpc

class SetupError(Exception):
    pass

test_dir = os.path.abspath(os.path.dirname(__file__))
base_dir = os.path.abspath(os.path.dirname(__file__) + '/..')

server_exe = test_dir + '/simple_server'
server_log_file = test_dir + '/simple_server.log'
if os.path.isfile(server_log_file):
    os.unlink(server_log_file)

url = "http://localhost:8021"

class _Test(unittest.TestCase):
    server_args = ''
    sever_name = 'no name'
    
    def setUp(self):
        # start server
        self._server_process = None
        path = base_dir + '/build/lib'
        path_check = path + '/rpclite/server/__init__.py'
        if not os.path.isfile(path_check):
            raise SetupError("Could not start test server, no rpclite server module at: '%s' \
            "%os.path.dirname(path_check))
        fp = open(server_log_file, 'a+')
        print 'Starting', self.server_name
        self._server_process = Popen([server_exe, self.server_args], stderr=fp, stdout=fp, env={'PYTHONPATH': path,})
        self._server_log_fp = fp
        time.sleep(1.0)
        
    def tearDown(self):
        # shut down server
        if self._server_process:
            print 'Stopping', self.server_name
            self._server_process.wait()
            self._server_log_fp.close()            

    def test(self):
        server = rpc.XMLRPCServerProxy(url)
        self.server = server

        # 1) echo
        print 'echo ...'
        text = "what's up doc ?"
        self.failUnlessEqual(text, server.echo(text), 'echo failed')

        # 2) instance server
        print 'instance server ...'
        self.failUnlessEqual('hello', server.hello(), 'instance server failed')
        self.failUnlessEqual('nested hello', server.nested.hello(), 'nested instance server failed')

        # 3) class server
        print 'class server ...'
        self.failUnlessEqual('hello', server.hello(), 'class server failed')
        self.failUnlessEqual('nested hello', server.nested.hello(), 'nested class server failed')

        # 4) object server
        print 'object server ...'
        object_str = "{'nested_object': {'number': 8989, 'tuple': ['thurston', 'kim', 'steve', 'lee']}, 'dict': {'a': 1, 'c': 3, 'b': 2}, 'number': 9898}"
        self.failUnlessEqual(object_str, str(server.get_object()), 'fetching an object failed')

        # 5) timeout server
        print 'timeout ...'
        self.failUnlessRaises(rpc.SocketTimeout, self._check_timeout)
        # can we still talk to the server ?
        if not server.system.isalive():
            self.fail('server is dead after timeout')
        print 'server is alive ...'
        sys.stdout.flush()
        time.sleep(2.2)

        # 6) list methods
        print 'list methods ...'
        server_methods = ['echo', 'get_object', 'hello', 'nested.hello', 'sleep', 'system.isalive', 'system.listMethods', 'system.methodHelp', 'system.methodSignature', 'system.multicall', 'system.ping', 'system.whoami', 'system.whoareyou']
        self.failUnlessEqual(server_methods, server.system.listMethods(), 'server method list differ')

    def _check_timeout(self):
        self.server.sleep(3, timeout=1)

class TestBlocking(_Test):
    server_args = '-b'
    server_name = 'Blocking server'

class TestThreading(_Test):
    server_args = '-t'
    server_name = 'Threading server'

class TestForking(_Test):
    server_args = '-f'
    server_name = 'Forking server'
    
