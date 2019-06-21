# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A client for NDB which manages credentials, project, namespace."""

import contextlib
import os

from google.cloud import environment_vars
from google.cloud import _helpers
from google.cloud import client as google_client
from google.cloud.datastore_v1.gapic import datastore_client

from google.cloud.ndb import context as context_module

DATASTORE_API_HOST = datastore_client.DatastoreClient.SERVICE_ADDRESS.rsplit(
    ":", 1
)[0]


def _get_gcd_project():
    """Gets the GCD application ID if it can be inferred."""
    return os.getenv(environment_vars.GCD_DATASET)


def _determine_default_project(project=None):
    """Determine default project explicitly or implicitly as fall-back.

    In implicit case, supports four environments. In order of precedence, the
    implicit environments are:

    * DATASTORE_DATASET environment variable (for ``gcd`` / emulator testing)
    * GOOGLE_CLOUD_PROJECT environment variable
    * Google App Engine application ID
    * Google Compute Engine project ID (from metadata server)
_
    Arguments:
        project (Optional[str]): The project to use as default.

    Returns:
        Union([str, None]): Default project if it can be determined.
    """
    if project is None:
        project = _get_gcd_project()

    if project is None:
        project = _helpers._determine_default_project(project=project)

    return project


class Client(google_client.ClientWithProject):
    """An NDB client.

    The NDB client must be created in order to use NDB, and any use of NDB must
    be within the context of a call to :meth:`context`.

    Arguments:
        project (Optional[str]): The project to pass to proxied API methods. If
            not passed, falls back to the default inferred from the
            environment.
        namespace (Optional[str]): Namespace to pass to proxied API methods.
        credentials (Optional[:class:`~google.auth.credentials.Credentials`]):
            The OAuth2 Credentials to use for this client. If not passed, falls
            back to the default inferred from the environment.
    """

    SCOPE = ("https://www.googleapis.com/auth/datastore",)
    """The scopes required for authenticating as a Cloud Datastore consumer."""

    def __init__(self, project=None, namespace=None, credentials=None):
        super(Client, self).__init__(project=project, credentials=credentials)
        self.namespace = namespace
        self.host = os.environ.get(
            environment_vars.GCD_HOST, DATASTORE_API_HOST
        )

        # Use insecure connection when using Datastore Emulator, otherwise
        # use secure connection
        emulator = bool(os.environ.get("DATASTORE_EMULATOR_HOST"))
        self.secure = not emulator

    @contextlib.contextmanager
    def context(self, cache_policy=None):
        """Establish a context for a set of NDB calls.

        This method provides a context manager which establishes the runtime
        state for using NDB.

        For example:

        .. code-block:: python

            from google.cloud import ndb

            client = ndb.Client()
            with client.context():
                # Use NDB for some stuff
                pass

        Use of a context is required--NDB can only be used inside a running
        context. The context is used to manage the connection to Google Cloud
        Datastore, an event loop for asynchronous API calls, runtime caching
        policy, and other essential runtime state.

        Code within an asynchronous context should be single threaded.
        Internally, a :class:`threading.local` instance is used to track the
        current event loop.

        In a web application, it is recommended that a single context be used
        per HTTP request. This can typically be accomplished in a middleware
        layer.

        Arguments:
            cache_policy (Optional[Callable[[key.Key], bool]]): The
                cache policy to use in this context. See:
                :meth:`~google.cloud.ndb.context.Context.set_cache_policy`.
        """
        context = context_module.Context(self, cache_policy=cache_policy)
        with context.use():
            yield context

        # Finish up any work left to do on the event loop
        context.eventloop.run()

    @property
    def _http(self):
        """Getter for object used for HTTP transport.

        Raises:
            NotImplementedError: Always, HTTP transport is not supported.
        """
        raise NotImplementedError("HTTP transport is not supported.")

    @staticmethod
    def _determine_default(project):
        """Helper:  override default project detection."""
        return _determine_default_project(project)
