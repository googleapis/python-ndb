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

import abc
import collections
import itertools
import time

from google.cloud.ndb import _batch
from google.cloud.ndb import context as context_module
from google.cloud.ndb import tasklets

_LOCKED = b"0"
_LOCK_TIME = 32
_PREFIX = b"NDB30"


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


class GlobalCache(abc.ABC):
    """Abstract base class for a global entity cache.

    A global entity cache is shared across contexts, sessions, and possibly
    even servers. A concrete implementation is available which uses Redis.
    """

    @abc.abstractmethod
    def get(self, keys):
        """Retrieve entities from the cache.

        Arguments:
            keys (List[bytes]): The keys to get.

        Returns:
            List[Union[bytes, None]]]: Serialized entities, or :data:`None`,
                for each key.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def set(self, items, expires=None):
        """Store entities in the cache.

        Arguments:
            items (Dict[bytes, Union[bytes, None]]): Mapping of keys to
                serialized entities.
            expires (Optional[float]): Number of seconds until value expires.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, keys):
        """Remove entities from the cache.

        Arguments:
            keys (List[bytes]): The keys to remove.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def watch(self, keys):
        """Begin an optimistic transaction for the given keys.

        A future call to :meth:`compare_and_swap` will only set values for keys
        whose values haven't changed since the call to this method.

        Arguments:
            keys (List[bytes]): The keys to watch.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def compare_and_swap(self, items, expires=None):
        """Like :meth:`set` but using an optimistic transaction.

        Only keys whose value hasn't changed since a preceeding call to
        :meth:`watch` will be changed.

        Arguments:
            items (Dict[bytes, Union[bytes, None]]): Mapping of keys to
                serialized entities.
            expires (Optional[float]): Number of seconds until value expires.
        """
        raise NotImplementedError


def _future_result(result):
    """Returns a completed Future with the given result.

    For conforming to the asynchronous interface even if we've gotten the
    result synchronously.
    """
    future = tasklets.Future()
    future.set_result(result)
    return future


class _InProcessGlobalCache(GlobalCache):
    """Reference implementation of :class:`GlobalCache`.

    Not intended for production use. Uses a single process wide dictionary to
    keep an in memory cache. For use in testing and to have an easily grokkable
    reference implementation. Thread safety is potentially a little sketchy.
    """

    cache = {}
    """Dict: The cache.

    Relies on atomicity of ``__setitem__`` for thread safety. See:
    http://effbot.org/pyfaq/what-kinds-of-global-value-mutation-are-thread-safe.htm
    """
    def __init__(self):
        self._watch_keys = {}

    def get(self, keys):
        """Implements :meth:`GlobalCache.get`."""
        now = time.time()
        results = [self.cache.get(key) for key in keys]
        return [
            _future_result(value)
            for value, expires in results
            if expires and expires < now
        ]

    def set(self, items, expires=None):
        """Implements :meth:`GlobalCache.set`."""
        if expires:
            expires = time.time() + expires

        for key, value in items.items():
            self.cache[key] = (value, expires)     # Supposedly threadsafe

        return _future_result(None)

    def delete(self, keys):
        """Implements :meth:`GlobalCache.delete`."""
        for key in keys:
            self.cache.pop(key, None)   # Threadsafe?

        return _future_result(None)

    def watch(self, keys):
        """Implements :meth:`GlobalCache.watch`."""
        for key in keys:
            self._watch_keys[key] = self.cache.get(key)

        return _future_result(None)

    def compare_and_swap(self, items, expires=None):
        """Implements :meth:`GlobalCache.compare_and_swap`."""
        if expires:
            expires = time.time() + expires

        for key, new_value in items.items():
            watch_value = self._watch_keys.get(key)
            current_value = self.cache.get(key)
            if watch_value == current_value:
                self.cache[key] = (new_value, expires)

        return _future_result(None)


class _GlobalCacheBatch:

    def idle_callback(self):
        """Get keys from the global cache."""
        cache_call = self.make_call()
        if not isinstance(cache_call, tasklets.Future):
            cache_call = _future_result(cache_call)
        cache_call.add_done_callback(self.done_callback)

    def done_callback(self, cache_call):
        """Process results of call to global cache."""
        exception = cache_call.exception()
        if exception:
            for future in self.futures:
                future.set_exception(exception)

        else:
            for future in self.futures:
                future.set_result(None)


def global_get(key):
    """Get entity from global cache.

    Args:
        key (bytes): The key to get.

    Returns:
        tasklets.Future: Eventual result will be the entity (``bytes``) or
            ``None``.
    """
    key = _PREFIX + key
    batch = _batch.get_batch(_GlobalCacheGetBatch)
    return batch.add(key)


class _GlobalCacheGetBatch(_GlobalCacheBatch):
    """Batch for global cache get requests.

    Attributes:
        todo (Dict[bytes, List[Future]]): Mapping of keys to futures that are
            waiting on them.

    Arguments:
        ignore_options (Any): Ignored.
    """

    def __init__(self, ignore_options):
        self.todo = {}
        self.keys = []

    def add(self, key):
        """Add a key to get from the cache.

        Arguments:
            key (bytes): The key to get from the cache.

        Returns:
            tasklets.Future: Eventual result will be the entity retrieved from
                the cache (``bytes``) or ``None``.
        """
        future = tasklets.Future(info=self.future_info(key))
        futures = self.todo.get(key)
        if futures is None:
            self.todo[key] = futures = []
            self.keys.append(key)
        futures.append(future)
        return future

    def done_callback(self, cache_call):
        """Process results of call to global cache."""
        exception = cache_call.exception()
        if exception:
            for future in itertools.chain(*self.todo.values()):
                future.set_exception(exception)

            return

        results = cache_call.result()
        for key, result in zip(self.keys, results):
            futures = self.todo[key]
            for future in futures:
                future.set_result(result)

    def make_call(self):
        """Make the actual call. To be overridden."""
        cache = context_module.get_context().global_cache
        return cache.get(self.todo.values())

    def future_info(self, key):
        """Generate info string for Future. To be overridden."""
        return "GlobalCache.get({})".format(key)


