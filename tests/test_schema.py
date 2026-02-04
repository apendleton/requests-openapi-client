import datetime
import pytest
import dataclasses
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


def test_base_dto_serialize():
    dto = ExampleDto(field1=123)
    dto.name_map = {"field1": "Field1", "field2": "Field2"}
    serialized = dto.serialize()
    assert serialized == {"Field1": 123, "Field2": "default"}


def test_base_dto_serialize_use_python_names():
    dto = ExampleDto(field1=123)
    dto.name_map = {"field1": "Field1", "field2": "Field2"}
    serialized = dto.serialize(use_python_names=True)
    assert serialized == {"field1": 123, "field2": "default"}


def test_base_dto_serialize_use_python_names_no_map():
    dto = ExampleDto(field1=123, field2="hello")
    dto.name_map = {"field1": "Field1", "Field2": "Field2"}
    serialized = dto.serialize(use_python_names=True)
    assert serialized == {"field1": 123, "field2": "hello"}

    with pytest.raises(Exception):
        # no use_python_names but no mapping for lowercase `field2`
        serialized = dto.serialize()


def test_base_dto_deserialize():
    ExampleDto.name_map = {"field1": "Field1", "field2": "Field2"}
    data = {"Field1": 123, "Field2": "test"}
    dto = ExampleDto.deserialize(data)
    assert dto.field1 == 123
    assert dto.field2 == "test"


def test_base_dto_deserialize_use_python_names():
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


def test_deserialize_as():
    data = "2023-01-01T00:00:00Z"
    result = deserialize_as(data, datetime.datetime)
    # TODO: should action this preserve the timezone? It doesn't currently
    assert result.replace(tzinfo=None) == datetime.datetime(2023, 1, 1, 0, 0, 0)


def test_serialize_as():
    data = datetime.datetime(2023, 1, 1, 0, 0, 0)
    result = serialize_as(data, datetime.datetime)
    assert result == "2023-01-01T00:00:00"


def test_serialize_as_tz():
    data = datetime.datetime(2023, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    result = serialize_as(data, datetime.datetime)
    assert result == "2023-01-01T00:00:00Z"


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
