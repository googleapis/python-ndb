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

"""
Classes and functions to interact with remote cache backend.
"""

from google.cloud.datastore_v1.proto import entity_pb2

from google.cloud.ndb import context as context_module
from google.cloud.ndb import _eventloop
from google.cloud.ndb import tasklets

__all__ = [
    "RemoteCacheAdapter",
    "cache_get",
    "cache_set",
    "cache_set_locked",
    "cache_start_cas",
    "cache_cas",
    "cache_delete",
    "is_locked_value",
    "remote_cache_available",
]

_LOCKED = 0
_LOCKED_STR = '0'
_LOCKED_BYTES = b'0'
_LOCK_TIME = 32
_PREFIX = "NDB9"


class RemoteCacheAdapter:
    """Base class for remote cache.

    Child classes are expected to implement actual operation with remote cache
    backend, get, set, delete and cas (check and set).
    NDB backend supports batch operation, so each operation can contain
    several keys or values even if each key are called with single cache_get().
    """

    def cache_key(self, key):
        """Convert a key to string for remote cache.

        Args:
            key (ndb.key.Key): The key to save.

        Returns:
            str: A string to save entity with.
        """
        items = [_PREFIX, key.urlsafe().decode('ascii')]
        ns = key.namespace()
        if ns:
            items.insert(0, ns)
        return ':'.join(items)

    def cache_get_multi(self, keys):
        """Get multiple objects from remote cache.

        Args:
            keys (List[str]): The keys to get.

        Returns:
            List[str]: Fetched values, in the same order as keys.
                Empty results should be None.
        """
        raise NotImplementedError

    def cache_set_multi(self, values, expire=None):
        """Set multiple objects to remote cache.

        Args:
            values (Dict[str, Union[str, None]]): The key-value
                dict to save.
            expire (Union[int, None]): The expiration for this key-value set.

        Returns:
            Dict[str, bool]: The results mapped with keys. True means success.
        """
        raise NotImplementedError

    def cache_start_cas_multi(self, keys):
        """Start optimistic transaction for given keys.
        Note: NDB does not keep the cas result, so each adapter should keep
        information to execute following cas operation.
        (e.g. cas_id for memcache, pipeline for redis)

        Args:
            keys (List[str]): The keys to start transaction with.

        Returns:
            List[bool]: Operation results, in the same order as keys.
        """
        raise NotImplementedError

    def cache_cas_multi(self, values, expire=None):
        """Check and set multiple objects to remote cache.

        Args:
            values (Dict[str, Union[str, None]]): The key-value
                dict to save.
            expire (Union[int, None]): The expiration for this key-value set.

        Returns:
            Dict[str, bool]: The results mapped with keys. True means success.
        """
        raise NotImplementedError

    def cache_delete_multi(self, keys):
        """Delete multiple objects from remote cache.

        Args:
            keys (List[str]): The keys to delete.

        Returns:
            List[str]: Operation results, in the same order as keys.
        """
        raise NotImplementedError


def cache_get(key, **options):
    """Get object from remote cache.

    Args:
        key (ndb.key.Key): The key to get.

    Returns:
        tasklets.Future: A future for the eventual result.
    """
    if not remote_cache_available():
        return _do_nothing_future()
    batch = _get_batch(_RemoteCacheGetBatch, options)
    return batch.add(key, **options)


def cache_set(key, value, **options):
    """Set object to remote cache.

    Args:
        key (ndb.key.Key): The key to save.
        value (ndb.model.Model): The entity to save.

    Returns:
        tasklets.Future: A future for the eventual result.
    """
    if not remote_cache_available():
        return _do_nothing_future()
    batch = _get_batch(_RemoteCacheSetBatch, options)
    return batch.add(key, value, **options)


def cache_set_locked(key, **options):
    """Set a special value for value locking to remote cache.

    Args:
        key (ndb.key.Key): The key to lock.

    Returns:
        tasklets.Future: A future for the eventual result.
    """
    if not remote_cache_available():
        return _do_nothing_future()
    value = _LOCKED
    options = options or {}
    options['expire'] = _LOCK_TIME
    return cache_set(key, value, **options)


def cache_start_cas(key, **options):
    """Start optimistic transaction with remote cache.

    Args:
        key (ndb.key.Key): The key to start cas.

    Returns:
        tasklets.Future: A future for the eventual result.
    """
    if not remote_cache_available():
        return _do_nothing_future()
    batch = _get_batch(_RemoteCacheStartCasBatch, options)
    return batch.add(key, **options)


