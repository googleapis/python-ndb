"""
Module Description
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
]

_LOCKED = 0
_LOCKED_STR = '0'
_LOCKED_BYTES = b'0'
_LOCK_TIME = 32
_PREFIX = "NDB9"


class RemoteCacheAdapter:
    def cache_key(self, key):
        items = [_PREFIX, key.urlsafe().decode('ascii')]
        ns = key.namespace()
        if ns:
            items.insert(0, ns)
        return ':'.join(items)

    def cache_get_multi(self, keys):
        """Direct pass-through to memcache client."""
        raise NotImplementedError

    def cache_set_multi(self, values, expire=None):
        """Direct pass-through to memcache client."""
        raise NotImplementedError

    def cache_start_cas_multi(self, keys):
        """Direct pass-through to memcache client."""
        raise NotImplementedError

    def cache_cas_multi(self, values, expire=None):
        """Direct pass-through to memcache client."""
        raise NotImplementedError

    def cache_delete_multi(self, keys):
        """Direct pass-through to memcache client."""
        raise NotImplementedError


def cache_get(key, **options):
    """Direct pass-through to memcache client."""
    batch = _get_batch(_RemoteCacheGetBatch, options)
    return batch.add(key, **options)


def cache_set(key, value, **options):
    """Direct pass-through to memcache client."""
    batch = _get_batch(_RemoteCacheSetBatch, options)
    return batch.add(key, value, **options)


def cache_set_locked(key, **options):
    """Direct pass-through to memcache client."""
    value = _LOCKED
    options = options or {}
    options['expire'] = _LOCK_TIME
    return cache_set(key, value, **options)


def cache_start_cas(key, **options):
    """Direct pass-through to memcache client."""
    batch = _get_batch(_RemoteCacheStartCasBatch, options)
    return batch.add(key, **options)


def cache_cas(key, value, **options):
    """Direct pass-through to memcache client."""
    batch = _get_batch(_RemoteCacheCasBatch, options)
    return batch.add(key, value, **options)


def cache_delete(key, **options):
    """Direct pass-through to memcache client."""
    batch = _get_batch(_RemoteCacheDeleteBatch, options)
    return batch.add(key, **options)


def is_locked_value(value):
    return value in (_LOCKED, _LOCKED_STR, _LOCKED_BYTES)


def _get_batch(batch_cls, options):
    """Gets a data structure for storing batched calls to Datastore Lookup.

    The batch data structure is stored in the current context. If there is
    not already a batch started, a new structure is created and an idle
    callback is added to the current event loop which will eventually perform
    the batch look up.

    Args:
        batch_cls (type): Class representing the kind of operation being
            batched.
        options (_options.ReadOptions): The options for the request. Calls with
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
    """Batch for Lookup requests.

    Attributes:
        options (Dict[str, Any]): See Args.
        todo (Dict[bytes, List[tasklets.Future]]: Mapping of serialized key
            protocol buffers to dependent futures.

    Args:
        options (_options.ReadOptions): The options for the request. Calls with
            different options will be placed in different batches.
    """

    def __init__(self, options):
        self.options = options
        self.todo = {}

    def future_info(self, key):
        return "cache_get({})".format(key)

    def execute(self, adapter, keys):
        return adapter.cache_get_multi(keys)

    def add(self, key):
        """Add a key to the batch to look up.

        Args:
            key (datastore.Key): The key to look up.

        Returns:
            tasklets.Future: A future for the eventual result.
        """

        future = tasklets.Future(info=self.future_info(key))
        adapter = context_module.get_context().remote_cache
        if not adapter:
            future.set_result(None)
            return future
        todo_key = adapter.cache_key(key)
        self.todo.setdefault(todo_key, []).append(future)
        return future

    def idle_callback(self):
        """Perform a Datastore Lookup on all batched Lookup requests."""
        from google.cloud.ndb import model

        keys = self.todo.keys()

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
    """Batch for Lookup requests.

    Attributes:
        options (Dict[str, Any]): See Args.
        todo (Dict[bytes, List[tasklets.Future]]: Mapping of serialized key
            protocol buffers to dependent futures.

    Args:
        options (_options.ReadOptions): The options for the request. Calls with
            different options will be placed in different batches.
    """

    def __init__(self, options):
        self.options = options
        self.todo = {}

    def future_info(self, value):
        return "cache_set({})".format(value)

    def execute(self, adapter, mapping):
        return adapter.cache_set_multi(mapping)

    def add(self, key, value, expire=None):
        """Add a key to the batch to look up.

        Args:
            key (datastore.Key): The key to look up.

        Returns:
            tasklets.Future: A future for the eventual result.
        """
        from google.cloud.ndb import model

        future = tasklets.Future(info=self.future_info(value))
        adapter = context_module.get_context().remote_cache
        if not adapter:
            future.set_result(False)
            return future
        todo_key = adapter.cache_key(key)
        todo_value = value
        if not is_locked_value(value):
            pb = model._entity_to_protobuf(value)
            todo_value = pb.SerializePartialToString()
        self.todo.setdefault(todo_key, []).append((future, todo_value))
        return future

    def idle_callback(self):
        """Perform a Datastore Lookup on all batched Lookup requests."""
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
    def future_info(self, key):
        return "cache_start_cas({})".format(key)

    def execute(self, adapter, keys):
        return adapter.cache_start_cas_multi(keys)


class _RemoteCacheCasBatch(_RemoteCacheSetBatch):
    def future_info(self, value):
        return "cache_cas({})".format(value)

    def execute(self, adapter, mapping):
        return adapter.cache_cas_multi(mapping)


class _RemoteCacheDeleteBatch(_RemoteCacheGetBatch):
    def future_info(self, key):
        return "cache_delete({})".format(key)

    def execute(self, adapter, keys):
        return adapter.cache_delete_multi(keys)
