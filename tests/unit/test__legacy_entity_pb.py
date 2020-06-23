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

import array

from google.cloud.ndb import _legacy_entity_pb as entity_module
from google.cloud.ndb import _legacy_protocol_buffer as pb_module


def _get_decoder(s):
    a = array.array("B")
    a.fromstring(s)
    d = pb_module.Decoder(a, 0, len(a))
    return d


class TestEntityProto:
    @staticmethod
    def test_constructor():
        entity = entity_module.EntityProto()
        assert entity.property_ == []

    @staticmethod
    def test_TryMerge_set_kind():
        entity = entity_module.EntityProto()
        d = _get_decoder(b"\x20\x2a")
        entity.TryMerge(d)
        assert entity.has_kind()
        assert entity.kind() == 42

    @staticmethod
    def test_TryMerge_set_kind_uri():
        entity = entity_module.EntityProto()
        d = _get_decoder(b"\x2a\x01\x41")
        entity.TryMerge(d)
        assert entity.has_kind_uri()
        assert entity.kind_uri().decode() == "A"

    @staticmethod
    def test_TryMerge_mutable_key_app():
        entity = entity_module.EntityProto()
        d = _get_decoder(b"\x6a\x03\x6a\x01\x41")
        entity.TryMerge(d)
        assert entity.key().has_app()
        assert entity.key().app().decode() == "A"

    @staticmethod
    def test_TryMerge_mutable_key_namespace():
        entity = entity_module.EntityProto()
        d = _get_decoder(b"\x6a\x04\xa2\x01\x01\x42")
        entity.TryMerge(d)
        assert entity.key().has_name_space()
        assert entity.key().name_space().decode() == "B"

    @staticmethod
    def test_TryMerge_mutable_key_database():
        entity = entity_module.EntityProto()
        d = _get_decoder(b"\x6a\x04\xba\x01\x01\x43")
        entity.TryMerge(d)
        assert entity.key().has_database_id()
        assert entity.key().database_id().decode() == "C"

    @staticmethod
    def test_TryMerge_mutable_key_path():
        entity = entity_module.EntityProto()
        d = _get_decoder(
            b"\x6a\x0c\x72\x0a\x0b\x12\x01\x44\x18\x01\x22\x01\x45\x0c"
        )
        entity.TryMerge(d)
        assert entity.key().has_path()
        assert entity.key().path().element_size() == 1
        element = entity.key().path().element_list()[0]
        assert element.has_type()
        assert element.type().decode() == "D"
        assert element.has_id()
        assert element.id() == 1
        assert element.has_name()
        assert element.name().decode() == "E"

    @staticmethod
    def test_TryMerge_property_string():
        entity = entity_module.EntityProto()
        d = _get_decoder(b"\x72\x08\x1a\x01\x46\x2a\x03\x1a\x01\x47")
        entity.TryMerge(d)
        assert entity.entity_props()["F"].decode() == "G"

    @staticmethod
    def test_TryMerge_property_int():
        entity = entity_module.EntityProto()
        d = _get_decoder(b"\x72\x07\x1a\x01\x46\x2a\x02\x08\x01")
        entity.TryMerge(d)
        assert entity.entity_props()["F"] == 1

    @staticmethod
    def test_TryMerge_property_double():
        entity = entity_module.EntityProto()
        d = _get_decoder(
            b"\x72\x0e\x1a\x01\x46\x2a\x09\x21\x00\x00\x00\x00\x00\x00E@"
        )
        entity.TryMerge(d)
        assert entity.entity_props()["F"] == 42.0

    @staticmethod
    def test_TryMerge_property_boolean():
        entity = entity_module.EntityProto()
        d = _get_decoder(b"\x72\x07\x1a\x01\x46\x2a\x02\x10\x01")
        entity.TryMerge(d)
        assert entity.entity_props()["F"]

    @staticmethod
    def test_TryMerge_property_point():
        entity = entity_module.EntityProto()
        d = _get_decoder(
            b"\x72\x19\x1a\x01\x46\x2a\x14\x2b\x31\x00\x00\x00\x00\x00\x00E@"
            b"\x39\x00\x00\x00\x00\x00\x00E@\x2c"
        )
        entity.TryMerge(d)
        point = entity.entity_props()["F"]
        assert point.has_x()
        assert point.x() == 42.0
        assert point.has_y()
        assert point.y() == 42.0

    @staticmethod
    def test_TryMerge_property_reference():
        entity = entity_module.EntityProto()
        d = _get_decoder(b"\x72\x0a\x1a\x01\x46\x2a\x05\x63\x6a\x01\x41\x64")
        entity.TryMerge(d)
        assert entity.entity_props()["F"].has_app()
        assert entity.entity_props()["F"].app().decode() == "A"
