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
System tests for queries.
"""

import functools
import operator

import grpc
import pytest

import test_utils.system

from google.cloud import ndb

from tests.system import KIND, OTHER_NAMESPACE, eventually


def _length_equals(n):
    def predicate(sequence):
        return len(sequence) == n

    return predicate


def _equals(n):
    return functools.partial(operator.eq, n)


@pytest.mark.usefixtures("client_context")
def test_fetch_all_of_a_kind(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query()
    results = eventually(query.fetch, _length_equals(5))

    results = sorted(results, key=operator.attrgetter("foo"))
    assert [entity.foo for entity in results] == [0, 1, 2, 3, 4]


@pytest.mark.usefixtures("client_context")
def test_fetch_w_absurdly_short_timeout(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query()
    timeout = 1e-9  # One nanosecend
    with pytest.raises(Exception) as error_context:
        query.fetch(timeout=timeout)

    assert error_context.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED


@pytest.mark.usefixtures("client_context")
def test_fetch_lots_of_a_kind(dispose_of):
    n_entities = 500

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    @ndb.tasklet
    def make_entities():
        entities = [SomeKind(foo=i) for i in range(n_entities)]
        keys = yield [entity.put_async() for entity in entities]
        return keys

    for key in make_entities().result():
        dispose_of(key._key)

    query = SomeKind.query()
    results = eventually(query.fetch, _length_equals(n_entities))

    results = sorted(results, key=operator.attrgetter("foo"))
    assert [entity.foo for entity in results][:5] == [0, 1, 2, 3, 4]


@pytest.mark.usefixtures("client_context")
def test_ancestor_query(ds_entity):
    root_id = test_utils.system.unique_resource_id()
    ds_entity(KIND, root_id, foo=-1)
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, root_id, KIND, entity_id, foo=i)

    another_id = test_utils.system.unique_resource_id()
    ds_entity(KIND, another_id, foo=42)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query(ancestor=ndb.Key(KIND, root_id))
    results = eventually(query.fetch, _length_equals(6))

    results = sorted(results, key=operator.attrgetter("foo"))
    assert [entity.foo for entity in results] == [-1, 0, 1, 2, 3, 4]


@pytest.mark.usefixtures("client_context")
def test_projection(ds_entity):
    entity_id = test_utils.system.unique_resource_id()
    ds_entity(KIND, entity_id, foo=12, bar="none")
    entity_id = test_utils.system.unique_resource_id()
    ds_entity(KIND, entity_id, foo=21, bar="naan")

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StringProperty()

    query = SomeKind.query(projection=("foo",))
    results = eventually(query.fetch, _length_equals(2))

    results = sorted(results, key=operator.attrgetter("foo"))

    assert results[0].foo == 12
    with pytest.raises(ndb.UnprojectedPropertyError):
        results[0].bar

    assert results[1].foo == 21
    with pytest.raises(ndb.UnprojectedPropertyError):
        results[1].bar


@pytest.mark.usefixtures("client_context")
def test_distinct_on(ds_entity):
    for i in range(6):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i % 2, bar="none")

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StringProperty()

    query = SomeKind.query(distinct_on=("foo",))
    eventually(SomeKind.query().fetch, _length_equals(6))

    results = query.fetch()
    results = sorted(results, key=operator.attrgetter("foo"))

    assert results[0].foo == 0
    assert results[0].bar == "none"

    assert results[1].foo == 1
    assert results[1].bar == "none"


@pytest.mark.usefixtures("client_context")
def test_namespace(dispose_of):
    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StringProperty()

    entity1 = SomeKind(foo=1, bar="a", namespace=OTHER_NAMESPACE)
    entity1.put()
    dispose_of(entity1.key._key)

    entity2 = SomeKind(foo=2, bar="b")
    entity2.put()
    dispose_of(entity2.key._key)

    eventually(SomeKind.query().fetch, _length_equals(1))

    query = SomeKind.query(namespace=OTHER_NAMESPACE)
    results = eventually(query.fetch, _length_equals(1))

    assert results[0].foo == 1
    assert results[0].bar == "a"
    assert results[0].key.namespace() == OTHER_NAMESPACE


@pytest.mark.usefixtures("client_context")
def test_filter_equal(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    eventually(SomeKind.query().fetch, _length_equals(5))

    query = SomeKind.query(SomeKind.foo == 2)
    results = query.fetch()
    assert results[0].foo == 2


@pytest.mark.usefixtures("client_context")
def test_filter_not_equal(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    eventually(SomeKind.query().fetch, _length_equals(5))

    query = SomeKind.query(SomeKind.foo != 2)
    results = query.fetch()
    results = sorted(results, key=operator.attrgetter("foo"))
    assert [entity.foo for entity in results] == [0, 1, 3, 4]


@pytest.mark.usefixtures("client_context")
def test_filter_or(dispose_of):
    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StringProperty()

    @ndb.tasklet
    def make_entities():
        keys = yield (
            SomeKind(foo=1, bar="a").put_async(),
            SomeKind(foo=2, bar="b").put_async(),
            SomeKind(foo=1, bar="c").put_async(),
        )
        for key in keys:
            dispose_of(key._key)

    make_entities().check_success()
    eventually(SomeKind.query().fetch, _length_equals(3))

    query = SomeKind.query(ndb.OR(SomeKind.foo == 1, SomeKind.bar == "c"))
    results = query.fetch()
    results = sorted(results, key=operator.attrgetter("bar"))
    assert [entity.bar for entity in results] == ["a", "c"]


@pytest.mark.usefixtures("client_context")
def test_order_by_ascending(ds_entity):
    for i in reversed(range(5)):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query().order(SomeKind.foo)
    results = eventually(query.fetch, _length_equals(5))

    assert [entity.foo for entity in results] == [0, 1, 2, 3, 4]


@pytest.mark.usefixtures("client_context")
def test_order_by_descending(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    # query = SomeKind.query()  # Not implemented yet
    query = SomeKind.query().order(-SomeKind.foo)
    results = eventually(query.fetch, _length_equals(5))
    assert len(results) == 5

    assert [entity.foo for entity in results] == [4, 3, 2, 1, 0]


@pytest.mark.usefixtures("client_context")
def test_order_by_with_or_filter(dispose_of):
    """
    Checking to make sure ordering is preserved when merging different
    results sets.
    """

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StringProperty()

    @ndb.tasklet
    def make_entities():
        keys = yield (
            SomeKind(foo=0, bar="a").put_async(),
            SomeKind(foo=1, bar="b").put_async(),
            SomeKind(foo=2, bar="a").put_async(),
            SomeKind(foo=3, bar="b").put_async(),
        )
        for key in keys:
            dispose_of(key._key)

    make_entities().check_success()
    query = SomeKind.query(ndb.OR(SomeKind.bar == "a", SomeKind.bar == "b"))
    query = query.order(SomeKind.foo)
    results = eventually(query.fetch, _length_equals(4))

    assert [entity.foo for entity in results] == [0, 1, 2, 3]


@pytest.mark.usefixtures("client_context")
def test_keys_only(ds_entity):
    # Assuming unique resource ids are assigned in order ascending with time.
    # Seems to be true so far.
    entity_id1 = test_utils.system.unique_resource_id()
    ds_entity(KIND, entity_id1, foo=12, bar="none")
    entity_id2 = test_utils.system.unique_resource_id()
    ds_entity(KIND, entity_id2, foo=21, bar="naan")

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StringProperty()

    query = SomeKind.query().order(SomeKind.key)
    results = eventually(
        lambda: query.fetch(keys_only=True), _length_equals(2)
    )

    assert results[0] == ndb.Key("SomeKind", entity_id1)
    assert results[1] == ndb.Key("SomeKind", entity_id2)


@pytest.mark.usefixtures("client_context")
def test_offset_and_limit(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    eventually(SomeKind.query().fetch, _length_equals(5))

    query = SomeKind.query(order_by=["foo"])
    results = query.fetch(offset=2, limit=2)
    assert [entity.foo for entity in results] == [2, 3]


@pytest.mark.usefixtures("client_context")
def test_offset_and_limit_with_or_filter(dispose_of):
    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StringProperty()

    @ndb.tasklet
    def make_entities():
        keys = yield (
            SomeKind(foo=0, bar="a").put_async(),
            SomeKind(foo=1, bar="b").put_async(),
            SomeKind(foo=2, bar="a").put_async(),
            SomeKind(foo=3, bar="b").put_async(),
            SomeKind(foo=4, bar="a").put_async(),
            SomeKind(foo=5, bar="b").put_async(),
        )
        for key in keys:
            dispose_of(key._key)

    make_entities().check_success()
    eventually(SomeKind.query().fetch, _length_equals(6))

    query = SomeKind.query(ndb.OR(SomeKind.bar == "a", SomeKind.bar == "b"))
    query = query.order(SomeKind.foo)
    results = query.fetch(offset=1, limit=2)

    assert [entity.foo for entity in results] == [1, 2]


@pytest.mark.usefixtures("client_context")
def test_iter_all_of_a_kind(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query().order("foo")
    results = eventually(lambda: list(query), _length_equals(5))
    assert [entity.foo for entity in results] == [0, 1, 2, 3, 4]


@pytest.mark.usefixtures("client_context")
def test_get_first(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query().order(SomeKind.foo)
    eventually(query.fetch, _length_equals(5))
    assert query.get().foo == 0


@pytest.mark.usefixtures("client_context")
def test_get_only(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query().order(SomeKind.foo)
    eventually(query.fetch, _length_equals(5))
    assert query.filter(SomeKind.foo == 2).get().foo == 2


@pytest.mark.usefixtures("client_context")
def test_get_none(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query().order(SomeKind.foo)
    eventually(query.fetch, _length_equals(5))
    assert query.filter(SomeKind.foo == -1).get() is None


@pytest.mark.usefixtures("client_context")
def test_count_all(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query()
    eventually(query.count, _equals(5))


@pytest.mark.usefixtures("client_context")
def test_count_with_limit(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query()
    eventually(query.count, _equals(5))

    assert query.count(3) == 3


@pytest.mark.usefixtures("client_context")
def test_count_with_filter(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query()
    eventually(query.count, _equals(5))

    assert query.filter(SomeKind.foo == 2).count() == 1


@pytest.mark.usefixtures("client_context")
def test_count_with_multi_query(ds_entity):
    for i in range(5):
        entity_id = test_utils.system.unique_resource_id()
        ds_entity(KIND, entity_id, foo=i)

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    query = SomeKind.query()
    eventually(query.count, _equals(5))

    assert query.filter(SomeKind.foo != 2).count() == 4


@pytest.mark.usefixtures("client_context")
def test_fetch_page(dispose_of):
    page_size = 5
    n_entities = page_size * 2

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()

    @ndb.tasklet
    def make_entities():
        entities = [SomeKind(foo=i) for i in range(n_entities)]
        keys = yield [entity.put_async() for entity in entities]
        return keys

    for key in make_entities().result():
        dispose_of(key._key)

    query = SomeKind.query().order(SomeKind.foo)
    eventually(query.fetch, _length_equals(n_entities))

    results, cursor, more = query.fetch_page(page_size)
    assert [entity.foo for entity in results] == [0, 1, 2, 3, 4]
    assert more

    safe_cursor = cursor.urlsafe()
    next_cursor = ndb.Cursor(urlsafe=safe_cursor)
    results, cursor, more = query.fetch_page(
        page_size, start_cursor=next_cursor
    )
    assert [entity.foo for entity in results] == [5, 6, 7, 8, 9]

    results, cursor, more = query.fetch_page(page_size, start_cursor=cursor)
    assert not results
    assert not more


@pytest.mark.usefixtures("client_context")
def test_polymodel_query(ds_entity):
    class Animal(ndb.PolyModel):
        foo = ndb.IntegerProperty()

    class Cat(Animal):
        pass

    animal = Animal(foo=1)
    animal.put()
    cat = Cat(foo=2)
    cat.put()

    query = Animal.query()
    results = eventually(query.fetch, _length_equals(2))

    results = sorted(results, key=operator.attrgetter("foo"))
    assert isinstance(results[0], Animal)
    assert not isinstance(results[0], Cat)
    assert isinstance(results[1], Animal)
    assert isinstance(results[1], Cat)

    query = Cat.query()
    results = eventually(query.fetch, _length_equals(1))

    assert isinstance(results[0], Animal)
    assert isinstance(results[0], Cat)


@pytest.mark.skip("Requires an index")
@pytest.mark.usefixtures("client_context")
def test_query_repeated_property(ds_entity):
    entity_id = test_utils.system.unique_resource_id()
    ds_entity(KIND, entity_id, foo=1, bar=["a", "b", "c"])

    entity_id = test_utils.system.unique_resource_id()
    ds_entity(KIND, entity_id, foo=2, bar=["c", "d", "e"])

    entity_id = test_utils.system.unique_resource_id()
    ds_entity(KIND, entity_id, foo=3, bar=["e", "f", "g"])

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StringProperty(repeated=True)

    eventually(SomeKind.query().fetch, _length_equals(3))

    query = SomeKind.query().filter(SomeKind.bar == "c").order(SomeKind.foo)
    results = query.fetch()

    assert len(results) == 2
    assert results[0].foo == 1
    assert results[1].foo == 2


@pytest.mark.usefixtures("client_context")
def test_query_structured_property(dispose_of):
    class OtherKind(ndb.Model):
        one = ndb.StringProperty()
        two = ndb.StringProperty()
        three = ndb.StringProperty()

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StructuredProperty(OtherKind)

    @ndb.synctasklet
    def make_entities():
        entity1 = SomeKind(
            foo=1, bar=OtherKind(one="pish", two="posh", three="pash")
        )
        entity2 = SomeKind(
            foo=2, bar=OtherKind(one="pish", two="posh", three="push")
        )
        entity3 = SomeKind(
            foo=3,
            bar=OtherKind(one="pish", two="moppish", three="pass the peas"),
        )

        keys = yield (
            entity1.put_async(),
            entity2.put_async(),
            entity3.put_async(),
        )
        return keys

    keys = make_entities()
    eventually(SomeKind.query().fetch, _length_equals(3))
    for key in keys:
        dispose_of(key._key)

    query = (
        SomeKind.query()
        .filter(SomeKind.bar.one == "pish", SomeKind.bar.two == "posh")
        .order(SomeKind.foo)
    )

    results = query.fetch()
    assert len(results) == 2
    assert results[0].foo == 1
    assert results[1].foo == 2


@pytest.mark.usefixtures("client_context")
def test_query_legacy_structured_property(ds_entity):
    class OtherKind(ndb.Model):
        one = ndb.StringProperty()
        two = ndb.StringProperty()
        three = ndb.StringProperty()

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StructuredProperty(OtherKind)

    entity_id = test_utils.system.unique_resource_id()
    ds_entity(
        KIND,
        entity_id,
        **{"foo": 1, "bar.one": "pish", "bar.two": "posh", "bar.three": "pash"}
    )

    entity_id = test_utils.system.unique_resource_id()
    ds_entity(
        KIND,
        entity_id,
        **{"foo": 2, "bar.one": "pish", "bar.two": "posh", "bar.three": "push"}
    )

    entity_id = test_utils.system.unique_resource_id()
    ds_entity(
        KIND,
        entity_id,
        **{
            "foo": 3,
            "bar.one": "pish",
            "bar.two": "moppish",
            "bar.three": "pass the peas",
        }
    )

    eventually(SomeKind.query().fetch, _length_equals(3))

    query = (
        SomeKind.query()
        .filter(SomeKind.bar.one == "pish", SomeKind.bar.two == "posh")
        .order(SomeKind.foo)
    )

    results = query.fetch()
    assert len(results) == 2
    assert results[0].foo == 1
    assert results[1].foo == 2


@pytest.mark.usefixtures("client_context")
def test_query_repeated_structured_property_with_properties(dispose_of):
    class OtherKind(ndb.Model):
        one = ndb.StringProperty()
        two = ndb.StringProperty()
        three = ndb.StringProperty()

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StructuredProperty(OtherKind, repeated=True)

    @ndb.synctasklet
    def make_entities():
        entity1 = SomeKind(
            foo=1,
            bar=[
                OtherKind(one="pish", two="posh", three="pash"),
                OtherKind(one="bish", two="bosh", three="bash"),
            ],
        )
        entity2 = SomeKind(
            foo=2,
            bar=[
                OtherKind(one="pish", two="bosh", three="bass"),
                OtherKind(one="bish", two="posh", three="pass"),
            ],
        )
        entity3 = SomeKind(
            foo=3,
            bar=[
                OtherKind(one="fish", two="fosh", three="fash"),
                OtherKind(one="bish", two="bosh", three="bash"),
            ],
        )

        keys = yield (
            entity1.put_async(),
            entity2.put_async(),
            entity3.put_async(),
        )
        return keys

    keys = make_entities()
    eventually(SomeKind.query().fetch, _length_equals(3))
    for key in keys:
        dispose_of(key._key)

    query = (
        SomeKind.query()
        .filter(SomeKind.bar.one == "pish", SomeKind.bar.two == "posh")
        .order(SomeKind.foo)
    )

    results = query.fetch()
    assert len(results) == 2
    assert results[0].foo == 1
    assert results[1].foo == 2


@pytest.mark.usefixtures("client_context")
def test_query_repeated_structured_property_with_entity_twice(dispose_of):
    class OtherKind(ndb.Model):
        one = ndb.StringProperty()
        two = ndb.StringProperty()
        three = ndb.StringProperty()

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StructuredProperty(OtherKind, repeated=True)

    @ndb.synctasklet
    def make_entities():
        entity1 = SomeKind(
            foo=1,
            bar=[
                OtherKind(one="pish", two="posh", three="pash"),
                OtherKind(one="bish", two="bosh", three="bash"),
            ],
        )
        entity2 = SomeKind(
            foo=2,
            bar=[
                OtherKind(one="bish", two="bosh", three="bass"),
                OtherKind(one="pish", two="posh", three="pass"),
            ],
        )
        entity3 = SomeKind(
            foo=3,
            bar=[
                OtherKind(one="pish", two="fosh", three="fash"),
                OtherKind(one="bish", two="posh", three="bash"),
            ],
        )

        keys = yield (
            entity1.put_async(),
            entity2.put_async(),
            entity3.put_async(),
        )
        return keys

    keys = make_entities()
    eventually(SomeKind.query().fetch, _length_equals(3))
    for key in keys:
        dispose_of(key._key)

    query = (
        SomeKind.query()
        .filter(
            SomeKind.bar == OtherKind(one="pish", two="posh"),
            SomeKind.bar == OtherKind(two="posh", three="pash"),
        )
        .order(SomeKind.foo)
    )

    results = query.fetch()
    assert len(results) == 1
    assert results[0].foo == 1


@pytest.mark.usefixtures("client_context")
def test_query_legacy_repeated_structured_property(ds_entity):
    class OtherKind(ndb.Model):
        one = ndb.StringProperty()
        two = ndb.StringProperty()
        three = ndb.StringProperty()

    class SomeKind(ndb.Model):
        foo = ndb.IntegerProperty()
        bar = ndb.StructuredProperty(OtherKind, repeated=True)

    entity_id = test_utils.system.unique_resource_id()
    ds_entity(
        KIND,
        entity_id,
        **{
            "foo": 1,
            "bar.one": ["pish", "bish"],
            "bar.two": ["posh", "bosh"],
            "bar.three": ["pash", "bash"],
        }
    )

    entity_id = test_utils.system.unique_resource_id()
    ds_entity(
        KIND,
        entity_id,
        **{
            "foo": 2,
            "bar.one": ["bish", "pish"],
            "bar.two": ["bosh", "posh"],
            "bar.three": ["bass", "pass"],
        }
    )

    entity_id = test_utils.system.unique_resource_id()
    ds_entity(
        KIND,
        entity_id,
        **{
            "foo": 3,
            "bar.one": ["pish", "bish"],
            "bar.two": ["fosh", "posh"],
            "bar.three": ["fash", "bash"],
        }
    )

    eventually(SomeKind.query().fetch, _length_equals(3))

    query = (
        SomeKind.query()
        .filter(
            SomeKind.bar == OtherKind(one="pish", two="posh"),
            SomeKind.bar == OtherKind(two="posh", three="pash"),
        )
        .order(SomeKind.foo)
    )

    results = query.fetch()
    assert len(results) == 1
    assert results[0].foo == 1
