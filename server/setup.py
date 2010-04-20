from distutils.core import setup, Extension

setup(name='python-rpclite-server',
      version='0.1',
      description='DMI/TI, XML-RPC server.',
      author='Lars Orum',
      author_email='ras@dmi.dk',
      maintainer='Lars Orum',
      maintainer_email='ras@dmi.dk',
      package_dir={'rpclite/server': '.'},
      packages=['rpclite/server'],
     )
