import logging
import pprint
import typing

import requests
# import yaml

from .requestor import Requestor
from .util import camel_to_snake

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


class Operation(object):
    _internal_param_prefix = "_"
    _path: str
    _method: str
    _spec: typing.Dict[str, typing.Any]
    _requestor: Requestor
    _req_opts: typing.Dict[str, typing.Any]
    _server: Server

    _call: typing.Optional[typing.Callable] = None

    def __init__(self, path, method, spec,):
        self._path = path
        self._method = method
        self._spec = spec

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
        return [spec[OpenAPIKeyWord.NAME] for spec in self._spec.get(OpenAPIKeyWord.PARAMETERS, [])]

    def url(self, server, **kwargs):
        return server.url + self._path.format(**kwargs)

    def _gen_call(self):
        def f(client, **kwargs):
            # collect api params
            path_params = {}
            params = {}
            headers = {}
            cookies = {}
            for spec in self._spec.get(OpenAPIKeyWord.PARAMETERS, []):
                _in = spec[OpenAPIKeyWord.IN]
                name = spec[OpenAPIKeyWord.NAME]

                if name not in kwargs:
                    if _in == OpenAPIKeyWord.PATH:
                        raise ValueError(f"'{name}' is required")
                    continue

                if _in == OpenAPIKeyWord.PATH:
                    path_params[name] = kwargs.pop(name)
                elif _in == OpenAPIKeyWord.QUERY:
                    params[name] = kwargs.pop(name)
                elif _in == OpenAPIKeyWord.HEADER:
                    headers[name] = kwargs.pop(name)
                elif _in == OpenAPIKeyWord.COOKIE:
                    cookies[name] = kwargs.pop(name)

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
            for k, v in client._req_opts.items():
                kwargs.setdefault(k, v)
            return client._requestor.request(
                self._method, self.url(client._server, **path_params), **kwargs
            )

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
        for spec in self._spec.get(OpenAPIKeyWord.PARAMETERS, []):
            _in = spec[OpenAPIKeyWord.IN]
            name = spec[OpenAPIKeyWord.NAME]
            required = spec.get(OpenAPIKeyWord.REQUIRED, False)

            if required or _in == OpenAPIKeyWord.PATH:
                required_params.append(name)
            else:
                optional_params.append(name)

        signature_params = ", ".join(
            required_params +\
            [f"{param}=None" for param in optional_params]
        )
        passthrough_params = ", ".join(
            [f"{param}={param}" for param in required_params + optional_params]
        )
        exec(f"def {op_name}(self, {signature_params}):\n    return op(self, {passthrough_params})", op_locals)
        setattr(target, op_name, op_locals[op_name])


def load_spec_from_url(url):
    r = requests.get(url)
    r.raise_for_status()

    return yaml.load(r.text, Loader=yaml.Loader)


def load_spec_from_file(file_path):
    with open(file_path) as f:
        spec_str = f.read()

    return yaml.load(spec_str, Loader=yaml.Loader)


class BaseClient:
    _requestor: Requestor
    _req_opts: typing.Dict[str, typing.Any]
    _server: Server
    _operations: typing.Dict[str, typing.Any]
    _spec: typing.Dict[str, typing.Any]

    def __init__(self, requestor=None, server=None, req_opts={}):
        self._requestor = requestor or requests.Session()
        self._req_opts = req_opts
        if server:
            self._server = server
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
    def subclass_from_spec(base_cls, spec: typing.Dict, client_name="ApiClient"):
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

    def __getattr__(self, a):
        # raw function
        func = getattr(self._sub_api, a)
        # bind to client
        return func.__get__(self._client)
