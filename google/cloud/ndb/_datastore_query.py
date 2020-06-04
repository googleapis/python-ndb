# -*- coding: utf-8 -*-
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

"""Translate NDB queries to Datastore calls."""

import base64
import functools
import logging

from google.cloud.datastore_v1.proto import datastore_pb2
from google.cloud.datastore_v1.proto import entity_pb2
from google.cloud.datastore_v1.proto import query_pb2
from google.cloud.datastore import helpers

from google.cloud.ndb import context as context_module
from google.cloud.ndb import _datastore_api
from google.cloud.ndb import exceptions
from google.cloud.ndb import key as key_module
from google.cloud.ndb import model
from google.cloud.ndb import tasklets

log = logging.getLogger(__name__)

MoreResultsType = query_pb2.QueryResultBatch.MoreResultsType
MORE_RESULTS_TYPE_NOT_FINISHED = MoreResultsType.Value("NOT_FINISHED")
MORE_RESULTS_AFTER_LIMIT = MoreResultsType.Value("MORE_RESULTS_AFTER_LIMIT")

ResultType = query_pb2.EntityResult.ResultType
RESULT_TYPE_FULL = ResultType.Value("FULL")
RESULT_TYPE_KEY_ONLY = ResultType.Value("KEY_ONLY")
RESULT_TYPE_PROJECTION = ResultType.Value("PROJECTION")

DOWN = query_pb2.PropertyOrder.DESCENDING
UP = query_pb2.PropertyOrder.ASCENDING

FILTER_OPERATORS = {
    "=": query_pb2.PropertyFilter.EQUAL,
    "<": query_pb2.PropertyFilter.LESS_THAN,
    "<=": query_pb2.PropertyFilter.LESS_THAN_OR_EQUAL,
    ">": query_pb2.PropertyFilter.GREATER_THAN,
    ">=": query_pb2.PropertyFilter.GREATER_THAN_OR_EQUAL,
}

_KEY_NOT_IN_CACHE = object()


def make_filter(name, op, value):
    """Make a property filter protocol buffer.

    Args:
        name (str): The name of the property to filter by.
        op (str): The operator to apply in the filter. Must be one of "=", "<",
            "<=", ">", or ">=".
        value (Any): The value for comparison.

    Returns:
        query_pb2.PropertyFilter: The filter protocol buffer.
    """
    filter_pb = query_pb2.PropertyFilter(
        property=query_pb2.PropertyReference(name=name),
        op=FILTER_OPERATORS[op],
    )
    helpers._set_protobuf_value(filter_pb.value, value)
    return filter_pb


def make_composite_and_filter(filter_pbs):
    """Make a composite filter protocol buffer using AND.

    Args:
        List[Union[query_pb2.PropertyFilter, query_pb2.CompositeFilter]]: The
            list of filters to be combined.

    Returns:
        query_pb2.CompositeFilter: The new composite filter.
    """
    return query_pb2.CompositeFilter(
        op=query_pb2.CompositeFilter.AND,
        filters=[_filter_pb(filter_pb) for filter_pb in filter_pbs],
    )


@tasklets.tasklet
def fetch(query):
    """Fetch query results.

    Args:
        query (query.QueryOptions): The query spec.

    Returns:
        tasklets.Future: Result is List[Union[model.Model, key.Key]]: The query
            results.
    """
    results = iterate(query)
    entities = []
    while (yield results.has_next_async()):
        entities.append(results.next())

    raise tasklets.Return(entities)


def iterate(query, raw=False):
    """Get iterator for query results.

    Args:
        query (query.QueryOptions): The query spec.

    Returns:
        QueryIterator: The iterator.
    """
    filters = query.filters
    if filters:
        if filters._multiquery:
            return _MultiQueryIteratorImpl(query, raw=raw)

        post_filters = filters._post_filters()
        if post_filters:
            predicate = post_filters._to_filter(post=True)
            return _PostFilterQueryIteratorImpl(query, predicate, raw=raw)

    return _QueryIteratorImpl(query, raw=raw)


