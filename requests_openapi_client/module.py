import json
import requests

from .schemas import add_types_to_module
from .core import BaseClient

def load_spec_from_url(url):
    r = requests.get(url)
    r.raise_for_status()

    return json.load(r.text, Loader=yaml.Loader)


def load_spec_from_file(file_path):
    with open(file_path) as f:
        spec_str = f.read()

    return json.load(spec_str, Loader=yaml.Loader)

def build_client_module(spec, module):
    models = add_types_to_module(spec, module)
    client_class = BaseClient.subclass_from_spec(spec, available_types=models)
    setattr(module, client_class.__name__, client_class)
