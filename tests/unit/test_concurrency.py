# Copyright 2021 Google LLC
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

import logging
import os

import pytest

try:
    from unittest import mock
except ImportError:  # pragma: NO PY3 COVER
    import mock

from google.cloud.ndb import _cache
from google.cloud.ndb import global_cache as global_cache_module
from google.cloud.ndb import tasklets

from . import orchestrate

log = logging.getLogger(__name__)


def cache_factories():
    yield global_cache_module._InProcessGlobalCache

    def redis_cache():
        return global_cache_module.RedisCache.from_environment()

    if os.environ.get("REDIS_CACHE_URL"):
        yield redis_cache

    def memcache_cache():
        return global_cache_module.MemcacheCache.from_environment()

    if os.environ.get("MEMCACHED_HOSTS"):
        yield global_cache_module.MemcacheCache.from_environment


@pytest.mark.parametrize("cache_factory", cache_factories())
@mock.patch("google.cloud.ndb._cache._syncpoint_update_key", orchestrate.syncpoint)
def test_global_cache_concurrent_write_692(cache_factory, context_factory):
    """Regression test for #692

    https://github.com/googleapis/python-ndb/issues/692
    """
    key = b"somekey"

    @tasklets.synctasklet
    def lock_unlock_key():
        lock = yield _cache.global_lock_for_write(key)
        cache_value = yield _cache.global_get(key)
        assert lock in cache_value

        yield _cache.global_unlock_for_write(key, lock)
        cache_value = yield _cache.global_get(key)
        assert lock not in cache_value

    def run_test():
        global_cache = cache_factory()
        with context_factory(global_cache=global_cache).use():
            lock_unlock_key()

    orchestrate.orchestrate(run_test, run_test)
