import json
import requests

from .schemas import add_types_to_module
from .core import BaseClient

def load_spec_from_url(url):
    r = requests.get(url)
    r.raise_for_status()

    return r.json()


def load_spec_from_file(file_path):
    return json.load(open(file_path))

def build_client_module(spec, module):
    models = add_types_to_module(spec, module)
    client_class = BaseClient.subclass_from_spec(spec, available_types=models)
    setattr(module, client_class.__name__, client_class)

def build_client_module_from_url(url, module):
    spec = load_spec_from_url(url)
    build_client_module(spec, module)

def build_client_module_from_file(file_path, module):
    spec = load_spec_from_file(file_path)
    build_client_module(spec, module)
