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

"""A class for information about remote calls."""

# In its own module to avoid circular import between _datastore_api and
# tasklets modules.


class RemoteCall:
    """Represents a remote call.

    This is primarily a wrapper for futures returned by gRPC. This holds some
    information about the call to make debugging easier. Can be used for
    anything that returns a future for something running outside of our own
    event loop.

    Arguments:
        future (Union[grpc.Future, tasklets.Future]): The future handed back
            from initiating the call.
        info (str): Helpful human readable string about the call. This string
            will be handed back verbatim by calls to :meth:`__repr__`.
    """

    def __init__(self, future, info):
        self.future = future
        self.info = info

    def __repr__(self):
        return self.info

    def exception(self):
        """Calls :meth:`grpc.Future.exception` on attr:`future`."""
        return self.future.exception()

    def result(self):
        """Calls :meth:`grpc.Future.result` on attr:`future`."""
        return self.future.result()

    def add_done_callback(self, callback):
        """Calls :meth:`grpc.Future.add_done_callback` on attr:`future`."""
        return self.future.add_done_callback(callback)