class QueryIterator(object):
    """An iterator for query results.

    Executes the given query and provides an interface for iterating over
    instances of either :class:`model.Model` or :class:`key.Key` depending on
    whether ``keys_only`` was specified for the query.

    This is an abstract base class. Users should not instantiate an iterator
    class directly. Use :meth:`query.Query.iter` or ``iter(query)`` to get an
    instance of :class:`QueryIterator`.
    """

    def __iter__(self):
        return self

    def has_next(self):
        """Is there at least one more result?

        Blocks until the answer to this question is known and buffers the
        result (if any) until retrieved with :meth:`next`.

        Returns:
            bool: :data:`True` if a subsequent call to
                :meth:`QueryIterator.next` will return a result, otherwise
                :data:`False`.
        """
        raise NotImplementedError()

    def has_next_async(self):
        """Asynchronous version of :meth:`has_next`.

        Returns:
            tasklets.Future: See :meth:`has_next`.
        """
        raise NotImplementedError()

    def probably_has_next(self):
        """Like :meth:`has_next` but won't block.

        This uses a (sometimes inaccurate) shortcut to avoid having to hit the
        Datastore for the answer.

        May return a false positive (:data:`True` when :meth:`next` would
        actually raise ``StopIteration``), but never a false negative
        (:data:`False` when :meth:`next` would actually return a result).
        """
        raise NotImplementedError()

    def next(self):
        """Get the next result.

        May block. Guaranteed not to block if immediately following a call to
        :meth:`has_next` or :meth:`has_next_async` which will buffer the next
        result.

        Returns:
            Union[model.Model, key.Key]: Depending on if ``keys_only=True`` was
                passed in as an option.
        """
        raise NotImplementedError()

    def cursor_before(self):
        """Get a cursor to the point just before the last result returned.

        Returns:
            Cursor: The cursor.

        Raises:
            exceptions.BadArgumentError: If there is no cursor to return. This
                will happen if the iterator hasn't returned a result yet, has
                only returned a single result so far, or if the iterator has
                been exhausted. Also, if query uses ``OR``, ``!=``, or ``IN``,
                since those are composites of multiple Datastore queries each
                with their own cursors—it is impossible to return a cursor for
                the composite query.
        """
        raise NotImplementedError()

    def cursor_after(self):
        """Get a cursor to the point just after the last result returned.

        Returns:
            Cursor: The cursor.

        Raises:
            exceptions.BadArgumentError: If there is no cursor to return. This
                will happen if the iterator hasn't returned a result yet. Also,
                if query uses ``OR``, ``!=``, or ``IN``, since those are
                composites of multiple Datastore queries each with their own
                cursors—it is impossible to return a cursor for the composite
                query.
        """
        raise NotImplementedError()

    def index_list(self):
        """Return a list of indexes used by the query.

        Raises:
            NotImplementedError: Always. This information is no longer
                available from query results in Datastore.
        """
        raise exceptions.NoLongerImplementedError()


