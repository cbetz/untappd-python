from setuptools import setup, find_packages

import untappd
version = str(untappd.__version__)

setup(
    name='untappd',
    version=version,
    author='Christopher Betz',
    author_email='christopherwilliambetz@gmail.com',
    url='https://github.com/cbetz/untappd-python',
    description='Untappd wrapper library',
    long_description=open('./README.txt', 'r').read(),
    download_url='https://github.com/cbetz/untappd-python/tarball/master',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'License :: OSI Approved :: MIT License',
        ],
    packages=find_packages(),
    install_requires=[
        'requests',
        'future',
    ],
    license='MIT License',
    keywords='untappd api',
    include_package_data=True,
    zip_safe=True,
)
