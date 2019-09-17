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

try:
    from unittest import mock
except ImportError:
    import mock

from google.cloud.ndb import _remote
from google.cloud.ndb import tasklets


class TestRemoteCall:
    @staticmethod
    def test_constructor():
        call = _remote.RemoteCall("future", "info")
        assert call.future == "future"
        assert call.info == "info"

    @staticmethod
    def test_repr():
        call = _remote.RemoteCall(None, "a remote call")
        assert repr(call) == "a remote call"

    @staticmethod
    def test_exception():
        error = Exception("Spurious error")
        future = tasklets.Future()
        future.set_exception(error)
        call = _remote.RemoteCall(future, "testing")
        assert call.exception() is error

    @staticmethod
    def test_result():
        future = tasklets.Future()
        future.set_result("positive")
        call = _remote.RemoteCall(future, "testing")
        assert call.result() == "positive"

    @staticmethod
    def test_add_done_callback():
        future = tasklets.Future()
        call = _remote.RemoteCall(future, "testing")
        callback = mock.Mock(spec=())
        call.add_done_callback(callback)
        future.set_result(None)
        callback.assert_called_once_with(future)
