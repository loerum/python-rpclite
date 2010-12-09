#-----------------------------------------------------------------------------
#
# XML-RPC server proxy (client).
#
# This code mainly to propagate keyworded agument to the socket layer.
# like: server.get_something(params, timeout=11)
#
#-----------------------------------------------------------------------------
import os
import sys
import logging
import socket
import httplib
from xmlrpclib import * # !!!

assert sys.version[:3] >= '2.3', 'Python version 2.3 or above is required.'

__version__ = "$Revision$"

SocketError = socket.error
SocketTimeout = socket.timeout

logger = logging.getLogger('rpc-client')

#-----------------------------------------------------------------------------
#
# httplib overwrites.
#
#-----------------------------------------------------------------------------
class HTTPConnection(httplib.HTTPConnection):

    # this way of handling socket timeout could be unnecessary in python-2.6
    _jojo_sock_timeout = 0
    
    def send(self, str):
        """Send `str' to the server."""
        if self.sock is None:
            if self.auto_open:
                self.connect()
            else:
                raise NotConnected()
        #
        # Set timeout, we don't need to reset timeout, since socket is only
        # used once.
        #
        if self._jojo_sock_timeout:
            self.sock.settimeout(self._jojo_sock_timeout)

        # Send the data to the server. if we get a broken pipe, then close
        # the socket. we want to reconnect when somebody tries to send again.
        #
        # NOTE: we DO propagate the error, though, because we cannot simply
        #       ignore the error... the caller will know if they can retry.
        logger.debug( "send: %s", repr(str))
        try:
            self.sock.sendall(str)
        except socket.error, v:
            if v[0] == 32:      # Broken pipe
                self.close()
            raise
        
class HTTPSConnection(HTTPConnection, httplib.HTTPSConnection):
    pass

class HTTP(httplib.HTTP):
    _connection_class = HTTPConnection

#-----------------------------------------------------------------------------
#
# xmlrpclib overwrites.
#
#-----------------------------------------------------------------------------
class _JojoTransport(Transport):

    _sock_timeout = 0
    
    def make_connection(self, host):
        # create a HTTP connection object from a host descriptor
        host, extra_headers, x509 = self.get_host_info(host)
        http = HTTP(host)
        http._conn._jojo_sock_timeout = self._sock_timeout
        return http

class _SafeJojoTransport(_JojoTransport, SafeTransport):
    # xmlrpclib say: FIXME, mostly untested
    pass

class _Fault(Fault):
    
    @staticmethod
    def _remove_backslashes(text):
        # tsk, tsk
        for s in ("\\'", '\\"',
                  "\\\'", '\\\"',
                  "\\\\'", '\\\\"',
                  "\\\\\'",'\\\\\"',
                  "\\\\\\'",'\\\\\\"'):
            if text.find(s) != -1:
                text = text.replace(s, s[-1])
        return text        

    # Try to decode servers traceback ... ugly.
    def __repr__(self):        
        try:
            text = repr(self.faultString)
            text, tb = text.split('server-tb: ')
            tb = tb.rstrip('">,\'')
            tb = self._remove_backslashes(tb)
            text = text.rstrip('">, ')
            text = self._remove_backslashes(text)
            text += '">'
            tb = eval(tb)
            text += '\n<< server traceback >>'
            for l in tb:
                text += '\n' + "   File \"%s\", line %d, in %s\n     %s"%l
        except:
            text = repr(self.faultString)
        return (text)

#-----------------------------------------------------------------------------
#
# ServerProxy.
#
# We took it all (from xmlrpclib) and modified it so we can pass keyworded
# arguments.
#
#-----------------------------------------------------------------------------
class _Method:
    # some magic to bind an XML-RPC method to an RPC server.
    # supports "nested" methods (e.g. examples.getStateName)
    def __init__(self, send, name):
        self.__send = send
        self.__name = name
        
    def __getattr__( self, name):
        return _Method(self.__send, "%s.%s" % (self.__name, name))
    
    def __call__(self, *args, **kwargs):
        return self.__send(self.__name, *args, **kwargs)

##
# Standard server proxy.  This class establishes a virtual connection
# to an XML-RPC server.
# <p>
# This class is available as ServerProxy and Server.  New code should
# use ServerProxy, to avoid confusion.
#
# @def ServerProxy(uri, **options)
# @param uri The connection point on the server.
# @keyparam transport A transport factory, compatible with the
#    standard transport class.
# @keyparam encoding The default encoding used for 8-bit strings
#    (default is UTF-8).
# @keyparam verbose Use a true value to enable debugging output.
#    (printed to standard output).
# @see Transport

class XMLRPCServerProxy:
    """uri [,options] -> a logical connection to an XML-RPC server

    uri is the connection point on the server, given as
    scheme://host/target.

    The standard implementation always supports the "http" scheme.  If
    SSL socket support is available (Python 2.0), it also supports
    "https".

    If the target part and the slash preceding it are both omitted,
    "/RPC2" is assumed.

    The following options can be given as keyword arguments:

        transport: a transport factory
        encoding: the request encoding (default is UTF-8)

    All 8-bit strings passed to the server proxy are assumed to use
    the given encoding.
    """

    def __init__(self, uri, encoding=None, verbose=0, allow_none=0):
        # establish a "logical" server connection

        # get the url
        import urllib
        type, uri = urllib.splittype(uri)
        if type not in ("http", "https"):
            raise IOError, "unsupported XML-RPC protocol"
        self.__host, self.__handler = urllib.splithost(uri)
        if not self.__handler:
            self.__handler = "/RPC2"

        if type == "https":
            transport = _SafeJojoTransport()
        else:
            transport = _JojoTransport()
        self.__transport = transport

        self.__encoding = encoding
        self.__verbose = verbose
        self.__allow_none = allow_none
        self.__timeout = socket.getdefaulttimeout()

    def __request(self, methodname, *params, **kwargs):
        # call a method on the remote server

        timeout = kwargs.pop('timeout', self.__timeout)
        if kwargs:
            raise TypeError("got unexpected keyword argument %r" % (kwargs.keys()[0],))

        request = dumps(params, methodname, encoding=self.__encoding,
                        allow_none=self.__allow_none)

        # cheap
        self.__transport._sock_timeout = timeout
        
        try:
            response = self.__transport.request(
                self.__host,
                self.__handler,
                request,
                verbose=self.__verbose
                )
        except Fault:
            exc_type, exc_value, exc_tb = sys.exc_info()
            raise _Fault(1, exc_value)
            

        if len(response) == 1:
            response = response[0]

        return response
    
    def __repr__(self):
        return (
            "<ServerProxy for %s%s>" %
            (self.__host, self.__handler)
            )

    __str__ = __repr__

    def __getattr__(self, name):
        # magic method dispatcher
        return _Method(self.__request, name)

    def set_defaulttimeout(self, timeout):
        self.__timeout = timeout
        
    def get_defaulttimeout(self):
        return self.__timeout
        
    # note: to call a remote object with an non-standard name, use
    # result getattr(server, "strange-python-name")(args)

