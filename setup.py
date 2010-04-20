from setuptools import setup, Extension

setup(name='python-rpclite',
      version='0.2',
      description='DMI/TI, XML-RPC client.',
      author='Lars Orum',
      author_email='ras@dmi.dk',
      maintainer='Lars Orum',
      maintainer_email='ras@dmi.dk',
      package_dir={'rpclite': '.'},
      packages=['rpclite'],
      test_suite = 'nose.collector',
     )
