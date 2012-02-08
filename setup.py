from setuptools import setup

setup(
    name='Thing',
    version='0.1',
    url='http://github.com/lzyy/thing/',
    license='BSD',
    author='lzyy',
    author_email='healdream@gmail.com',
    description='a tiny active record orm based on sqlalchemy',
    long_description=__doc__,
    zip_safe=False,
    platforms='any',
    install_requires=[
        'sqlalchemy',
        'blinker',
        'formencode',
        'mysql-python',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Database',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)
