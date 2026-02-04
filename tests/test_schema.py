import datetime
import pytest
import dataclasses
from typing import List
from requests_openapi_client.schemas import (
    BaseDto,
    deserialize_as,
    serialize_as,
    type_for_schema,
    TaggedUnion,
)


@dataclasses.dataclass
class ExampleDto(BaseDto):
    field1: int
    field2: str = "default"


@dataclasses.dataclass
class ChildDto(BaseDto):
    value: int
    label: str = "child"


@dataclasses.dataclass
class ParentDto(BaseDto):
    name: str
    child: ChildDto = None


class TestSerialize:
    def test_base_dto_serialize(self):
        dto = ExampleDto(field1=123)
        dto.name_map = {"field1": "Field1", "field2": "Field2"}
        serialized = dto.serialize()
        assert serialized == {"Field1": 123, "Field2": "default"}

    def test_base_dto_serialize_use_python_names(self):
        dto = ExampleDto(field1=123)
        dto.name_map = {"field1": "Field1", "field2": "Field2"}
        serialized = dto.serialize(use_python_names=True)
        assert serialized == {"field1": 123, "field2": "default"}

    def test_base_dto_serialize_use_python_names_no_map(self):
        dto = ExampleDto(field1=123, field2="hello")
        dto.name_map = {"field1": "Field1", "Field2": "Field2"}
        serialized = dto.serialize(use_python_names=True)
        assert serialized == {"field1": 123, "field2": "hello"}

        with pytest.raises(Exception):
            # no use_python_names but no mapping for lowercase `field2`
            serialized = dto.serialize()


class TestSerializeAs:
    def test_serialize_as(self):
        data = datetime.datetime(2023, 1, 1, 0, 0, 0)
        result = serialize_as(data, datetime.datetime)
        assert result == "2023-01-01T00:00:00"

    def test_serialize_as_tz(self):
        data = datetime.datetime(2023, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
        result = serialize_as(data, datetime.datetime)
        assert result == "2023-01-01T00:00:00Z"

    def test_serialize_as_list(self):
        data = [1, 2, 3]
        result = serialize_as(data, List[int])
        assert result == [1, 2, 3]

    def test_serialize_as_list_of_dtos(self):
        ChildDto.name_map = {"value": "Value", "label": "Label"}

        data = [
            ChildDto(value=1, label="first"),
            ChildDto(value=2, label="second"),
        ]
        result = serialize_as(data, List[ChildDto])

        assert result == [
            {"Value": 1, "Label": "first"},
            {"Value": 2, "Label": "second"},
        ]

    def test_serialize_as_list_of_dtos_use_python_names(self):
        ChildDto.name_map = {"value": "Value", "label": "Label"}

        data = [
            ChildDto(value=1, label="first"),
            ChildDto(value=2, label="second"),
        ]
        result = serialize_as(data, List[ChildDto], use_python_names=True)

        assert result == [
            {"value": 1, "label": "first"},
            {"value": 2, "label": "second"},
        ]


class TestDeserialize:
    def test_base_dto_deserialize(self):
        ExampleDto.name_map = {"field1": "Field1", "field2": "Field2"}
        data = {"Field1": 123, "Field2": "test"}
        dto = ExampleDto.deserialize(data)
        assert dto.field1 == 123
        assert dto.field2 == "test"

    def test_base_dto_deserialize_use_python_names(self):
        ExampleDto.name_map = {"field1": "Field1", "field2": "Field2"}

        data = {"field1": 123, "field2": "test"}
        dto = ExampleDto.deserialize(data, use_python_names=True)
        assert dto.field1 == 123
        assert dto.field2 == "test"

        # there are no "python names" in this data
        data = {"Field1": 123, "Field2": "test"}
        dto = ExampleDto.deserialize(data, use_python_names=True)
        assert dto.field1 == dataclasses.MISSING
        assert dto.field2 == "default"


class TestDeserializeAs:
    def test_deserialize_as(self):
        data = "2023-01-01T00:00:00Z"
        result = deserialize_as(data, datetime.datetime)
        # TODO: should action this preserve the timezone? It doesn't currently
        assert result.replace(tzinfo=None) == datetime.datetime(2023, 1, 1, 0, 0, 0)

    def test_deserialize_as_list(self):
        data = [1, 2, 3]
        result = deserialize_as(data, List[int])
        assert result == [1, 2, 3]

    def test_deserialize_as_list_of_dtos(self):
        ChildDto.name_map = {"value": "Value", "label": "Label"}

        data = [
            {"Value": 1, "Label": "first"},
            {"Value": 2, "Label": "second"},
        ]
        result = deserialize_as(data, List[ChildDto])

        assert len(result) == 2
        assert all(isinstance(item, ChildDto) for item in result)
        assert result[0].value == 1
        assert result[0].label == "first"
        assert result[1].value == 2
        assert result[1].label == "second"

    def test_deserialize_as_list_of_dtos_use_python_names(self):
        ChildDto.name_map = {"value": "Value", "label": "Label"}

        data = [
            {"value": 1, "label": "first"},
            {"value": 2, "label": "second"},
        ]
        result = deserialize_as(data, List[ChildDto], use_python_names=True)

        assert len(result) == 2
        assert result[0].value == 1
        assert result[1].label == "second"


def test_type_for_schema():
    schema = {"type": "string", "format": "date-time"}
    result = type_for_schema(schema, {})
    assert result == datetime.datetime


def test_tagged_union_deserialize():
    @dataclasses.dataclass
    class A(BaseDto):
        pass

    @dataclasses.dataclass
    class B(BaseDto):
        pass

    union = TaggedUnion(
        type_options=[
            {"$ref": "#/components/schemas/A"},
            {"$ref": "#/components/schemas/B"},
        ],
        discriminator={
            "propertyName": "type",
            "mapping": {"a": "#/components/schemas/A", "b": "#/components/schemas/B"},
        },
        full_spec={},
        realized_types={"A": A, "B": B},
    )
    data = {"type": "a"}
    result = union.deserialize(data)
    assert isinstance(result, A)


# --- TODO: Tests to implement ---

todo = pytest.mark.skip(reason="TODO")


@todo
def test_type_for_schema_ref():
    pass


@todo
def test_type_for_schema_allof():
    pass


@todo
def test_type_for_schema_oneof():
    pass


@todo
def test_type_for_schema_array():
    pass


@todo
def test_serialize_required_nullable_fields():
    pass


@todo
def test_deserialize_default_factory():
    pass


@todo
def test_tagged_union_serialize():
    pass


@todo
def test_tagged_union_errors():
    pass


@todo
def test_format_schema_name():
    pass


@todo
def test_update_field_type():
    pass


@todo
def test_add_types_to_module():
    pass
