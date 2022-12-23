#!/usr/bin/env python

from distutils.core import setup

setup(
  name='dfir-orc-archive-rebuilder',
  version='1.0',
  description='A tools to know what to do with your DFIR-ORC output archive',
  author='Nahotjan',
  url='https://github.com/nahotjan/dfir-orc-archive-rebuilder',

  # Add requirements here.
  install_requires=[
    'py7zr',
  ],

  # Make dfir-orc-archive-rebuilder.py available as standalone script.
  scripts=['dfir-orc-archive-rebuilder.py']
)
