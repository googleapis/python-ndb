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
        assert adapter.cache_key(key) == "NDB9:agd0ZXN0aW5ncg4LEghTb21lS2luZBh7DA"

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_cache_key_with_ns():
        adapter = remote_cache.RemoteCacheAdapter()
        key = key_module.Key("SomeKind", 123, namespace="ns")
        assert adapter.cache_key(key) == "ns:NDB9:agd0ZXN0aW5ncg4LEghTb21lS2luZBh7DKIBAm5z"

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
