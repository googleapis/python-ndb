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

import base64
import pickle
import unittest.mock

from google.cloud.datastore import _app_engine_key_pb2
import google.cloud.datastore
import pytest

from google.cloud.ndb import exceptions
from google.cloud.ndb import key as key_module
from google.cloud.ndb import model
from google.cloud.ndb import tasklets
import tests.unit.utils


def test___all__():
    tests.unit.utils.verify___all__(key_module)


class TestKey:
    URLSAFE = b"agZzfmZpcmVyDwsSBEtpbmQiBVRoaW5nDA"

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_constructor_default():
        key = key_module.Key("Kind", 42)

        assert key._key == google.cloud.datastore.Key(
            "Kind", 42, project="testing"
        )
        assert key._reference is None

    @staticmethod
    def test_constructor_empty_path():
        with pytest.raises(TypeError):
            key_module.Key(pairs=())

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_constructor_partial():
        with pytest.raises(ValueError):
            key_module.Key("Kind")

        key = key_module.Key("Kind", None)

        assert key._key.is_partial
        assert key._key.flat_path == ("Kind",)
        assert key._key.project == "testing"
        assert key._reference is None

    @staticmethod
    def test_constructor_invalid_id_type():
        with pytest.raises(TypeError):
            key_module.Key("Kind", object())
        with pytest.raises(exceptions.BadArgumentError):
            key_module.Key("Kind", None, "Also", 10)

    @staticmethod
    def test_constructor_invalid_kind_type():
        with pytest.raises(TypeError):
            key_module.Key(object(), 47)
        with pytest.raises(AttributeError):
            key_module.Key(object, 47)

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_constructor_kind_as_model():
        class Simple(model.Model):
            pass

        key = key_module.Key(Simple, 47)
        assert key._key == google.cloud.datastore.Key(
            "Simple", 47, project="testing"
        )
        assert key._reference is None

    @staticmethod
    def test_constructor_with_reference():
        reference = make_reference()
        key = key_module.Key(reference=reference)

        assert key._key == google.cloud.datastore.Key(
            "Parent",
            59,
            "Child",
            "Feather",
            project="sample-app",
            namespace="space",
        )
        assert key._reference is reference

    @staticmethod
    def test_constructor_with_serialized():
        serialized = (
            b"j\x18s~sample-app-no-locationr\n\x0b\x12\x04Zorp\x18X\x0c"
        )
        key = key_module.Key(serialized=serialized)

        assert key._key == google.cloud.datastore.Key(
            "Zorp", 88, project="sample-app-no-location"
        )
        assert key._reference == make_reference(
            path=({"type": "Zorp", "id": 88},),
            app="s~sample-app-no-location",
            namespace=None,
        )

    def test_constructor_with_urlsafe(self):
        key = key_module.Key(urlsafe=self.URLSAFE)

        assert key._key == google.cloud.datastore.Key(
            "Kind", "Thing", project="fire"
        )
        assert key._reference == make_reference(
            path=({"type": "Kind", "name": "Thing"},),
            app="s~fire",
            namespace=None,
        )

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_constructor_with_pairs():
        key = key_module.Key(pairs=[("Kind", 1)])

        assert key._key == google.cloud.datastore.Key(
            "Kind", 1, project="testing"
        )
        assert key._reference is None

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_constructor_with_flat():
        key = key_module.Key(flat=["Kind", 1])

        assert key._key == google.cloud.datastore.Key(
            "Kind", 1, project="testing"
        )
        assert key._reference is None

    @staticmethod
    def test_constructor_with_flat_and_pairs():
        with pytest.raises(TypeError):
            key_module.Key(pairs=[("Kind", 1)], flat=["Kind", 1])

    @staticmethod
    def test_constructor_with_app():
        key = key_module.Key("Kind", 10, app="s~foo")

        assert key._key == google.cloud.datastore.Key(
            "Kind", 10, project="foo"
        )
        assert key._reference is None

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_constructor_with_namespace():
        key = key_module.Key("Kind", 1337, namespace="foo")

        assert key._key == google.cloud.datastore.Key(
            "Kind", 1337, project="testing", namespace="foo"
        )
        assert key._reference is None

    def test_constructor_with_parent(self):
        parent = key_module.Key(urlsafe=self.URLSAFE)
        key = key_module.Key("Zip", 10, parent=parent)

        assert key._key == google.cloud.datastore.Key(
            "Kind", "Thing", "Zip", 10, project="fire"
        )
        assert key._reference is None

    def test_constructor_with_parent_bad_type(self):
        parent = unittest.mock.sentinel.parent
        with pytest.raises(exceptions.BadValueError):
            key_module.Key("Zip", 10, parent=parent)

    @staticmethod
    def test_constructor_insufficient_args():
        with pytest.raises(TypeError):
            key_module.Key(app="foo")

    def test_no_subclass_for_reference(self):
        class KeySubclass(key_module.Key):
            pass

        with pytest.raises(TypeError):
            KeySubclass(urlsafe=self.URLSAFE)

    @staticmethod
    def test_invalid_argument_combination():
        with pytest.raises(TypeError):
            key_module.Key(flat=["a", "b"], urlsafe=b"foo")

    def test_colliding_reference_arguments(self):
        urlsafe = self.URLSAFE
        padding = b"=" * (-len(urlsafe) % 4)
        serialized = base64.urlsafe_b64decode(urlsafe + padding)

        with pytest.raises(TypeError):
            key_module.Key(urlsafe=urlsafe, serialized=serialized)

    @staticmethod
    @unittest.mock.patch("google.cloud.ndb.key.Key.__init__")
    def test__from_ds_key(key_init):
        ds_key = google.cloud.datastore.Key("a", "b", project="c")
        key = key_module.Key._from_ds_key(ds_key)
        assert key._key is ds_key
        assert key._reference is None

        key_init.assert_not_called()

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test___repr__defaults():
        key = key_module.Key("a", "b")
        assert repr(key) == "Key('a', 'b')"
        assert str(key) == "Key('a', 'b')"

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test___repr__non_defaults():
        key = key_module.Key("X", 11, app="foo", namespace="bar")
        assert repr(key) == "Key('X', 11, app='foo', namespace='bar')"
        assert str(key) == "Key('X', 11, app='foo', namespace='bar')"

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test___hash__():
        key1 = key_module.Key("a", 1)
        assert hash(key1) == hash(key1)
        assert hash(key1) == hash(key1.pairs())
        key2 = key_module.Key("a", 2)
        assert hash(key1) != hash(key2)

    @staticmethod
    def test__tuple():
        key = key_module.Key("X", 11, app="foo", namespace="n")
        assert key._tuple() == ("foo", "n", (("X", 11),))

    @staticmethod
    def test___eq__():
        key1 = key_module.Key("X", 11, app="foo", namespace="n")
        key2 = key_module.Key("Y", 12, app="foo", namespace="n")
        key3 = key_module.Key("X", 11, app="bar", namespace="n")
        key4 = key_module.Key("X", 11, app="foo", namespace="m")
        key5 = unittest.mock.sentinel.key
        assert key1 == key1
        assert not key1 == key2
        assert not key1 == key3
        assert not key1 == key4
        assert not key1 == key5

    @staticmethod
    def test___ne__():
        key1 = key_module.Key("X", 11, app="foo", namespace="n")
        key2 = key_module.Key("Y", 12, app="foo", namespace="n")
        key3 = key_module.Key("X", 11, app="bar", namespace="n")
        key4 = key_module.Key("X", 11, app="foo", namespace="m")
        key5 = unittest.mock.sentinel.key
        assert not key1 != key1
        assert key1 != key2
        assert key1 != key3
        assert key1 != key4
        assert key1 != key5

    @staticmethod
    def test___lt__():
        key1 = key_module.Key("X", 11, app="foo", namespace="n")
        key2 = key_module.Key("Y", 12, app="foo", namespace="n")
        key3 = key_module.Key("X", 11, app="goo", namespace="n")
        key4 = key_module.Key("X", 11, app="foo", namespace="o")
        key5 = unittest.mock.sentinel.key
        assert not key1 < key1
        assert key1 < key2
        assert key1 < key3
        assert key1 < key4
        with pytest.raises(TypeError):
            key1 < key5

    @staticmethod
    def test___le__():
        key1 = key_module.Key("X", 11, app="foo", namespace="n")
        key2 = key_module.Key("Y", 12, app="foo", namespace="n")
        key3 = key_module.Key("X", 11, app="goo", namespace="n")
        key4 = key_module.Key("X", 11, app="foo", namespace="o")
        key5 = unittest.mock.sentinel.key
        assert key1 <= key1
        assert key1 <= key2
        assert key1 <= key3
        assert key1 <= key4
        with pytest.raises(TypeError):
            key1 <= key5

    @staticmethod
    def test___gt__():
        key1 = key_module.Key("X", 11, app="foo", namespace="n")
        key2 = key_module.Key("M", 10, app="foo", namespace="n")
        key3 = key_module.Key("X", 11, app="boo", namespace="n")
        key4 = key_module.Key("X", 11, app="foo", namespace="a")
        key5 = unittest.mock.sentinel.key
        assert not key1 > key1
        assert key1 > key2
        assert key1 > key3
        assert key1 > key4
        with pytest.raises(TypeError):
            key1 > key5

    @staticmethod
    def test___ge__():
        key1 = key_module.Key("X", 11, app="foo", namespace="n")
        key2 = key_module.Key("M", 10, app="foo", namespace="n")
        key3 = key_module.Key("X", 11, app="boo", namespace="n")
        key4 = key_module.Key("X", 11, app="foo", namespace="a")
        key5 = unittest.mock.sentinel.key
        assert key1 >= key1
        assert key1 >= key2
        assert key1 >= key3
        assert key1 >= key4
        with pytest.raises(TypeError):
            key1 >= key5

    @staticmethod
    def test_pickling():
        key = key_module.Key("a", "b", app="c", namespace="d")
        pickled = pickle.dumps(key)
        unpickled = pickle.loads(pickled)
        assert key == unpickled

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test___setstate__bad_state():
        key = key_module.Key("a", "b")

        state = ("not", "length", "one")
        with pytest.raises(TypeError):
            key.__setstate__(state)

        state = ("not-a-dict",)
        with pytest.raises(TypeError):
            key.__setstate__(state)

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_parent():
        key = key_module.Key("a", "b", "c", "d")
        parent = key.parent()
        assert parent._key == key._key.parent
        assert parent._reference is None

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_parent_top_level():
        key = key_module.Key("This", "key")
        assert key.parent() is None

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_root():
        key = key_module.Key("a", "b", "c", "d")
        root = key.root()
        assert root._key == key._key.parent
        assert root._reference is None

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_root_top_level():
        key = key_module.Key("This", "key")
        assert key.root() is key

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_namespace():
        namespace = "my-space"
        key = key_module.Key("abc", 1, namespace=namespace)
        assert key.namespace() == namespace

    @staticmethod
    def test_app():
        app = "s~example"
        key = key_module.Key("X", 100, app=app)
        assert key.app() != app
        assert key.app() == app[2:]

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_id():
        for id_or_name in ("x", 11, None):
            key = key_module.Key("Kind", id_or_name)
            assert key.id() == id_or_name

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_string_id():
        pairs = (("x", "x"), (11, None), (None, None))
        for id_or_name, expected in pairs:
            key = key_module.Key("Kind", id_or_name)
            assert key.string_id() == expected

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_integer_id():
        pairs = (("x", None), (11, 11), (None, None))
        for id_or_name, expected in pairs:
            key = key_module.Key("Kind", id_or_name)
            assert key.integer_id() == expected

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_pairs():
        key = key_module.Key("a", "b")
        assert key.pairs() == (("a", "b"),)

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_pairs_partial_key():
        key = key_module.Key("This", "key", "that", None)
        assert key.pairs() == (("This", "key"), ("that", None))

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_flat():
        key = key_module.Key("This", "key")
        assert key.flat() == ("This", "key")

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_flat_partial_key():
        key = key_module.Key("Kind", None)
        assert key.flat() == ("Kind", None)

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_kind():
        key = key_module.Key("This", "key")
        assert key.kind() == "This"
        key = key_module.Key("a", "b", "c", "d")
        assert key.kind() == "c"

    @staticmethod
    def test_reference():
        key = key_module.Key("This", "key", app="fire")
        assert key.reference() == make_reference(
            path=({"type": "This", "name": "key"},), app="fire", namespace=None
        )

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_reference_cached():
        key = key_module.Key("This", "key")
        key._reference = unittest.mock.sentinel.reference
        assert key.reference() is unittest.mock.sentinel.reference

    @staticmethod
    def test_reference_bad_kind():
        too_long = "a" * (key_module._MAX_KEYPART_BYTES + 1)
        for kind in ("", too_long):
            key = key_module.Key(kind, "key", app="app")
            with pytest.raises(ValueError):
                key.reference()

    @staticmethod
    def test_reference_bad_string_id():
        too_long = "a" * (key_module._MAX_KEYPART_BYTES + 1)
        for id_ in ("", too_long):
            key = key_module.Key("kind", id_, app="app")
            with pytest.raises(ValueError):
                key.reference()

    @staticmethod
    def test_reference_bad_integer_id():
        for id_ in (-10, 0, 2 ** 64):
            key = key_module.Key("kind", id_, app="app")
            with pytest.raises(ValueError):
                key.reference()

    @staticmethod
    def test_serialized():
        key = key_module.Key("a", 108, app="c")
        assert key.serialized() == b"j\x01cr\x07\x0b\x12\x01a\x18l\x0c"

    @staticmethod
    def test_urlsafe():
        key = key_module.Key("d", None, app="f")
        assert key.urlsafe() == b"agFmcgULEgFkDA"

    @staticmethod
    @unittest.mock.patch("google.cloud.ndb.key._datastore_api")
    @unittest.mock.patch("google.cloud.ndb.model._entity_from_protobuf")
    def test_get(_entity_from_protobuf, _datastore_api):
        ds_future = tasklets.Future()
        ds_future.set_result("ds_entity")
        _datastore_api.lookup.return_value = ds_future
        _entity_from_protobuf.return_value = "the entity"

        key = key_module.Key("a", "b", app="c")
        assert key.get() == "the entity"

        _datastore_api.lookup.assert_called_once_with(key._key)
        _entity_from_protobuf.assert_called_once_with("ds_entity")

    @staticmethod
    @unittest.mock.patch("google.cloud.ndb.key._datastore_api")
    @unittest.mock.patch("google.cloud.ndb.model._entity_from_protobuf")
    def test_get_async(_entity_from_protobuf, _datastore_api):
        ds_future = tasklets.Future()
        _datastore_api.lookup.return_value = ds_future
        _entity_from_protobuf.return_value = "the entity"

        key = key_module.Key("a", "b", app="c")
        future = key.get_async()
        ds_future.set_result("ds_entity")
        assert future.result() == "the entity"

        _datastore_api.lookup.assert_called_once_with(key._key)
        _entity_from_protobuf.assert_called_once_with("ds_entity")

    @staticmethod
    @unittest.mock.patch("google.cloud.ndb.key._datastore_api")
    def test_get_async_not_found(_datastore_api):
        ds_future = tasklets.Future()
        _datastore_api.lookup.return_value = ds_future

        key = key_module.Key("a", "b", app="c")
        future = key.get_async()
        ds_future.set_result(_datastore_api._NOT_FOUND)
        assert future.result() is None

    @staticmethod
    def test_delete():
        key = key_module.Key("a", "b", app="c")
        with pytest.raises(NotImplementedError):
            key.delete()

    @staticmethod
    def test_delete_async():
        key = key_module.Key("a", "b", app="c")
        with pytest.raises(NotImplementedError):
            key.delete_async()

    @staticmethod
    def test_from_old_key():
        with pytest.raises(NotImplementedError):
            key_module.Key.from_old_key(None)

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_to_old_key():
        key = key_module.Key("a", "b")
        with pytest.raises(NotImplementedError):
            key.to_old_key()


