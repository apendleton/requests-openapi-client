import logging
import pprint
import typing
import json
import collections
import dataclasses
import builtins

import requests

from .requestor import Requestor
from .util import camel_to_snake
from .schemas import type_for_schema, serialize_as, deserialize_as

log = logging.getLogger(__name__)


class OpenAPIKeyWord:
    OPENAPI = "openapi"
    INFO = "info"

    SERVERS = "servers"
    URL = "url"
    DESCRIPTION = "description"
    VARIABLES = "variables"

    PATHS = "paths"
    OPERATION_ID = "operationId"
    PARAMETERS = "parameters"
    IN = "in"
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"
    NAME = "name"
    REQUIRED = "required"
    SCHEMA = "schema"
    TYPE = "type"
    STRING = "string"
    TAGS = "tags"
    REQUEST_BODY = "requestBody"
    RESPONSES = "responses"


class Server:
    _url: str
    description: str
    variables: typing.Dict[str, typing.Any]

    def __init__(self, url=None, description=None, variables={}):
        self._url = url
        self.description = description
        self.variables = variables

    @property
    def url(self):
        return self._url.format(self.variables)

    def set_url(self, url):
        self._url = url

@dataclasses.dataclass
class Parameter:
    name: str
    raw_name: str
    type: type
    required: bool
    in_: str
    default: typing.Any