class _QueryIteratorImpl(QueryIterator):
    """Implementation of :class:`QueryIterator` for single Datastore queries.

    Args:
        query (query.QueryOptions): The query spec.
        raw (bool): Whether or not to marshall NDB entities or keys for query
            results or return internal representations (:class:`_Result`). For
            internal use only.
    """

    def __init__(self, query, raw=False):
        self._query = query
        self._batch = None
        self._index = None
        self._has_next_batch = None
        self._cursor_before = None
        self._cursor_after = None
        self._raw = raw

    def has_next(self):
        """Implements :meth:`QueryIterator.has_next`."""
        return self.has_next_async().result()

    @tasklets.tasklet
    def has_next_async(self):
        """Implements :meth:`QueryIterator.has_next_async`."""
        if self._batch is None:
            yield self._next_batch()  # First time

        if self._index < len(self._batch):
            raise tasklets.Return(True)

        while self._has_next_batch:
            # Firestore will sometimes send us empty batches when there are
            # still more results to go. This `while` loop skips those.
            yield self._next_batch()
            if self._batch:
                raise tasklets.Return(self._index < len(self._batch))

        raise tasklets.Return(False)

    def probably_has_next(self):
        """Implements :meth:`QueryIterator.probably_has_next`."""
        return (
            self._batch is None  # Haven't even started yet
            or self._has_next_batch  # There's another batch to fetch
            or self._index < len(self._batch)  # Not done with current batch
        )

    @tasklets.tasklet
    def _next_batch(self):
        """Get the next batch from Datastore.

        If this batch isn't the last batch for the query, update the internal
        query spec with a cursor pointing to the next batch.
        """
        query = self._query
        response = yield _datastore_run_query(query)

        batch = response.batch
        result_type = batch.entity_result_type

        self._start_cursor = query.start_cursor
        self._index = 0
        self._batch = [
            _Result(result_type, result_pb, query.order_by)
            for result_pb in response.batch.entity_results
        ]

        self._has_next_batch = more_results = (
            batch.more_results == MORE_RESULTS_TYPE_NOT_FINISHED
        )

        self._more_results_after_limit = (
            batch.more_results == MORE_RESULTS_AFTER_LIMIT
        )

        if more_results:
            # Fix up query for next batch
            limit = self._query.limit
            if limit is not None:
                limit -= len(self._batch)

            offset = self._query.offset
            if offset:
                offset -= response.batch.skipped_results

            self._query = self._query.copy(
                start_cursor=Cursor(batch.end_cursor),
                offset=offset,
                limit=limit,
            )

    def next(self):
        """Implements :meth:`QueryIterator.next`."""
        # May block
        if not self.has_next():
            self._cursor_before = None
            raise StopIteration

        # Won't block
        next_result = self._batch[self._index]
        self._index += 1

        # Adjust cursors
        self._cursor_before = self._cursor_after
        self._cursor_after = next_result.cursor

        if not self._raw:
            next_result = next_result.entity()

        return next_result

    def _peek(self):
        """Get the current, buffered result without advancing the iterator.

        Returns:
            _Result: The current result.

        Raises:
            KeyError: If there's no current, buffered result.
        """
        batch = self._batch
        index = self._index

        if batch and index < len(batch):
            return batch[index]

        raise KeyError(index)

    __next__ = next

    def cursor_before(self):
        """Implements :meth:`QueryIterator.cursor_before`."""
        if self._cursor_before is None:
            raise exceptions.BadArgumentError("There is no cursor currently")

        return self._cursor_before

    def cursor_after(self):
        """Implements :meth:`QueryIterator.cursor_after."""
        if self._cursor_after is None:
            raise exceptions.BadArgumentError("There is no cursor currently")

        return self._cursor_after


class _PostFilterQueryIteratorImpl(QueryIterator):
    """Iterator for query with post filters.

    A post-filter is a filter that can't be executed server side in Datastore
    and therefore must be handled in memory on the client side. This iterator
    allows a predicate representing one or more post filters to be applied to
    query results, returning only those results which satisfy the condition(s)
    enforced by the predicate.

    Args:
        query (query.QueryOptions): The query spec.
        predicate (Callable[[entity_pb2.Entity], bool]): Predicate from post
            filter(s) to be applied. Only entity results for which this
            predicate returns :data:`True` will be returned.
        raw (bool): Whether or not to marshall NDB entities or keys for query
            results or return internal representations (:class:`_Result`). For
            internal use only.
    """

    def __init__(self, query, predicate, raw=False):
        self._result_set = _QueryIteratorImpl(
            query.copy(offset=None, limit=None), raw=True
        )
        self._predicate = predicate
        self._next_result = None
        self._offset = query.offset
        self._limit = query.limit
        self._cursor_before = None
        self._cursor_after = None
        self._raw = raw

    def has_next(self):
        """Implements :meth:`QueryIterator.has_next`."""
        return self.has_next_async().result()

    @tasklets.tasklet
    def has_next_async(self):
        """Implements :meth:`QueryIterator.has_next_async`."""
        if self._next_result:
            raise tasklets.Return(True)

        if self._limit == 0:
            raise tasklets.Return(False)

        # Actually get the next result and load it into memory, or else we
        # can't really know
        while True:
            has_next = yield self._result_set.has_next_async()
            if not has_next:
                raise tasklets.Return(False)

            next_result = self._result_set.next()

            if not self._predicate(next_result.result_pb.entity):
                # Doesn't sastisfy predicate, skip
                continue

            # Satisfies predicate

            # Offset?
            if self._offset:
                self._offset -= 1
                continue

            # Limit?
            if self._limit:
                self._limit -= 1

            self._next_result = next_result

            # Adjust cursors
            self._cursor_before = self._cursor_after
            self._cursor_after = next_result.cursor

            raise tasklets.Return(True)

    def probably_has_next(self):
        """Implements :meth:`QueryIterator.probably_has_next`."""
        return bool(self._next_result) or self._result_set.probably_has_next()

    def next(self):
        """Implements :meth:`QueryIterator.next`."""
        # Might block
        if not self.has_next():
            raise StopIteration()

        # Won't block
        next_result = self._next_result
        self._next_result = None
        if self._raw:
            return next_result
        else:
            return next_result.entity()

    __next__ = next

    def cursor_before(self):
        """Implements :meth:`QueryIterator.cursor_before`."""
        if self._cursor_before is None:
            raise exceptions.BadArgumentError("There is no cursor currently")

        return self._cursor_before

    def cursor_after(self):
        """Implements :meth:`QueryIterator.cursor_after."""
        if self._cursor_after is None:
            raise exceptions.BadArgumentError("There is no cursor currently")

        return self._cursor_after

    @property
    def _more_results_after_limit(self):
        return self._result_set._more_results_after_limit