class Test__project_from_app:
    @staticmethod
    def test_already_clean():
        app = "my-prahjekt"
        assert key_module._project_from_app(app) == app

    @staticmethod
    def test_prefixed():
        project = "my-prahjekt"
        for prefix in ("s", "e", "dev"):
            app = "{}~{}".format(prefix, project)
            assert key_module._project_from_app(app) == project

    @staticmethod
    def test_app_fallback(context):
        context.client.project = "s~jectpro"
        with context:
            assert key_module._project_from_app(None) == "jectpro"


class Test__from_reference:
    def test_basic(self):
        reference = make_reference()
        ds_key = key_module._from_reference(reference, None, None)
        assert ds_key == google.cloud.datastore.Key(
            "Parent",
            59,
            "Child",
            "Feather",
            project="sample-app",
            namespace="space",
        )

    def test_matching_app(self):
        reference = make_reference()
        ds_key = key_module._from_reference(reference, "s~sample-app", None)
        assert ds_key == google.cloud.datastore.Key(
            "Parent",
            59,
            "Child",
            "Feather",
            project="sample-app",
            namespace="space",
        )

    def test_differing_app(self):
        reference = make_reference()
        with pytest.raises(RuntimeError):
            key_module._from_reference(reference, "pickles", None)

    def test_matching_namespace(self):
        reference = make_reference()
        ds_key = key_module._from_reference(reference, None, "space")
        assert ds_key == google.cloud.datastore.Key(
            "Parent",
            59,
            "Child",
            "Feather",
            project="sample-app",
            namespace="space",
        )

    def test_differing_namespace(self):
        reference = make_reference()
        with pytest.raises(RuntimeError):
            key_module._from_reference(reference, None, "pickles")


