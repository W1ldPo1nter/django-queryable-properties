#!/usr/bin/env python
# encoding: utf-8

from __future__ import unicode_literals

import distutils
import subprocess
from os.path import dirname, join

from setuptools import setup, find_packages


def read(*args):
    return open(join(dirname(__file__), *args)).read()


class ToxTestCommand(distutils.cmd.Command):
    """
    Distutils command to run tests via tox with 'python setup.py test'.

    See https://docs.python.org/3/distutils/apiref.html#creating-a-new-distutils-command
    for more documentation on custom distutils commands.
    """
    description = "Run tests via 'tox'."
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        self.announce("Running tests with 'tox'...", level=distutils.log.INFO)
        return subprocess.call(['tox'])


exec(read('queryable_properties', 'version.py'))

classifiers = """
# The next line is important: it prevents accidental upload to PyPI!
Private :: Do Not Upload
Development Status :: 2 - Pre-Alpha
Programming Language :: Python
Programming Language :: Python :: 2.7
Programming Language :: Python :: 3.5
Programming Language :: Python :: 3.6
Programming Language :: Python :: 3.7
Framework :: Django
Framework :: Django :: 1.11
Framework :: Django :: 2.0
Framework :: Django :: 2.1
Intended Audience :: Developers
License :: Other/Proprietary License
Operating System :: Microsoft :: Windows
Operating System :: POSIX
Operating System :: MacOS :: MacOS X
Topic :: Internet
"""

install_requires = [
    # 'six',
]

tests_require = [
    'coverage',
    'flake8',
    'pydocstyle',
    'pylint',
    'pytest-django',
    'pytest-pep8',
    'pytest-cov',
    'pytest-pythonpath',
    'pytest',
]

setup(
    name='Queryable Properties',
    version=__version__,  # noqa
    description='Use Django model properties in database queries.',
    long_description=read('README.rst'),
    author='Marcus Klöpfel',
    author_email='marcus.kloepfel@gmail.com',
    maintainer='Marcus Klöpfel',
    maintainer_email='marcus.kloepfel@gmail.com',
    url='https://autorelat1ve.po1nter.com/WildPointer/django-queryable-properties',
    license='Proprietary',
    classifiers=[c.strip() for c in classifiers.splitlines()
                 if c.strip() and not c.startswith('#')],
    packages=find_packages(exclude=['tests']),
    include_package_data=True,
    test_suite='tests',
    install_requires=install_requires,
    tests_require=tests_require,
    cmdclass={
        'test': ToxTestCommand,
    }
)
