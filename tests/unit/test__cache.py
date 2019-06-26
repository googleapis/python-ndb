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

from unittest import mock

import pytest

from google.cloud.ndb import _cache


class TestContextCache:
    @staticmethod
    def test_get_and_validate_valid():
        cache = _cache.ContextCache()
        test_entity = mock.Mock(_key="test")
        cache["test"] = test_entity
        assert cache.get_and_validate("test") is test_entity

    @staticmethod
    def test_get_and_validate_invalid():
        cache = _cache.ContextCache()
        test_entity = mock.Mock(_key="test")
        cache["test"] = test_entity
        test_entity._key = "changed_key"
        with pytest.raises(KeyError):
            cache.get_and_validate("test")

    @staticmethod
    def test_get_and_validate_none():
        cache = _cache.ContextCache()
        cache["test"] = None
        assert cache.get_and_validate("test") is None

    @staticmethod
    def test_get_and_validate_miss():
        cache = _cache.ContextCache()
        with pytest.raises(KeyError):
            cache.get_and_validate("nonexistent_key")
