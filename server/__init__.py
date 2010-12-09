#-----------------------------------------------------------------------------
#
# XML-RPC server.
#
# This code to introduce threaded and forking XML-RPC severs.
#
# Therefor, also the possibility to register classes instead of
# instances, so connections can have separate instances of the
# registered class.
#
# Currently we have no management of threads or subprocesses, and
# we probly should not.
#
#-----------------------------------------------------------------------------
import os
import sys
import time
import logging
import threading
import socket
import SocketServer
from SimpleXMLRPCServer import *

try:
    import fcntl
except ImportError:
    fcntl = None

# if socket.timeout are used, uncomment the following line.
assert sys.version[:3] >= '2.3', 'Python version 2.3 or above is required.'

__version__ = "$Revision$"
__all__ = ['XMLRPCServer', 'ThreadingXMLRPCServer', 'ForkingXMLRPCServer', 'BlockingXMLRPCServer']

logger = logging.getLogger('rpc-server')

#-----------------------------------------------------------------------------
#
# XML-RPC Dispatcher.
#
# - An more thread-safe XMLRPCDispatcher.
# - A class can be registered. Each request/thread will then have it's own instance.
#
# We will overwrite _dispatch to lock the method lookup.
#
# (It's goes like this: SocketServer is instantiating a SimpleXMLRPCRequestHandler
# per request (good). It's do_POST calls SimpleXMLRPCDispatch._marshaled_dispatch,
# which at some point calls SimpleXMLRPCDispatcher._dispatch).
#
#-----------------------------------------------------------------------------
class _XMLRPCDispatcher(SimpleXMLRPCDispatcher):
    """Simple XML-RPC server.

    Simple XML-RPC server that allows functions and a single instance
    to be installed to handle requests. The default implementation
    attempts to dispatch XML-RPC calls to the functions or instance
    installed in the server. Override the _dispatch method inhereted
    from SimpleXMLRPCDispatcher to change this behavior.
    """    
    server_type = 'unknown'
    _enable_tracebacks = True
    _print_exceptions = False

    
    def __init__(self, allow_none, encoding):
        self.klass = None
        self._lookup_lock = threading.Lock()
	self.allow_none= allow_none
	self.encoding = encoding
        try:
            # python 2.4 -> 2.5 incompatibilities
            SimpleXMLRPCDispatcher.__init__(self, allow_none, encoding)
        except TypeError:
            SimpleXMLRPCDispatcher.__init__(self)

    def register_class(self, klass, allow_dotted_names=True):
        self.klass = klass
        self.allow_dotted_names = allow_dotted_names
        if self.instance:
            logger.warning("warning: overwriting previous registered instance")
        self.instance = None

    def register_instance(self, instance, allow_dotted_names=True):
        self.instance = instance
        self.allow_dotted_names = allow_dotted_names
        if self.klass:
            logger.warning("warning: overwriting previous registered class")
        self.klass = None

    #
    # Extra "introspection" calls
    #
    def system_whoareyou(self):
        return self.main_id

    def system_whoami(self):
        args = self.name, threading.currentThread().getName(), os.getpid(), socket.gethostname()
        return "%s thread '%s' in process '%r' on %r"%args

    def system_isalive(self):
        return True

    def system_ping(self, data):
        return data

    def register_introspection_functions_extra(self):
        self.funcs.update(
            {'system.whoareyou' : self.system_whoareyou,
             'system.whoami' : self.system_whoami,
             'system.isalive' : self.system_isalive,
             'system.ping' : self.system_ping,}
            )
        
    def _setup_dispatcher(self):
        self.register_multicall_functions()
        self.register_introspection_functions()
        self.register_introspection_functions_extra()

    def _marshaled_dispatch(self, data, dispatch_method = None):
        """Dispatches an XML-RPC method from marshalled (XML) data.
        This overwrite to have the option to send server tracebacks.
        """

        try:
            params, method = xmlrpclib.loads(data)

            # generate response
            if dispatch_method is not None:
                response = dispatch_method(method, params)
            else:
                response = self._dispatch(method, params)
            # wrap response in a singleton tuple
            response = (response,)
            response = xmlrpclib.dumps(response, methodresponse=1,
                                       allow_none=self.allow_none, encoding=self.encoding)
        except Fault, fault:
            response = xmlrpclib.dumps(fault, allow_none=self.allow_none,
                                       encoding=self.encoding)
        except:
            # report exception back to server
            import traceback
            exc_type, exc_value, exc_tb = sys.exc_info()
            if self._print_exceptions:
                traceback.print_exc()
            if self._enable_tracebacks:
                exc_tb = ', server-tb: ' + repr(traceback.extract_tb(exc_tb))
            else:
                exc_tb = ''
            response = xmlrpclib.dumps(
                xmlrpclib.Fault(1, "%s:%s%s" % (exc_type, exc_value, exc_tb)),
                encoding=self.encoding, allow_none=self.allow_none,
                )

        return response
    
    def _dispatch(self, method, params):
        """Dispatches the XML-RPC method.
        All from SimpleXMLRPCDispatcher._dispatch, but we have overwitten
        to introduce a lock for _dispatch lookup ... (_dispatch is called
        from _marshaled_dispatch, which looks safe.)
        """        
        func = None
        dispatch_func = None
        
        self._lookup_lock.acquire()
        try:
            # do we have a registred klass ?
            if self.klass:
                self.instance = self.klass()
            try:
                # check to see if a matching function has been registered
                func = self.funcs[method]
            except KeyError:
                if self.instance is not None:
                    # check for a _dispatch method
                    if hasattr(self.instance, '_dispatch'):
                        dispatch_func = self.instance._dispatch
                    else:
                        # call instance method directly
                        try:
                            func = resolve_dotted_attribute(
                                self.instance,
                                method,
                                self.allow_dotted_names
                                )
                        except AttributeError:
                            pass
        finally:
            self._lookup_lock.release()

        if func is not None:
            return func(*params)
        elif dispatch_func is not None:
            return self.instance._dispatch(method, params)
        else:
            raise Exception('method "%s" is not supported' % method)

