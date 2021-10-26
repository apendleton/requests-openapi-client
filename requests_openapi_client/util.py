import re

CAMEL_NAME_RE = re.compile('(.)([A-Z][a-z]+)')
CAMEL_RE = re.compile('([a-z0-9])([A-Z])')
def camel_to_snake(name):
    name = CAMEL_NAME_RE.sub(r'\1_\2', name)
    return CAMEL_RE.sub(r'\1_\2', name).lower().replace("-", "_")