class _MultiQueryIteratorImpl(QueryIterator):
    """Multiple Query Iterator

    Some queries that in NDB are logically a single query have to be broken
    up into two or more Datastore queries, because Datastore doesn't have a
    composite filter with a boolean OR. This iterator merges two or more query
    result sets. If the results are ordered, it merges results in sort order,
    otherwise it simply chains result sets together. In either case, it removes
    any duplicates so that entities that appear in more than one result set
    only appear once in the merged set.

    Args:
        query (query.QueryOptions): The query spec.
        raw (bool): Whether or not to marshall NDB entities or keys for query
            results or return internal representations (:class:`_Result`). For
            internal use only.
    """

    def __init__(self, query, raw=False):
        queries = [
            query.copy(filters=node, offset=None, limit=None)
            for node in query.filters._nodes
        ]
        self._result_sets = [iterate(_query, raw=True) for _query in queries]
        self._sortable = bool(query.order_by)
        self._seen_keys = set()
        self._next_result = None

        self._offset = query.offset
        self._limit = query.limit
        self._raw = raw

    def has_next(self):
        """Implements :meth:`QueryIterator.has_next`."""
        return self.has_next_async().result()

    @tasklets.tasklet
    def has_next_async(self):
        """Implements :meth:`QueryIterator.has_next_async`."""
        if self._next_result:
            raise tasklets.Return(True)

        if not self._result_sets:
            raise tasklets.Return(False)

        if self._limit == 0:
            raise tasklets.Return(False)

        # Actually get the next result and load it into memory, or else we
        # can't really know
        while True:
            has_nexts = yield [
                result_set.has_next_async() for result_set in self._result_sets
            ]

            self._result_sets = result_sets = [
                result_set
                for i, result_set in enumerate(self._result_sets)
                if has_nexts[i]
            ]

            if not result_sets:
                raise tasklets.Return(False)

            # If sorting, peek at the next values from all result sets and take
            # the minimum.
            if self._sortable:
                min_index, min_value = 0, result_sets[0]._peek()
                for i, result_set in enumerate(result_sets[1:], 1):
                    value = result_sets[i]._peek()
                    if value < min_value:
                        min_value = value
                        min_index = i

                next_result = result_sets[min_index].next()

            # If not sorting, take the next result from the first result set.
            # Will exhaust each result set in turn.
            else:
                next_result = result_sets[0].next()

            # Check to see if it's a duplicate
            hash_key = next_result.result_pb.entity.key.SerializeToString()
            if hash_key in self._seen_keys:
                continue

            # Not a duplicate
            self._seen_keys.add(hash_key)

            # Offset?
            if self._offset:
                self._offset -= 1
                continue

            # Limit?
            if self._limit:
                self._limit -= 1

            self._next_result = next_result

            raise tasklets.Return(True)

    def probably_has_next(self):
        """Implements :meth:`QueryIterator.probably_has_next`."""
        return bool(self._next_result) or any(
            [
                result_set.probably_has_next()
                for result_set in self._result_sets
            ]
        )

    def next(self):
        """Implements :meth:`QueryIterator.next`."""
        # Might block
        if not self.has_next():
            raise StopIteration()

        # Won't block
        next_result = self._next_result
        self._next_result = None
        if self._raw:
            return next_result
        else:
            return next_result.entity()

    __next__ = next

    def cursor_before(self):
        """Implements :meth:`QueryIterator.cursor_before`."""
        raise exceptions.BadArgumentError("Can't have cursors with OR filter")

    def cursor_after(self):
        """Implements :meth:`QueryIterator.cursor_after`."""
        raise exceptions.BadArgumentError("Can't have cursors with OR filter")


