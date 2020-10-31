#!/usr/bin/env python
# encoding: utf-8

from __future__ import unicode_literals

import io
import os
import subprocess
from distutils.cmd import Command

from setuptools import find_packages, setup

HERE = os.path.abspath(os.path.dirname(__file__))


def read_file(*path_parts, **kwargs):
    with io.open(os.path.join(HERE, *path_parts), **kwargs) as f:
        return f.read()


META = {}
exec(read_file('queryable_properties', '__init__.py', mode='rb'), {}, META)


class PytestCommand(Command):
    """
    Distutils command to run tests via pytest in the current environment.
    """
    description = 'Run tests in the current environment using pytest.'
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import py
        return py.test.cmdline.main([])


class ToxCommand(Command):
    """
    Distutils command to run tests via tox, which must be installed and be able
    to access all supported python versions.
    """
    description = ('Run tests using tox, which must already be installed and be able to access all supported python '
                   'versions to create its environments.')
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        return subprocess.call(['tox'])


setup(
    name='django-queryable-properties',
    version=META['__version__'],
    description=META['__doc__'],
    long_description='\n\n'.join((read_file('README.rst', encoding='utf-8'),
                                  read_file('CHANGELOG.rst', encoding='utf-8'))),
    author=META['__author__'],
    author_email=META['__email__'],
    maintainer=META['__maintainer__'],
    maintainer_email=META['__email__'],
    url='https://github.com/W1ldPo1nter/django-queryable-properties',
    license='BSD',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 1.4',
        'Framework :: Django :: 1.5',
        'Framework :: Django :: 1.6',
        'Framework :: Django :: 1.7',
        'Framework :: Django :: 1.8',
        'Framework :: Django :: 1.9',
        'Framework :: Django :: 1.10',
        'Framework :: Django :: 1.11',
        'Framework :: Django :: 2.0',
        'Framework :: Django :: 2.1',
        'Framework :: Django :: 2.2',
        'Framework :: Django :: 3.0',
        'Framework :: Django :: 3.1',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Internet',
    ],
    packages=find_packages(include='queryable_properties*'),
    include_package_data=True,
    install_requires=[
        'Django>=1.4',
        'six>=1.9',
    ],
    tests_require=[
        'Django>=1.4',
        'six>=1.9',
        'coverage',
        'flake8',
        'mock',
        'pytest',
        'pytest-cov',
        'pytest-django',
        'pytest-pythonpath',
    ],
    cmdclass={
        'test': PytestCommand,
        'tox': ToxCommand,
    }
)
