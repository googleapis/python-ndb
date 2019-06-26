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

import collections


class ContextCache(collections.UserDict):
    """A per-context in-memory entity cache.

    This cache verifies the fetched entity has the correct key before
    returning a result, in order to handle cases where the entity's key was
    modified but the cache's key was not updated.
    """
    def get_and_validate(self, key):
        """Verify that the entity's key has not changed since it was added
           to the cache. If it has changed, consider this a cache miss.
           See issue 13.  http://goo.gl/jxjOP"""
        entity = self.data[key]  # May be None, meaning "doesn't exist".
        if entity is None or entity._key == key:
            return entity
        else:
            del self.data[key]
            raise KeyError(key)


class GlobalCache:
    """Abstract base class for a global entity cache.

    A global entity cache is shared across contexts, sessions, and possibly
    even servers. Concrete implementations are available which use Redis, or
    GAE Memcache.
    """

    def get(self, key):
        """Retreive an entity from the cache.

        Arguments:
            key (bytes): Serialized protocol buffer of key.

        Returns:
            Optional[bytes]: Serialized protocol buffer of entity, or
                :data:`None`.
        """
        raise NotImplementedError

    def set(self, key, entity):
        """Stores an entity in the cache.

        Arguments:
            key (bytes): Serialized protocol buffer of key.
            entity (bytes): Serialized protocol buffer of entity.
        """
        raise NotImplementedError

    def invalidate(self, key):
        """Remove an entity from the cache.

        Arguments:
            key (bytes): Serialized protocol buffer of key.
        """
        raise NotImplementedError