@functools.total_ordering
class _Result(object):
    """A single, sortable query result.

    Args:
        result_type (query_pb2.EntityResult.ResultType): The type of result.
        result_pb (query_pb2.EntityResult): Protocol buffer result.
        order_by (Optional[Sequence[query.PropertyOrder]]): Ordering for the
            query. Used to merge sorted result sets while maintaining sort
            order.
    """

    def __init__(self, result_type, result_pb, order_by=None):
        self.result_type = result_type
        self.result_pb = result_pb
        self.order_by = order_by

        self.cursor = Cursor(result_pb.cursor)

    def __lt__(self, other):
        """For total ordering. """
        return self._compare(other) == -1

    def __eq__(self, other):
        """For total ordering. """
        if isinstance(other, _Result) and self.result_pb == other.result_pb:
            return True

        return self._compare(other) == 0

    def _compare(self, other):
        """Compare this result to another result for sorting.

        Args:
            other (_Result): The other result to compare to.

        Returns:
            int: :data:`-1` if this result should come before `other`,
                :data:`0` if this result is equivalent to `other` for sorting
                purposes, or :data:`1` if this result should come after
                `other`.

        Raises:
            NotImplemented: If `order_by` was not passed to constructor or is
                :data:`None` or is empty.
            NotImplemented: If `other` is not a `_Result`.
        """
        if not self.order_by:
            raise NotImplementedError("Can't sort result set without order_by")

        if not isinstance(other, _Result):
            return NotImplemented

        for order in self.order_by:
            this_value_pb = self.result_pb.entity.properties[order.name]
            this_value = helpers._get_value_from_value_pb(this_value_pb)
            other_value_pb = other.result_pb.entity.properties[order.name]
            other_value = helpers._get_value_from_value_pb(other_value_pb)

            direction = -1 if order.reverse else 1

            if this_value < other_value:
                return -direction

            elif this_value > other_value:
                return direction

        return 0

    def entity(self):
        """Get an entity for an entity result. Use the cache if available.

        Args:
            projection (Optional[Sequence[str]]): Sequence of property names to
                be projected in the query results.

        Returns:
            Union[model.Model, key.Key]: The processed result.
        """

        if self.result_type == RESULT_TYPE_FULL:
            # First check the cache.
            context = context_module.get_context()
            key_pb = self.result_pb.entity.key
            ds_key = helpers.key_from_protobuf(key_pb)
            key = key_module.Key._from_ds_key(ds_key)
            entity = _KEY_NOT_IN_CACHE
            use_cache = context._use_cache(key)
            if use_cache:
                try:
                    entity = context.cache.get_and_validate(key)
                except KeyError:
                    pass
            if entity is _KEY_NOT_IN_CACHE:
                # entity not in cache, create one.
                entity = model._entity_from_protobuf(self.result_pb.entity)
            return entity

        elif self.result_type == RESULT_TYPE_PROJECTION:
            entity = model._entity_from_protobuf(self.result_pb.entity)
            projection = tuple(self.result_pb.entity.properties.keys())
            entity._set_projection(projection)
            return entity

        elif self.result_type == RESULT_TYPE_KEY_ONLY:
            key_pb = self.result_pb.entity.key
            ds_key = helpers.key_from_protobuf(key_pb)
            key = key_module.Key._from_ds_key(ds_key)
            return key

        raise NotImplementedError(
            "Got unexpected entity result type for query."
        )


