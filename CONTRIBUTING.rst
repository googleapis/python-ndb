############
Contributing
############

#. **Please sign one of the contributor license agreements below.**
#. ``python-ndb`` is undergoing heavy development right now, so if you plan to
   implement a feature, please create an issue to discuss your idea first. That
   way we can coordinate and avoid possibly duplicating ongoing work.
#. Fork the repo, develop and test your code changes, add docs.
#. Make sure that your commit messages clearly describe the changes.
#. Send a pull request. (Please Read: `Faster Pull Request Reviews`_)

.. _Faster Pull Request Reviews: https://github.com/kubernetes/community/blob/master/contributors/guide/pull-requests.md#best-practices-for-faster-reviews

.. contents:: Here are some guidelines for hacking on ``python-ndb``.

***************
Adding Features
***************

In order to add a feature to ``python-ndb``:

- The feature must be documented in both the API and narrative
  documentation (in ``docs/``).

- The feature must work fully on the following CPython versions:
  3.7, 3.8, 3.9, 3.10, 3.11, 3.12 and 3.13 on both UNIX and Windows.

- The feature must not add unnecessary dependencies (where
  "unnecessary" is of course subjective, but new dependencies should
  be discussed).

****************************
Using a Development Checkout
****************************

You'll have to create a development environment to hack on
``python-ndb``, using a Git checkout:

- While logged into your GitHub account, navigate to the
  ``python-ndb`` `repo`_ on GitHub.

- Fork and clone the ``python-ndb`` repository to your GitHub account by
  clicking the "Fork" button.

- Clone your fork of ``python-ndb`` from your GitHub account to your local
  computer, substituting your account username and specifying the destination
  as ``hack-on-python-ndb``.  E.g.::

   $ cd ${HOME}
   $ git clone git@github.com:USERNAME/python-ndb.git hack-on-python-ndb
   $ cd hack-on-python-ndb
   # Configure remotes such that you can pull changes from the python-ndb
   # repository into your local repository.
   $ git remote add upstream git@github.com:googleapis/python-ndb.git
   # fetch and merge changes from upstream into main
   $ git fetch upstream
   $ git merge upstream/main

Now your local repo is set up such that you will push changes to your GitHub
repo, from which you can submit a pull request.

To work on the codebase and run the tests, we recommend using ``nox``,
but you can also use a ``virtualenv`` of your own creation.

.. _repo: https://github.com/googleapis/python-ndb

Using ``nox``
=============

We use `nox <https://nox.readthedocs.io/en/latest/>`__ to instrument our tests.

- To test your changes, run unit tests with ``nox``::

    $ nox -s unit-3.10
    $ nox -s unit-3.7
    $ ...

.. nox: https://pypi.org/project/nox-automation/

- To run unit tests that use Memcached or Redis, you must have them running and set the appropriate environment variables:

    $ export MEMCACHED_HOSTS=localhost:11211
    $ export REDIS_CACHE_URL=redis://localhost:6379


Note on Editable Installs / Develop Mode
========================================

- As mentioned previously, using ``setuptools`` in `develop mode`_
  or a ``pip`` `editable install`_ is not possible with this
  library. This is because this library uses `namespace packages`_.
  For context see `Issue #2316`_ and the relevant `PyPA issue`_.

  Since ``editable`` / ``develop`` mode can't be used, packages
  need to be installed directly. Hence your changes to the source
  tree don't get incorporated into the **already installed**
  package.

.. _namespace packages: https://www.python.org/dev/peps/pep-0420/
.. _Issue #2316: https://github.com/googleapis/google-cloud-python/issues/2316
.. _PyPA issue: https://github.com/pypa/packaging-problems/issues/12
.. _develop mode: https://setuptools.readthedocs.io/en/latest/setuptools.html#development-mode
.. _editable install: https://pip.pypa.io/en/stable/reference/pip_install/#editable-installs

*****************************************
I'm getting weird errors... Can you help?
*****************************************

If the error mentions ``Python.h`` not being found,
install ``python-dev`` and try again.
On Debian/Ubuntu::

  $ sudo apt-get install python-dev

************
Coding Style
************

- PEP8 compliance, with exceptions defined in the linter configuration.
  If you have ``nox`` installed, you can test that you have not introduced
  any non-compliant code via::

   $ nox -s lint

- In order to make ``nox -s lint`` run faster, you can set some environment
  variables::

   export GOOGLE_CLOUD_TESTING_REMOTE="upstream"
   export GOOGLE_CLOUD_TESTING_BRANCH="main"

  By doing this, you are specifying the location of the most up-to-date
  version of ``python-ndb``. The the suggested remote name ``upstream``
  should point to the official ``googleapis`` checkout and the
  the branch should be the main branch on that remote (``main``).

Exceptions to PEP8:

- Many unit tests use a helper method, ``_call_fut`` ("FUT" is short for
  "Function-Under-Test"), which is PEP8-incompliant, but more readable.
  Some also use a local variable, ``MUT`` (short for "Module-Under-Test").

********************
Running System Tests
********************

- To run system tests for a given package, you can execute::

   $ export SYSTEM_TESTS_DATABASE=system-tests-named-db
   $ nox -e system

  .. note::

      System tests are only configured to run under Python 3.8. For
      expediency, we do not run them in older versions of Python 3.

  This alone will not run the tests. You'll need to change some local
  auth settings and change some configuration in your project to
  run all the tests.

