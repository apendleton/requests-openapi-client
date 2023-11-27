import typing
import datetime

import jsonpointer
import dataclasses
import dateutil.parser

from .util import camel_to_snake

TYPE_EQUIVALENTS = {
    "number": float,
    "object": object,
    "boolean": bool,
    "array": list,
    "string": str,
}

class BaseDto:
    name_map: typing.Dict = {}
    reverse_name_map: typing.Dict = {}
    required_fields: typing.Set = set()
    nullable_fields: typing.Set = set()

    def serialize(self, use_python_names=False):
        out = {}
        for field_name, field in self.__dataclass_fields__.items():
            value = getattr(self, field_name)
            if value is None and field_name not in self.required_fields and field_name not in self.nullable_fields:
                # this field isn't nullable and isn't required, so interpret it being None as "don't set"
                # instead of "set to null"
                continue
            raw_name = field_name if use_python_names else self.name_map[field_name]
            out[raw_name] = serialize_as(value, field.type, use_python_names=use_python_names)
        return out

    @classmethod
    def deserialize(cls, data):
        init_fields = {}
        for field_name, field in cls.__dataclass_fields__.items():
            raw_name = cls.name_map[field_name]
            if raw_name in data:
                init_fields[field_name] = deserialize_as(data[raw_name], field.type)
            elif field.default is not None:
                init_fields[field_name] = field.default
            elif callable(field.default_factory):
                init_fields[field_name] = field.default_factory()
            else:
                init_fields[field_name] = None
        return cls(**init_fields)

def deserialize_as(data, data_type):
    if data is None:
        return None
    elif type(data_type) is type and issubclass(data_type, BaseDto):
        return data_type.deserialize(data)
    elif isinstance(data_type, TaggedUnion):
        return data_type.deserialize(data)
    elif typing.get_origin(data_type) is list and type(data) is list and typing.get_args(data_type):
        # TODO: what if there are multiple args?
        item_type = typing.get_args(data_type)[0]
        return [deserialize_as(item, item_type) for item in data]
    elif data_type is datetime.datetime and type(data) is str:
        return dateutil.parser.parse(data)
    return data

def serialize_as(data, data_type, use_python_names=False):
    if data is None:
        return None
    elif type(data_type) is type and issubclass(data_type, BaseDto) and issubclass(type(data), BaseDto):
        return data.serialize(use_python_names=use_python_names)
    elif isinstance(data_type, TaggedUnion) and type(data) in data_type.allowed_types:
        return data.serialize(use_python_names=use_python_names)
    elif typing.get_origin(data_type) is list and type(data) is list and typing.get_args(data_type):
        # TODO: what if there are multiple args?
        item_type = typing.get_args(data_type)[0]
        return [serialize_as(item, item_type, use_python_names=use_python_names) for item in data]
    elif data_type is datetime.datetime and type(data) is datetime.datetime:
        # prefer Z instead of "+00:00" for to UTC, match JS norms
        return data.isoformat().replace("+00:00", "Z")
    return data

def type_for_schema(schema, full_spec, realized_types={}):
    if "$ref" in schema:
        if not schema["$ref"].startswith("#"):
            raise Exception("only '#' refs are supported")
        if schema["$ref"].startswith("#/components/schemas/"):
            schema_name = format_schema_name(schema["$ref"].split("/")[-1])
            if schema_name in realized_types:
                return realized_types[schema_name]
        return type_for_schema(jsonpointer.resolve_pointer(full_spec, schema["$ref"][1:]), full_spec, realized_types)

    if "allOf" in schema:
        if len(schema["allOf"]) == 1:
            return type_for_schema(schema["allOf"][0], full_spec, realized_types)
        else:
            # TODO: not sure what to do with multi-item allOf
            print("warning: can't really support allOf")
            return object

    if "oneOf" in schema:
        if len(schema["oneOf"]) == 1:
            return type_for_schema(schema["oneOf"][0], full_spec, realized_types)
        else:
            discriminator = schema.get("discriminator", None)
            if not discriminator:
                return Exception("oneOf clauses are only supported with accompanying discriminator attributes")
            return TaggedUnion(schema["oneOf"], discriminator, full_spec, realized_types)

    if not "type" in schema:
        raise Exception("schemas must have types or refs")
    if schema["type"] == "array":
        if "items" in schema:
            return typing.List.__getitem__(type_for_schema(schema["items"], full_spec, realized_types))
        else:
            return list
    # special-case dates
    if schema["type"] == "string" and schema.get("format", None) == "date-time":
        return datetime.datetime

    return TYPE_EQUIVALENTS.get(schema["type"], None)