#-----------------------------------------------------------------------------
#
# Socket Mixout.
#
#-----------------------------------------------------------------------------
class _SocketMixout:
    
    allow_reuse_address = True

    def _setup_socket(self):
        # SimpleXMLRPCServer say:
        # [Bug #1222790] If possible, set close-on-exec flag; if a
        # method spawns a subprocess, the subprocess shouldn't have
        # the listening socket open.
        if fcntl is not None and hasattr(fcntl, 'FD_CLOEXEC'):
            flags = fcntl.fcntl(self.fileno(), fcntl.F_GETFD)
            flags |= fcntl.FD_CLOEXEC
            fcntl.fcntl(self.fileno(), fcntl.F_SETFD, flags)
            
    #
    # Not to much noise for socket error 32 (Broken pipe) ... please.
    #
    def handle_error(self, request, client_address):
        type, value, trace = sys.exc_info()
        if type == socket.error and value[0] == 32:
            logger.error('Broken pipe for %s ...ignoring', str(client_address))
        else:
            super('_SocketMixout', self).handle_error(request, client_address)

#-----------------------------------------------------------------------------
#
# Small helpers.
#
#-----------------------------------------------------------------------------
def list_public_methods(obj, prepend=''):
    # From SimpleXMLRPCServer, but with an optional argument.
    return [prepend + member for member in dir(obj)
            if not member.startswith('_') and
            hasattr(getattr(obj, member), '__call__')]

#-----------------------------------------------------------------------------
#
# The base server.
#
#-----------------------------------------------------------------------------
class _XMLRPCServer(_SocketMixout, SocketServer.TCPServer, _XMLRPCDispatcher):

    def __init__(self, name, addr, logRequests=1, allow_none=False, encoding=None):

        self.name = name
        self.logRequests = logRequests

        _XMLRPCDispatcher.__init__(self, allow_none, encoding)
        SocketServer.TCPServer.__init__(self, addr, SimpleXMLRPCRequestHandler)

        args = (self.name,
                self.server_type,
                self.server_address,
                threading.currentThread().getName(),
                os.getpid(),
                socket.gethostname())
        self.main_id = "%s - %s - %r - thread %r in process '%r' on %r"%args
        
        self._setup_socket()        
        self._setup_dispatcher()
        logger.info(self.main_id)

#-----------------------------------------------------------------------------
#
# The none threaded, none forking version.
# This one can block other clients, and client timeouts does not make sense.
#
#-----------------------------------------------------------------------------
class BlockingXMLRPCServer(_XMLRPCServer):

    server_type = 'blocking'

#-----------------------------------------------------------------------------
#
# The forking version.
#
#-----------------------------------------------------------------------------
class ForkingXMLRPCServer(SocketServer.ForkingMixIn, _XMLRPCServer):

    server_type = 'forking'
    max_children = 40
    
#-----------------------------------------------------------------------------
#
# The threaded version.
#
#-----------------------------------------------------------------------------
class ThreadingXMLRPCServer(SocketServer.ThreadingMixIn, _XMLRPCServer):

    server_type = 'threading'
    daemon_threads = False

#-----------------------------------------------------------------------------
#
# Be biased.
#
#-----------------------------------------------------------------------------

XMLRPCServer = ThreadingXMLRPCServer

#-----------------------------------------------------------------------------
if __name__ == '__main__':
    
    try:
        addr = sys.argv[1], int(sys.argv[2])
    except IndexError:
        addr = "localhost", 8081
    
    server = XMLRPCServer('No_Name', addr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print '... interrupted'