def _query_to_protobuf(query):
    """Convert an NDB query to a Datastore protocol buffer.

    Args:
        query (query.QueryOptions): The query spec.

    Returns:
        query_pb2.Query: The protocol buffer representation of the query.
    """
    query_args = {}
    if query.kind:
        query_args["kind"] = [query_pb2.KindExpression(name=query.kind)]

    if query.projection:
        query_args["projection"] = [
            query_pb2.Projection(
                property=query_pb2.PropertyReference(name=name)
            )
            for name in query.projection
        ]

    if query.distinct_on:
        query_args["distinct_on"] = [
            query_pb2.PropertyReference(name=name)
            for name in query.distinct_on
        ]

    if query.order_by:
        query_args["order"] = [
            query_pb2.PropertyOrder(
                property=query_pb2.PropertyReference(name=order.name),
                direction=DOWN if order.reverse else UP,
            )
            for order in query.order_by
        ]

    filter_pb = query.filters._to_filter() if query.filters else None

    if query.ancestor:
        ancestor_pb = query.ancestor._key.to_protobuf()
        ancestor_filter_pb = query_pb2.PropertyFilter(
            property=query_pb2.PropertyReference(name="__key__"),
            op=query_pb2.PropertyFilter.HAS_ANCESTOR,
        )
        ancestor_filter_pb.value.key_value.CopyFrom(ancestor_pb)

        if filter_pb is None:
            filter_pb = ancestor_filter_pb

        elif isinstance(filter_pb, query_pb2.CompositeFilter):
            filter_pb.filters.add(property_filter=ancestor_filter_pb)

        else:
            filter_pb = query_pb2.CompositeFilter(
                op=query_pb2.CompositeFilter.AND,
                filters=[
                    _filter_pb(filter_pb),
                    _filter_pb(ancestor_filter_pb),
                ],
            )

    if filter_pb is not None:
        query_args["filter"] = _filter_pb(filter_pb)

    if query.start_cursor:
        query_args["start_cursor"] = query.start_cursor.cursor

    if query.end_cursor:
        query_args["end_cursor"] = query.end_cursor.cursor

    query_pb = query_pb2.Query(**query_args)

    if query.offset:
        query_pb.offset = query.offset

    if query.limit:
        query_pb.limit.value = query.limit

    return query_pb


def _filter_pb(filter_pb):
    """Convenience function to compose a filter protocol buffer.

    The Datastore protocol uses a Filter message which has one of either a
    PropertyFilter or CompositeFilter as a sole attribute.

    Args:
        filter_pb (Union[query_pb2.CompositeFilter, query_pb2.PropertyFilter]):
            The actual filter.

    Returns:
        query_pb2.Filter: The filter at the higher level of abstraction
            required to use it in a query.
    """
    if isinstance(filter_pb, query_pb2.CompositeFilter):
        return query_pb2.Filter(composite_filter=filter_pb)

    return query_pb2.Filter(property_filter=filter_pb)


@tasklets.tasklet
def _datastore_run_query(query):
    """Run a query in Datastore.

    Args:
        query (query.QueryOptions): The query spec.

    Returns:
        tasklets.Future:
    """
    query_pb = _query_to_protobuf(query)
    partition_id = entity_pb2.PartitionId(
        project_id=query.project, namespace_id=query.namespace
    )
    read_options = _datastore_api.get_read_options(
        query, default_read_consistency=_datastore_api.EVENTUAL
    )
    request = datastore_pb2.RunQueryRequest(
        project_id=query.project,
        partition_id=partition_id,
        query=query_pb,
        read_options=read_options,
    )
    response = yield _datastore_api.make_call(
        "RunQuery", request, timeout=query.timeout
    )
    log.debug(response)
    raise tasklets.Return(response)


class Cursor(object):
    """Cursor.

    A pointer to a place in a sequence of query results. Cursor itself is just
    a byte sequence passed back by Datastore. This class wraps that with
    methods to convert to/from a URL safe string.

    API for converting to/from a URL safe string is different depending on
    whether you're reading the Legacy NDB docstrings or the official Legacy NDB
    documentation on the web. We do both here.

    Args:
        cursor (bytes): Raw cursor value from Datastore
    """

    @classmethod
    def from_websafe_string(cls, urlsafe):
        # Documented in Legacy NDB docstring for query.Query.fetch
        return cls(urlsafe=urlsafe)

    def __init__(self, cursor=None, urlsafe=None):
        if cursor and urlsafe:
            raise TypeError("Can't pass both 'cursor' and 'urlsafe'")

        self.cursor = cursor

        # Documented in official Legacy NDB docs
        if urlsafe:
            self.cursor = base64.urlsafe_b64decode(urlsafe)

    def to_websafe_string(self):
        # Documented in Legacy NDB docstring for query.Query.fetch
        return self.urlsafe()

    def urlsafe(self):
        # Documented in official Legacy NDB docs
        return base64.urlsafe_b64encode(self.cursor)
