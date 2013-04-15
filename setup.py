from setuptools import setup
import os
import thing

setup(
    name = thing.__name__,
    version = thing.__version__,
    url = 'http://github.com/lzyy/thing',
    license = thing.__license__,
    author = thing.__author__,
    author_email = 'healdream@gmail.com',
    description = 'lightweight SQLAlchemy based ORM',
    long_description = open('README.md').read(),
    zip_safe = False,
    platforms = 'any',
    packages = ["thing"],
    include_package_data = True,
    install_requires = [
        'sqlalchemy',
        'mysql-python',
        'redis >= 2.7, <= 2.8',
    ],
    classifiers = [
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Database',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)
