# requests-openapi-client

`requests-openapi-client` is a python client library for OpenAPI 3.0. It's an opinionated fork of [requests-openapi](https://github.com/wy-z/requests-openapi), a great light-weight OpenAPI client built on `requests`, that tries to strike a balance between very simple API wrappers like that one, and heavy code-generation-based wrappers like the Swagger client library generator.

## Differences from lightweight wrappers
* DTOs have realized types that can be instantiated; API methods return instances of these types, and expect them as input
* Clients have realized methods for each API endpoint that are discoverable in a REPL and have type annotations for paramaters
* APIs are translated into idiomatic Python (e.g., snake case instead of camel case)

## Differences from heavy wrappers
* Types, methods, and clients are generated on the fly at runtime; there's no explicit manual code generation step
* No deliberate schema validation (there may be some inadvertent validation if data is wildly schema-nonconforming)
* Incomplete OpenAPI support

## Usage

```python
import json, sys
from requests_openapi_client import build_client_module_from_url

build_client_module_from_url("https://raw.githubusercontent.com/OAI/OpenAPI-Specification/main/examples/v3.0/uspto.json", sys.modules[__name__])

client = ApiClient(url="https://developer.uspto.gov/ds-api")
print(client.metadata.list_data_sets())
```

## Installation

```
pip install requests-openapi
```

## Licennse

MIT