def cache_cas(key, value, **options):
    """Check and set object to remote cache.

    Args:
        key (ndb.key.Key): The key to save.
        value (ndb.model.Model): The entity to save.

    Returns:
        tasklets.Future: A future for the eventual result.
    """
    if not remote_cache_available():
        return _do_nothing_future()
    batch = _get_batch(_RemoteCacheCasBatch, options)
    return batch.add(key, value, **options)


def cache_delete(key, **options):
    """Delete object from remote cache.

    Args:
        key (ndb.key.Key): The key to delete.

    Returns:
        tasklets.Future: A future for the eventual result.
    """
    if not remote_cache_available():
        return _do_nothing_future()
    batch = _get_batch(_RemoteCacheDeleteBatch, options)
    return batch.add(key, **options)


def _do_nothing_future():
    """Get a future for the immediate blank result.

    Returns:
        tasklets.Future: A future for the immediate result.
    """
    future = tasklets.Future()
    future.set_result(None)
    return future


def remote_cache_available():
    """Check if the remote cache is registered in this context.

    Returns:
        bool: Whether a remote cache backend is availble or not.
    """
    return context_module.get_context().remote_cache is not None


def is_locked_value(value):
    """Check if the given value is the special reserved value for value lock.

    Returns:
        bool: Whether the value is the special reserved value for value lock.
    """
    return value in (_LOCKED, _LOCKED_STR, _LOCKED_BYTES)


def _get_batch(batch_cls, options):
    """Gets a data structure for storing batched calls to remote cache operation.

    The batch data structure is stored in the current context. If there is
    not already a batch started, a new structure is created and an idle
    callback is added to the current event loop which will eventually perform
    the batch operation.

    Args:
        batch_cls (type): Class representing the kind of operation being
            batched.
        options (_options.Options): The options for the request. Calls with
            different options will be placed in different batches.

    Returns:
        batch_cls: An instance of the batch class.
    """
    context = context_module.get_context()
    batches = context.batches.get(batch_cls)
    if batches is None:
        context.batches[batch_cls] = batches = {}

    options_key = tuple(
        sorted(
            (
                (key, value)
                for key, value in options.items()
                if value is not None
            )
        )
    )
    batch = batches.get(options_key)
    if batch is not None:
        return batch

    def idle():
        batch = batches.pop(options_key)
        batch.idle_callback()

    batches[options_key] = batch = batch_cls(options)
    _eventloop.add_idle(idle)
    return batch


class _RemoteCacheGetBatch:
    """Batch for remote cahce get requests.

    Attributes:
        options (Dict[str, Any]): See Args.
        todo (Dict[str, List[tasklets.Future]]: Mapping of serialized key
            protocol buffers to dependent futures.

    Args:
        options (_options.Options): The options for the request. Calls with
            different options will be placed in different batches.
    """

    def __init__(self, options):
        self.options = options
        self.todo = {}

    def future_info(self, key):
        """Information passed to tasklets.Future.

        Args:
            key (ndb.key.Key): The key to get info.

        Returns:
            str: Info to passed to tasklets.Future.
        """
        return "cache_get({})".format(key)

    def execute(self, adapter, keys):
        """Batch operation implementation.

        Args:
            adapter (ndb.RemoteCacheAdapter): The adapter to do the operation.
            keys (List[str]): The keys to do the operation with.

        Returns:
            Any: Operation result.
        """
        return adapter.cache_get_multi(keys)

    def add(self, key):
        """Add a key to the batch.

        Args:
            key (ndb.key.Key): The key to be added.

        Returns:
            tasklets.Future: A future for the eventual result.
        """
        future = tasklets.Future(info=self.future_info(key))
        adapter = context_module.get_context().remote_cache
        todo_key = adapter.cache_key(key)
        self.todo.setdefault(todo_key, []).append(future)
        return future

    def idle_callback(self):
        """Perform a remote cache operation on all batched requests."""
        from google.cloud.ndb import model

        keys = sorted(self.todo.keys())

        # Note: this causes synchronous call
        adapter = context_module.get_context().remote_cache
        values = self.execute(adapter, keys)
        kvs = zip(keys, values)
        for todo_key, value in kvs:
            result = value
            if (value
                    and not is_locked_value(value)
                    and not isinstance(value, bool)):
                pb = entity_pb2.Entity()
                pb.MergeFromString(value)
                result = model._entity_from_protobuf(pb)
            for future in self.todo[todo_key]:
                future.set_result(result)


