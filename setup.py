try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name='satfire',
    version='0.0.1',
    description='Tools for geospatial analysis and remote sensing',
    author='Chris Waigl',
    author_email='chris.waigl@gmail.com',
    url='https://github.com/chryss/satfire',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Education',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Topic :: Scientific/Engineering :: GIS',
    ],
    license='MIT',
    install_requires=[
          'pygaarst',
    ],
    packages=['satfire'],
)