class Operation(object):
    _internal_param_prefix = "_"
    _path: str
    _method: str
    _spec: typing.Dict[str, typing.Any]
    _requestor: Requestor
    _req_opts: typing.Dict[str, typing.Any]
    _server: Server
    _parameters: typing.List[Parameter]
    _available_types: typing.Dict[str, type]
    _response_types: typing.Dict[typing.Any, type]

    _call: typing.Optional[typing.Callable] = None

    def __init__(self, path, method, op_spec, full_spec, available_types={}):
        self._path = path
        self._method = method
        self._spec = op_spec
        self._full_spec = full_spec
        self._available_types = available_types
        self._parameters = []
        self._response_types = {}

        body = self._spec.get(OpenAPIKeyWord.REQUEST_BODY, None)
        if body:
            schema = body.get("content", {}).get("application/json", {}).get("schema", None)
            if schema:
                body_type = type_for_schema(schema, self._full_spec, self._available_types)
            else:
                body_type = typing.Any

            self._parameters.append(Parameter(
                raw_name="body",
                name="body",
                in_=OpenAPIKeyWord.REQUEST_BODY,
                type=body_type,
                required=body.get(OpenAPIKeyWord.REQUIRED, False),
                default=None,
            ))

        for param_spec in self._spec.get(OpenAPIKeyWord.PARAMETERS, []):
            schema = param_spec.get(OpenAPIKeyWord.SCHEMA, None)
            if schema:
                param_type = type_for_schema(schema, self._full_spec, self._available_types)
                default = schema.get("default", None)
            else:
                param_type = typing.Any
                default = None
            self._parameters.append(Parameter(
                raw_name=param_spec[OpenAPIKeyWord.NAME],
                name=camel_to_snake(param_spec[OpenAPIKeyWord.NAME]),
                in_=param_spec[OpenAPIKeyWord.IN],
                type=param_type,
                required=param_spec.get(OpenAPIKeyWord.REQUIRED, False),
                default=default,
            ))

        for status, response in self._spec.get(OpenAPIKeyWord.RESPONSES, {}).items():
            schema = response\
                .get("content", {})\
                .get("application/json", {})\
                .get("schema", None)
            if schema:
                if status != "default":
                    status = int(status)
                expected_type = type_for_schema(schema, self._full_spec, self._available_types)
                self._response_types[status] = expected_type


    @property
    def spec(self):
        return self._spec

    @property
    def operation_id(self):
        return self._spec[OpenAPIKeyWord.OPERATION_ID]

    @property
    def method(self):
        return self._method

    @property
    def path(self):
        return self._path

    @property
    def parameters(self):
        return self._parameters

    def url(self, server, **kwargs):
        return server.url + self._path.format(**kwargs)

    def _gen_call(self):
        def f(client, **kwargs):
            # collect api params
            path_params = {}
            params = {}
            headers = {}
            cookies = {}
            body = None
            for param in self.parameters:
                if param.name not in kwargs:
                    if param.in_ == OpenAPIKeyWord.PATH or param.required:
                        raise ValueError(f"'{name}' is required")
                    continue

                serialized = serialize_as(
                    kwargs.pop(param.name),
                    param.type,
                )
                if param.in_ == OpenAPIKeyWord.PATH:
                    path_params[param.raw_name] = serialized
                elif param.in_ == OpenAPIKeyWord.QUERY:
                    params[param.raw_name] = serialized
                elif param.in_ == OpenAPIKeyWord.HEADER:
                    headers[param.raw_name] = serialized
                elif param.in_ == OpenAPIKeyWord.COOKIE:
                    cookies[param.raw_name] = serialized
                elif param.in_ == OpenAPIKeyWord.REQUEST_BODY:
                    body = serialized


            # collect internal params
            for k in list(kwargs.keys()):
                if not k.startswith(self._internal_param_prefix):
                    continue
                kwargs[
                    k[len(self._internal_param_prefix) :]  # noqa: E203
                ] = kwargs.pop(k)
            kwargs.setdefault("params", {}).update(params)
            kwargs.setdefault("headers", {}).update(headers)
            kwargs.setdefault("cookies", {}).update(cookies)
            if body:
                kwargs["json"] = body
            for k, v in client._req_opts.items():
                kwargs.setdefault(k, v)
            response = client._requestor.request(
                self._method, self.url(client._server, **path_params), **kwargs
            )

            # do a little voodoo so we actually get the response body into the exception
            try:
                response.raise_for_status()
            except Exception as e:
                try:
                    body = json.dumps(response.json())
                    message = f"{e.args[0]}; {body}"
                    e.args = (message,)
                except:
                    pass
                raise e

            data = (
                response.json() if int(response.headers["Content-Length"]) > 0 else None
            )
            if response.status_code in self._response_types:
                return deserialize_as(data, self._response_types[response.status_code])
            elif "default" in self._response_types:
                return deserialize_as(data, self._response_types["default"])
            else:
                return data

        return f

    def __call__(self, client, *args, **kwargs):
        if not self._call:
            self._call = self._gen_call()
        return self._call(client, *args, **kwargs)

    def help(self):
        return pprint.pprint(self.spec, indent=2)

    def __repr__(self):
        return f"<{type(self).__name__}: [{self._method}] {self._path}>"

    def add_client_method(self, target):
        op_name = camel_to_snake(self.operation_id)
        op_locals = {"op": self}

        required_params = []
        optional_params = []
        builtin_names = dir(builtins)
        for param in self.parameters:
            annotation = getattr(param.type, "__name__", None)
            if not (annotation in op_locals or annotation in globals() or annotation in builtin_names):
                annotation = "object"
            if param.required or param.in_ == OpenAPIKeyWord.PATH:
                required_params.append(f"{param.name}: {annotation}")
            else:
                default = json.dumps(param.default) if param.default is not None else "None"
                optional_params.append(f"{param.name}: {annotation}={default}")

        signature_params = ", ".join(required_params + optional_params)
        passthrough_params = ", ".join(
            [f"{param.name}={param.name}" for param in self.parameters]
        )
        exec(f"def {op_name}(self, {signature_params}):\n    return op(self, {passthrough_params})", op_locals)
        func = op_locals[op_name]

        # update the annotations for any types we couldn't see
        for param in self.parameters:
            func.__annotations__[param.name] = param.type

        setattr(target, op_name, func)


