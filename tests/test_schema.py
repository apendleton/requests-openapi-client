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


class TestTaggedUnion:
    def test_tagged_union_deserialize(self):
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
                "mapping": {
                    "a": "#/components/schemas/A",
                    "b": "#/components/schemas/B",
                },
            },
            full_spec={},
            realized_types={"A": A, "B": B},
        )
        data = {"type": "a"}
        result = union.deserialize(data)
        assert isinstance(result, A)

    def test_tagged_union_deserialize_use_python_names(self):
        @dataclasses.dataclass
        class A(BaseDto):
            value: int
            label: str = "default"

        @dataclasses.dataclass
        class B(BaseDto):
            pass

        A.name_map = {"value": "Value", "label": "Label"}
        B.name_map = {}

        union = TaggedUnion(
            type_options=[
                {"$ref": "#/components/schemas/A"},
                {"$ref": "#/components/schemas/B"},
            ],
            discriminator={
                "propertyName": "type",
                "mapping": {
                    "a": "#/components/schemas/A",
                    "b": "#/components/schemas/B",
                },
            },
            full_spec={},
            realized_types={"A": A, "B": B},
        )

        # With use_python_names=True, keys should be lowercase
        data = {"type": "a", "value": 42, "label": "test"}
        result = union.deserialize(data, use_python_names=True)
        assert isinstance(result, A)
        assert result.value == 42
        assert result.label == "test"

        # Without use_python_names, keys should be uppercase
        data = {"type": "a", "Value": 42, "Label": "test"}
        result = union.deserialize(data, use_python_names=False)
        assert isinstance(result, A)
        assert result.value == 42
        assert result.label == "test"

    def test_tagged_union_deserialize_camel_case_discriminator(self):
        @dataclasses.dataclass
        class SchemeA(BaseDto):
            pass

        @dataclasses.dataclass
        class SchemeB(BaseDto):
            pass

        SchemeA.name_map = {"big_scheme": "BigScheme"}
        SchemeA.reverse_name_map = {"BigScheme": "big_scheme"}
        SchemeB.name_map = {"big_scheme": "BigScheme"}
        SchemeB.reverse_name_map = {"BigScheme": "big_scheme"}

        union = TaggedUnion(
            type_options=[
                {"$ref": "#/components/schemas/SchemeA"},
                {"$ref": "#/components/schemas/SchemeB"},
            ],
            discriminator={
                "propertyName": "BigScheme",  # camelCase
                "mapping": {
                    "a": "#/components/schemas/SchemeA",
                    "b": "#/components/schemas/SchemeB",
                },
            },
            full_spec={},
            realized_types={"SchemeA": SchemeA, "SchemeB": SchemeB},
        )

        # With use_python_names=True, discriminator field should use reverse_name_map
        data = {"big_scheme": "a"}
        result = union.deserialize(data, use_python_names=True)
        assert isinstance(result, SchemeA)

        # Without use_python_names, discriminator field should be camelCase
        data = {"BigScheme": "b"}
        result = union.deserialize(data, use_python_names=False)
        assert isinstance(result, SchemeB)

    def test_tagged_union_missing_property_name(self):
        @dataclasses.dataclass
        class A(BaseDto):
            pass

        with pytest.raises(
            Exception, match="discriminator property name and mapping are required"
        ):
            TaggedUnion(
                type_options=[{"$ref": "#/components/schemas/A"}],
                discriminator={
                    # missing propertyName
                    "mapping": {"a": "#/components/schemas/A"},
                },
                full_spec={},
                realized_types={"A": A},
            )

    def test_tagged_union_missing_mapping(self):
        @dataclasses.dataclass
        class A(BaseDto):
            pass

        with pytest.raises(
            Exception, match="discriminator property name and mapping are required"
        ):
            TaggedUnion(
                type_options=[{"$ref": "#/components/schemas/A"}],
                discriminator={
                    "propertyName": "type",
                    # missing mapping
                },
                full_spec={},
                realized_types={"A": A},
            )

    def test_tagged_union_discriminator_field_not_in_data(self):
        @dataclasses.dataclass
        class A(BaseDto):
            pass

        A.name_map = {}

        union = TaggedUnion(
            type_options=[{"$ref": "#/components/schemas/A"}],
            discriminator={
                "propertyName": "type",
                "mapping": {"a": "#/components/schemas/A"},
            },
            full_spec={},
            realized_types={"A": A},
        )

        with pytest.raises(Exception, match="discriminator mapping field not found"):
            union.deserialize({"other_field": "value"})

    def test_tagged_union_invalid_discriminator_value(self):
        @dataclasses.dataclass
        class A(BaseDto):
            pass

        A.name_map = {}

        union = TaggedUnion(
            type_options=[{"$ref": "#/components/schemas/A"}],
            discriminator={
                "propertyName": "type",
                "mapping": {"a": "#/components/schemas/A"},
            },
            full_spec={},
            realized_types={"A": A},
        )

        with pytest.raises(Exception, match="discriminator value .* not in union"):
            union.deserialize({"type": "invalid_value"})

    def test_tagged_union_fallback_to_camel_to_snake(self):
        @dataclasses.dataclass
        class A(BaseDto):
            pass

        # No reverse_name_map set
        A.name_map = {}
        A.reverse_name_map = {}

        union = TaggedUnion(
            type_options=[{"$ref": "#/components/schemas/A"}],
            discriminator={
                "propertyName": "someDiscriminatorField",  # camelCase
                "mapping": {"a": "#/components/schemas/A"},
            },
            full_spec={},
            realized_types={"A": A},
        )

        # Should fall back to camel_to_snake conversion
        data = {"some_discriminator_field": "a"}
        result = union.deserialize(data, use_python_names=True)
        assert isinstance(result, A)


def test_type_for_schema():
    schema = {"type": "string", "format": "date-time"}
    result = type_for_schema(schema, {})
    assert result == datetime.datetime


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
