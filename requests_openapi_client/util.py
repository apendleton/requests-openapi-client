import re

CAMEL_NAME_RE = re.compile('(.)([A-Z][a-z]+)')
CAMEL_RE = re.compile('([a-z0-9])([A-Z])')
MULTI_UNDER_RE = re.compile(r'_{2,}')
def camel_to_snake(name):
    name = name.replace(' ', '_')
    name = CAMEL_NAME_RE.sub(r'\1_\2', name)
    name = CAMEL_RE.sub(r'\1_\2', name).lower().replace("-", "_")
    return MULTI_UNDER_RE.sub('_', name)