class TaggedUnion:
    discriminator_field: str
    discriminator_mapping: typing.Mapping[typing.Any, typing.Any]

    def __init__(self, type_options, discriminator, full_spec, realized_types={}):
        self.discriminator_field = discriminator.get("propertyName", None)
        mapping = discriminator.get("mapping", None)

        if not self.discriminator_field or not mapping:
            raise Exception("discriminator property name and mapping are required")

        types_by_ref = {type_option.get("$ref", None): type_for_schema(type_option, full_spec, realized_types) for type_option in type_options}
        self.discriminator_mapping = {name: types_by_ref[ref] for name, ref in mapping.items()}

    @property
    def allowed_types(self):
        return list(self.discriminator_mapping.values())

    @property
    def type_for_annotation(self):
        return typing.Union.__getitem__(tuple(self.allowed_types))

    def deserialize(self, data):
        type_value = data.get(self.discriminator_field, None)
        if not type_value:
            raise Exception("discriminator mapping field not found on union object")
        if type_value not in self.discriminator_mapping:
            raise Exception(f"discriminator value {type_value} not in union")
        return deserialize_as(data, self.discriminator_mapping[type_value])

def update_field_type(model, field_name, new_type):
    model.__dataclass_fields__[field_name].type = new_type

    if hasattr(new_type, "type_for_annotation"):
        # for tagged unions, we want the external-display type to be a typing.Union, not our
        # internal union type
        new_type = new_type.type_for_annotation

    model.__annotations__[field_name] = new_type
    model.__init__.__annotations__[field_name] = new_type

def format_schema_name(name):
    # TODO: do better
    return (name[0].capitalize() + name[1:]).replace("-", "").replace(" ", "")

def add_types_to_module(spec, module):
    # generate dataclasses for all of the schemas
    # first pass -- realize objects as 'object'
    models = {}
    for name, desc in spec.get("components", {}).get("schemas", {}).items():
        name = format_schema_name(name)
        if desc.get("type", None) == "object":
            properties = []
            required_fields = set()
            nullable_fields = set()
            name_map = {}
            reverse_name_map = {}

            source_required = set(desc.get("required", []))
            for prop, prop_schema in desc.get("properties", {}).items():
                snake_prop = camel_to_snake(prop)
                name_map[snake_prop] = prop
                reverse_name_map[prop] = snake_prop

                if prop in source_required:
                    required_fields.add(snake_prop)
                if prop_schema.get("nullable", False):
                    nullable_fields.add(snake_prop)
                properties.append((
                    snake_prop,
                    type_for_schema(prop_schema, spec),
                    dataclasses.field(default=prop_schema.get("default", None))
                ))

            model = dataclasses.make_dataclass(name, properties, bases=(BaseDto,))
            model.name_map = name_map
            model.reverse_name_map = reverse_name_map
            model.required_fields = required_fields
            model.nullable_fields = nullable_fields
            models[name] = model

            model.__module__ = module.__name__
            setattr(module, name, model)
    # second pass -- update type ascriptions to point to real objects now that
    # they're all realized
    for name, desc in spec.get("components", {}).get("schemas", {}).items():
        name = format_schema_name(name)
        if desc.get("type", None) == "object":
            model = models[name]
            for prop, prop_schema in desc.get("properties", {}).items():
                snake_prop = camel_to_snake(prop)
                realized_type = type_for_schema(prop_schema, spec, models)
                if realized_type != model.__annotations__[snake_prop]:
                    update_field_type(model, snake_prop, realized_type)
    return models