- System tests may be run against the emulator. To do this, set the
  ``DATASTORE_EMULATOR_HOST`` environment variable. Alternatively,
  system tests with the emulator can run with
  `nox -e emulator-system-PYTHON_VERSION`

- System tests will be run against an actual project and
  so you'll need to provide some environment variables to facilitate
  authentication to your project:

  - ``GOOGLE_APPLICATION_CREDENTIALS``: The path to a JSON key file;
    see ``system_tests/app_credentials.json.sample`` as an example. Such a file
    can be downloaded directly from the developer's console by clicking
    "Generate new JSON key". See private key
    `docs <https://cloud.google.com/storage/docs/authentication#generating-a-private-key>`__
    for more details.

  - In order for Logging system tests to work, the Service Account
    will also have to be made a project ``Owner``. This can be changed under
    "IAM & Admin". Additionally, ``cloud-logs@google.com`` must be given
    ``Editor`` permissions on the project.

- For datastore tests, you'll need to create composite
  `indexes <https://cloud.google.com/datastore/docs/tools/indexconfig>`__
  with the ``gcloud`` command line
  `tool <https://developers.google.com/cloud/sdk/gcloud/>`__::

   # Install the app (App Engine Command Line Interface) component.
   $ gcloud components install app-engine-python

   # Authenticate the gcloud tool with your account.
   $ GOOGLE_APPLICATION_CREDENTIALS="path/to/app_credentials.json"
   $ gcloud auth activate-service-account \
   > --key-file=${GOOGLE_APPLICATION_CREDENTIALS}

   # Create the indexes
   $ gcloud datastore indexes create tests/system/index.yaml
   $ gcloud alpha datastore indexes create --database=$SYSTEM_TESTS_DATABASE tests/system/index.yaml


*************
Test Coverage
*************

- The codebase *must* have 100% test statement coverage after each commit.
  You can test coverage via ``nox -s cover``.

******************************************************
Documentation Coverage and Building HTML Documentation
******************************************************

If you fix a bug, and the bug requires an API or behavior modification, all
documentation in this package which references that API or behavior must be
changed to reflect the bug fix, ideally in the same commit that fixes the bug
or adds the feature.

To build and review docs (where ``${VENV}`` refers to the virtualenv you're
using to develop ``python-ndb``):

#. After following the steps above in "Using a Development Checkout", install
   Sphinx and all development requirements in your virtualenv::

     $ cd ${HOME}/hack-on-python-ndb
     $ ${VENV}/bin/pip install Sphinx

#. Change into the ``docs`` directory within your ``python-ndb`` checkout and
   execute the ``make`` command with some flags::

     $ cd ${HOME}/hack-on-python-ndb/docs
     $ make clean html SPHINXBUILD=${VENV}/bin/sphinx-build

   The ``SPHINXBUILD=...`` argument tells Sphinx to use the virtualenv Python,
   which will have both Sphinx and ``python-ndb`` (for API documentation
   generation) installed.

#. Open the ``docs/_build/html/index.html`` file to see the resulting HTML
   rendering.

As an alternative to 1. and 2. above, if you have ``nox`` installed, you
can build the docs via::

   $ nox -s docs

********************************************
Note About ``README`` as it pertains to PyPI
********************************************

The `description on PyPI`_ for the project comes directly from the
``README``. Due to the reStructuredText (``rst``) parser used by
PyPI, relative links which will work on GitHub (e.g. ``CONTRIBUTING.rst``
instead of
``https://github.com/googleapis/python-ndb/blob/main/CONTRIBUTING.rst``)
may cause problems creating links or rendering the description.

.. _description on PyPI: https://pypi.org/project/google-cloud/


*************************
Supported Python Versions
*************************

We support:

-  `Python 3.7`_
-  `Python 3.8`_
-  `Python 3.9`_
-  `Python 3.10`_
-  `Python 3.11`_
-  `Python 3.12`_
-  `Python 3.13`_

.. _Python 3.7: https://docs.python.org/3.7/
.. _Python 3.8: https://docs.python.org/3.8/
.. _Python 3.9: https://docs.python.org/3.9/
.. _Python 3.10: https://docs.python.org/3.10/
.. _Python 3.11: https://docs.python.org/3.11/
.. _Python 3.12: https://docs.python.org/3.12/
.. _Python 3.13: https://docs.python.org/3.13/


Supported versions can be found in our ``noxfile.py`` `config`_.

.. _config: https://github.com/googleapis/python-ndb/blob/main/noxfile.py


**********
Versioning
**********

This library follows `Semantic Versioning`_.

.. _Semantic Versioning: http://semver.org/

Some packages are currently in major version zero (``0.y.z``), which means that
anything may change at any time and the public API should not be considered
stable.

******************************
Contributor License Agreements
******************************

Before we can accept your pull requests you'll need to sign a Contributor
License Agreement (CLA):

- **If you are an individual writing original source code** and **you own the
  intellectual property**, then you'll need to sign an
  `individual CLA <https://developers.google.com/open-source/cla/individual>`__.
- **If you work for a company that wants to allow you to contribute your work**,
  then you'll need to sign a
  `corporate CLA <https://developers.google.com/open-source/cla/corporate>`__.

You can sign these electronically (just scroll to the bottom). After that,
we'll be able to accept your pull requests.