class Test__from_serialized:
    @staticmethod
    def test_basic():
        serialized = (
            b"j\x0cs~sample-appr\x1e\x0b\x12\x06Parent\x18;\x0c\x0b\x12\x05"
            b'Child"\x07Feather\x0c\xa2\x01\x05space'
        )
        ds_key, reference = key_module._from_serialized(serialized, None, None)
        assert ds_key == google.cloud.datastore.Key(
            "Parent",
            59,
            "Child",
            "Feather",
            project="sample-app",
            namespace="space",
        )
        assert reference == make_reference()

    @staticmethod
    def test_no_app_prefix():
        serialized = (
            b"j\x18s~sample-app-no-locationr\n\x0b\x12\x04Zorp\x18X\x0c"
        )
        ds_key, reference = key_module._from_serialized(serialized, None, None)
        assert ds_key == google.cloud.datastore.Key(
            "Zorp", 88, project="sample-app-no-location"
        )
        assert reference == make_reference(
            path=({"type": "Zorp", "id": 88},),
            app="s~sample-app-no-location",
            namespace=None,
        )


class Test__from_urlsafe:
    @staticmethod
    def test_basic():
        urlsafe = (
            "agxzfnNhbXBsZS1hcHByHgsSBlBhcmVudBg7DAsSBUNoaWxkIgdGZ"
            "WF0aGVyDKIBBXNwYWNl"
        )
        urlsafe_bytes = urlsafe.encode("ascii")
        for value in (urlsafe, urlsafe_bytes):
            ds_key, reference = key_module._from_urlsafe(value, None, None)
            assert ds_key == google.cloud.datastore.Key(
                "Parent",
                59,
                "Child",
                "Feather",
                project="sample-app",
                namespace="space",
            )
            assert reference == make_reference()

    @staticmethod
    def test_needs_padding():
        urlsafe = b"agZzfmZpcmVyDwsSBEtpbmQiBVRoaW5nDA"

        ds_key, reference = key_module._from_urlsafe(urlsafe, None, None)
        assert ds_key == google.cloud.datastore.Key(
            "Kind", "Thing", project="fire"
        )
        assert reference == make_reference(
            path=({"type": "Kind", "name": "Thing"},),
            app="s~fire",
            namespace=None,
        )


