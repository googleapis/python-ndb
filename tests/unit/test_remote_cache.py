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


import pytest

from google.cloud.ndb import key as key_module
from google.cloud.ndb import remote_cache
import tests.unit.utils


def test___all__():
    tests.unit.utils.verify___all__(remote_cache)


class TestAdapter:
    @staticmethod
    def test_constructor():
        adapter = remote_cache.RemoteCacheAdapter()
        assert isinstance(adapter, remote_cache.RemoteCacheAdapter)

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_cache_key():
        adapter = remote_cache.RemoteCacheAdapter()
        key = key_module.Key("SomeKind", 123)
        key_str = "NDB9:agd0ZXN0aW5ncg4LEghTb21lS2luZBh7DA"
        assert adapter.cache_key(key) == key_str

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_cache_key_with_ns():
        adapter = remote_cache.RemoteCacheAdapter()
        key = key_module.Key("SomeKind", 123, namespace="ns")
        key_str = "ns:NDB9:agd0ZXN0aW5ncg4LEghTb21lS2luZBh7DKIBAm5z"
        assert adapter.cache_key(key) == key_str

    @staticmethod
    def test_cache_get_multi():
        adapter = remote_cache.RemoteCacheAdapter()
        with pytest.raises(NotImplementedError):
            adapter.cache_get_multi(["a"])

    @staticmethod
    def test_cache_set_multi():
        adapter = remote_cache.RemoteCacheAdapter()
        with pytest.raises(NotImplementedError):
            adapter.cache_set_multi({"a": "b"})

    @staticmethod
    def test_cache_start_cas_multi():
        adapter = remote_cache.RemoteCacheAdapter()
        with pytest.raises(NotImplementedError):
            adapter.cache_start_cas_multi(["a"])

    @staticmethod
    def test_cache_cas_multi():
        adapter = remote_cache.RemoteCacheAdapter()
        with pytest.raises(NotImplementedError):
            adapter.cache_cas_multi({"a": "b"})

    @staticmethod
    def test_cache_delete_multi():
        adapter = remote_cache.RemoteCacheAdapter()
        with pytest.raises(NotImplementedError):
            adapter.cache_delete_multi(["a"])


class Test__get_batch:
    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_get_new_batch():
        kls = remote_cache._RemoteCacheGetBatch
        options = {"a": "b"}
        assert isinstance(remote_cache._get_batch(kls, options), kls)

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_get_cached_batch(in_context):
        kls = remote_cache._RemoteCacheGetBatch
        options = {"a": "b"}
        batch = kls(options)
        in_context.batches[kls] = {(("a", "b"), ): batch}

        assert remote_cache._get_batch(kls, options) == batch


class Test_remote_cache_available:
    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_remote_cache_unavailable(in_context):
        assert not remote_cache.remote_cache_available()

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_remote_cache_available(in_context):
        with in_context.new(remote_cache="remote_cache").use():
            assert remote_cache.remote_cache_available()

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_cache_action_done_with_remote_cache_unavailable(in_context):
        key = "key"
        value = "value"
        assert remote_cache.cache_get(key).done()
        assert remote_cache.cache_set(key, value).done()
        assert remote_cache.cache_set_locked(key).done()
        assert remote_cache.cache_start_cas(key).done()
        assert remote_cache.cache_cas(key, value).done()
        assert remote_cache.cache_delete(key).done()