class _RemoteCacheSetBatch:
    """Batch for remote cahce set requests.

    Attributes:
        options (Dict[str, Any]): See Args.
        todo (Dict[str, List[List[tasklets.Future, str]]]: Mapping of
            serialized key protocol buffers to dependent futures.

    Args:
        options (_options.Options): The options for the request. Calls with
            different options will be placed in different batches.
    """

    def __init__(self, options):
        self.options = options
        self.todo = {}

    def future_info(self, value):
        """Information passed to tasklets.Future.

        Args:
            key (ndb.key.Key): The key to get info.

        Returns:
            str: Info to passed to tasklets.Future.
        """
        return "cache_set({})".format(value)

    def execute(self, adapter, mapping):
        """Batch operation implementation.

        Args:
            adapter (ndb.RemoteCacheAdapter): The adapter to do the operation.
            keys (List[str]): The keys to do the operation with.

        Returns:
            Any: Operation result.
        """
        return adapter.cache_set_multi(mapping)

    def add(self, key, value, expire=None):
        """Add a key to the batch.

        Args:
            key (ndb.key.Key): The key to be added.

        Returns:
            tasklets.Future: A future for the eventual result.
        """
        from google.cloud.ndb import model

        future = tasklets.Future(info=self.future_info(value))
        adapter = context_module.get_context().remote_cache
        todo_key = adapter.cache_key(key)
        todo_value = value
        if not is_locked_value(value):
            pb = model._entity_to_protobuf(value)
            todo_value = pb.SerializePartialToString()
        self.todo.setdefault(todo_key, []).append((future, todo_value))
        return future

    def idle_callback(self):
        """Perform a remote cache operation on all batched requests."""
        keys = self.todo.keys()
        adapter = context_module.get_context().remote_cache

        mapping = {}
        for todo_key in keys:
            for future, value in self.todo[todo_key]:
                mapping[todo_key] = value

        # Note: this causes synchronous call
        results = self.execute(adapter, mapping)
        for todo_key in keys:
            result = results[todo_key]
            for future, value in self.todo[todo_key]:
                future.set_result(result)


class _RemoteCacheStartCasBatch(_RemoteCacheGetBatch):
    """Batch for remote cahce start cas requests.

    Attributes:
        options (Dict[str, Any]): See Args.
        todo (Dict[str, List[tasklets.Future]]: Mapping of serialized key
            protocol buffers to dependent futures.

    Args:
        options (_options.Options): The options for the request. Calls with
            different options will be placed in different batches.
    """

    def future_info(self, key):
        """Information passed to tasklets.Future.

        Args:
            key (ndb.key.Key): The key to get info.

        Returns:
            str: Info to passed to tasklets.Future.
        """
        return "cache_start_cas({})".format(key)

    def execute(self, adapter, keys):
        """Batch operation implementation.

        Args:
            adapter (ndb.RemoteCacheAdapter): The adapter to do the operation.
            keys (List[str]): The keys to do the operation with.

        Returns:
            Any: Operation result.
        """
        return adapter.cache_start_cas_multi(keys)


class _RemoteCacheCasBatch(_RemoteCacheSetBatch):
    """Batch for remote cahce set requests.

    Attributes:
        options (Dict[str, Any]): See Args.
        todo (Dict[str, List[List[tasklets.Future, str]]]: Mapping of
            serialized key protocol buffers to dependent futures.

    Args:
        options (_options.Options): The options for the request. Calls with
            different options will be placed in different batches.
    """

    def future_info(self, value):
        """Information passed to tasklets.Future.

        Args:
            key (ndb.key.Key): The key to get info.

        Returns:
            str: Info to passed to tasklets.Future.
        """
        return "cache_cas({})".format(value)

    def execute(self, adapter, mapping):
        """Batch operation implementation.

        Args:
            adapter (ndb.RemoteCacheAdapter): The adapter to do the operation.
            keys (List[str]): The keys to do the operation with.

        Returns:
            Any: Operation result.
        """
        return adapter.cache_cas_multi(mapping)


class _RemoteCacheDeleteBatch(_RemoteCacheGetBatch):
    """Batch for remote cahce delete requests.

    Attributes:
        options (Dict[str, Any]): See Args.
        todo (Dict[str, List[tasklets.Future]]: Mapping of serialized key
            protocol buffers to dependent futures.

    Args:
        options (_options.Options): The options for the request. Calls with
            different options will be placed in different batches.
    """

    def future_info(self, key):
        """Information passed to tasklets.Future.

        Args:
            key (ndb.key.Key): The key to get info.

        Returns:
            str: Info to passed to tasklets.Future.
        """
        return "cache_delete({})".format(key)

    def execute(self, adapter, keys):
        """Batch operation implementation.

        Args:
            adapter (ndb.RemoteCacheAdapter): The adapter to do the operation.
            keys (List[str]): The keys to do the operation with.

        Returns:
            Any: Operation result.
        """
        return adapter.cache_delete_multi(keys)