class Test__constructor_handle_positional:
    @staticmethod
    def test_with_path():
        args = ("Kind", 1)
        kwargs = {}
        key_module._constructor_handle_positional(args, kwargs)
        assert kwargs == {"flat": args}

    @staticmethod
    def test_path_collide_flat():
        args = ("Kind", 1)
        kwargs = {"flat": ("OtherKind", "Cheese")}
        with pytest.raises(TypeError):
            key_module._constructor_handle_positional(args, kwargs)

    @staticmethod
    def test_dict_positional():
        args = ({"flat": ("OtherKind", "Cheese"), "app": "ehp"},)
        kwargs = {}
        key_module._constructor_handle_positional(args, kwargs)
        assert kwargs == args[0]

    @staticmethod
    def test_dict_positional_with_other_kwargs():
        args = ({"flat": ("OtherKind", "Cheese"), "app": "ehp"},)
        kwargs = {"namespace": "over-here"}
        with pytest.raises(TypeError):
            key_module._constructor_handle_positional(args, kwargs)


def make_reference(
    path=({"type": "Parent", "id": 59}, {"type": "Child", "name": "Feather"}),
    app="s~sample-app",
    namespace="space",
):
    elements = [
        _app_engine_key_pb2.Path.Element(**element) for element in path
    ]
    return _app_engine_key_pb2.Reference(
        app=app,
        path=_app_engine_key_pb2.Path(element=elements),
        name_space=namespace,
    )