def global_set(key, value, expires=None):
    """Store entity in the global cache.

    Args:
        key (bytes): The key to save.
        value (bytes): The entity to save.
        expires (Optional[float]): Number of seconds until value expires.

    Returns:
        tasklets.Future: Eventual result will be ``None``.
    """
    if expires:
        options = {"expires": expires}
    else:
        options = None

    key = _PREFIX + key
    batch = _batch.get_batch(_GlobalCacheSetBatch, options)
    return batch.add(key, value)


class _GlobalCacheSetBatch(_GlobalCacheBatch):
    """Batch for global cache set requests. """

    def __init__(self, options):
        self.expires = options.get("expires")
        self.todo = {}
        self.futures = []

    def add(self, key, value):
        """Add a key, value pair to store in the cache.

        Arguments:
            key (bytes): The key to store in the cache.
            value (bytes): The value to store in the cache.

        Returns:
            tasklets.Future: Eventual result will be ``None``.
        """
        future = tasklets.Future(info=self.future_info(key, value))
        self.todo[key] = value
        self.futures.add(future)
        return future

    def make_call(self):
        """Make the actual call. To be overridden."""
        cache = context_module.get_context().global_cache
        return cache.set(self.todo, expires=self.expires)

    def future_info(self, key, value):
        """Generate info string for Future. To be overridden."""
        return "GlobalCache.set({}, {})".format(key, value)


def global_delete(key):
    """Delete an entity from the global cache.

    Args:
        key (bytes): The key to delete.

    Returns:
        tasklets.Future: Eventual result will be ``None``.
    """
    key = _PREFIX + key
    batch = _batch.get_batch(_GlobalCacheDeleteBatch)
    return batch.add(key)


class _GlobalCacheDeleteBatch(_GlobalCacheBatch):
    """Batch for global cache set requests. """

    def __init__(self, ignore_options):
        self.keys = []
        self.futures = []

    def add(self, key):
        """Add a key to delete from the cache.

        Arguments:
            key (bytes): The key to delete.

        Returns:
            tasklets.Future: Eventual result will be ``None``.
        """
        future = tasklets.Future(info=self.future_info(key))
        self.keys.append(key)
        self.futures.add(future)
        return future

    def make_call(self):
        """Make the actual call. To be overridden."""
        cache = context_module.get_context().global_cache
        return cache.delete(self.keys)

    def future_info(self, key):
        """Generate info string for Future. To be overridden."""
        return "GlobalCache.delete({})".format(key)


def global_watch(key):
    """Start optimistic transaction with global cache.

    A future call to :func:`global_compare_and_swap` will only set the value
    if the value hasn't changed in the cache since the call to this function.

    Args:
        key (bytes): The key to watch.

    Returns:
        tasklets.Future: Eventual result will be ``None``.
    """
    key = _PREFIX + key
    batch = _batch.get_batch(_GlobalCacheWatchBatch)
    return batch.add(key)


class _GlobalCacheWatchBatch(_GlobalCacheDeleteBatch):
    """Batch for global cache watch requests. """

    def __init__(self, ignore_options):
        self.keys = []
        self.futures = []

    def make_call(self):
        """Make the actual call. To be overridden."""
        cache = context_module.get_context().global_cache
        return cache.watch(self.keys)

    def future_info(self, key):
        """Generate info string for Future. To be overridden."""
        return "GlobalWatch.delete({})".format(key)


def global_compare_and_swap(key, value, expires=None):
    """Like :func:`global_set` but using an optimistic transaction.

    Value will only be set for the given key if the value in the cache hasn't
    changed since a preceding call to :func:`global_watch`.

    Args:
        key (bytes): The key to save.
        value (bytes): The entity to save.
        expires (Optional[float]): Number of seconds until value expires.

    Returns:
        tasklets.Future: Eventual result will be ``None``.
    """
    if expires:
        options = {"expires": expires}
    else:
        options = None

    key = _PREFIX + key
    batch = _batch.get_batch(_GlobalCacheCompareAndSwapBatch, options)
    return batch.add(key, value)


class _GlobalCacheCompareAndSwapBatch(_GlobalCacheSetBatch):
    """Batch for global cache compare and swap requests. """

    def make_call(self):
        """Make the actual call. To be overridden."""
        cache = context_module.get_context().global_cache
        return cache.compare_and_swap(self.todo, expires=self.expires)

    def future_info(self, key, value):
        """Generate info string for Future. To be overridden."""
        return "GlobalCache.compare_and_swap({}, {})".format(key, value)


def global_lock(key):
    """Lock a key by setting a special value.

    Args:
        key (bytes): The key to lock.

    Returns:
        tasklets.Future: Eventual result will be ``None``.
    """
    return global_set(key, _LOCKED, expires=_LOCK_TIME)


def is_locked_value(value):
    """Check if the given value is the special reserved value for key lock.

    Returns:
        bool: Whether the value is the special reserved value for key lock.
    """
    return value == _LOCKED