class BaseClient:
    _requestor: Requestor
    _req_opts: typing.Dict[str, typing.Any]
    _server: Server
    _operations: typing.Dict[str, typing.Any]
    _spec: typing.Dict[str, typing.Any]
    _available_types: typing.Dict[str, type]

    def __init__(self, requestor=None, server=None, req_opts={}, url=None):
        self._requestor = requestor or requests.Session()
        self._req_opts = req_opts
        if server:
            if type(server) == str:
                self._server = Server(server)
            else:
                self._server = server
        elif url:
            self._server = Server(url=url)
        elif self.servers:
            self._server = self.servers[0]

        for sub_api in self._sub_apis:
            setattr(self, sub_api, SubApiProxy(getattr(self, sub_api), self))

    @property
    def operations(self):
        return self._operations

    @property
    def spec(self):
        return self._spec

    @classmethod
    def subclass_from_spec(base_cls, spec: typing.Dict, client_name="ApiClient", available_types={}):
        if not all(
            [
                i in spec
                for i in [
                    OpenAPIKeyWord.OPENAPI,
                    OpenAPIKeyWord.INFO,
                    OpenAPIKeyWord.PATHS,
                ]
            ]
        ):
            raise ValueError("Invaliad openapi document")

        cls = type(client_name, (base_cls,), {})

        cls._spec = spec.copy()
        _spec = spec.copy()

        cls._available_types = available_types

        servers = _spec.pop(OpenAPIKeyWord.SERVERS, [])
        for key in _spec:
            rkey = key.replace("-", "_")
            setattr(cls, rkey, _spec[key])
        cls.servers = [
            Server(
                url=s.get(OpenAPIKeyWord.URL),
                description=s.get(OpenAPIKeyWord.DESCRIPTION),
                variables=s.get(OpenAPIKeyWord.VARIABLES),
            )
            for s in servers
        ]

        cls._collect_operations()
        return cls

    @classmethod
    def _collect_operations(cls):
        cls._operations = {}
        cls._sub_apis = []
        for path, path_spec in cls.paths.items():
            for method, op_spec in path_spec.items():
                operation_id = op_spec.get(OpenAPIKeyWord.OPERATION_ID)
                if not operation_id:
                    log.warning(
                        f"'{OpenAPIKeyWord.OPERATION_ID}' not found in: '[{method}] {path}'"
                    )
                    continue

                op = Operation(
                    path,
                    method,
                    op_spec,
                    full_spec=cls._spec,
                    available_types=cls._available_types
                )
                if operation_id not in cls._operations:
                    cls._operations[operation_id] = op
                else:
                    log.warning(
                        f"multiple '{operation_id}' found , operation ID should be unique"
                    )
                    v = self._operations[operation_id]
                    if type(v) is not list:
                        self._operations[operation_id] = [v]
                    self._operations[operation_id].append(op)

                tags = op_spec.get(OpenAPIKeyWord.TAGS, None)
                if tags:
                    target_name = camel_to_snake(tags[0])
                    if not hasattr(cls, target_name):
                        setattr(cls, target_name, SubApi())
                        cls._sub_apis.append(target_name)
                    target = getattr(cls, target_name)
                else:
                    target = cls

                op.add_client_method(target)


    @classmethod
    def subclass_from_spec_url(cls, url):
        spec = load_spec_from_url(url)
        return cls.subclass_from_spec(spec)

    @classmethod
    def subclass_from_spec_file(cls, file_path):
        spec = load_spec_from_file(file_path)
        return cls.subclass_from_spec(spec)


    @property
    def requestor(self):
        return self._requestor

    def set_requestor(self, r: Requestor):
        self._requestor = r
        self._collect_operations()

    @property
    def server(self):
        return self._server

    def set_server(self, s):
        self._server = s
        self._collect_operations()

class SubApi:
    pass

class SubApiProxy:
    def __init__(self, sub_api, client):
        self._sub_api = sub_api
        self._client = client

        for func_name, func in sub_api.__dict__.items():
            # bind to client
            setattr(self, func_name, func.__get__(self._client))
