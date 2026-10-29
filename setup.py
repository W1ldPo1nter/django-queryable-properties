#!/usr/bin/env python
# encoding: utf-8

from __future__ import unicode_literals

import io
import os

from setuptools import find_packages, setup

HERE = os.path.abspath(os.path.dirname(__file__))


def read_file(*path_parts, **kwargs):
    with io.open(os.path.join(HERE, *path_parts), **kwargs) as f:
        return f.read()


META = {}
exec(read_file('queryable_properties', '__init__.py', mode='rb'), {}, META)

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
        'Framework :: Django :: 3.2',
        'Framework :: Django :: 4.0',
        'Framework :: Django :: 4.1',
        'Framework :: Django :: 4.2',
        'Framework :: Django :: 5.0',
        'Framework :: Django :: 5.1',
        'Framework :: Django :: 5.2',
        'Framework :: Django :: 6.0',
        'Framework :: Django :: 6.1',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'Topic :: Internet',
    ],
    packages=find_packages(include='queryable_properties*'),
    include_package_data=True,
    install_requires=[
        'Django>=1.4',
        'six>=1.9',
    ],
)
