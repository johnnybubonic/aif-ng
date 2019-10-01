import setuptools

with open('README', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
        name = 'aif',
        version = '0.2.0',
        author = 'Brent S.',
        author_email = 'bts@square-r00t.net',
        description = 'Arch Installation Framework (Next Generation)',
        long_description = long_description,
        long_description_content_type = 'text/plain',
        url = 'https://aif-ng.io',
        packages = setuptools.find_packages(),
        classifiers = ['Programming Language :: Python :: 3',
                       'Programming Language :: Python :: 3.6',
                       'Programming Language :: Python :: 3.7',
                       'Programming Language :: Python :: 3.8',
                       'Programming Language :: Python :: 3.9',
                       'Programming Language :: Python :: 3 :: Only',
                       'Operating System :: POSIX :: Linux',
                       'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
                       'Intended Audience :: Developers',
                       'Intended Audience :: Information Technology',
                       'Topic :: Software Development :: Build Tools',
                       'Topic :: Software Development :: Testing',
                       'Topic :: System :: Installation/Setup',
                       'Topic :: System :: Recovery Tools'],
        python_requires = '>=3.6',
        project_urls = {'Documentation': 'https://aif-ng.io/',
                        'Source': 'https://git.square-r00t.net/AIF-NG/',
                        'Tracker': 'https://bugs.square-r00t.net/index.php?project=9'},
        install_requires = ['gpg', 'requests', 'lxml', 'psutil', 'pyparted', 'pytz', 'passlib', 'validators']
        )
