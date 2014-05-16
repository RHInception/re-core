#!/usr/bin/env python
import jsonschema
from jsonschema import Draft4Validator

import json
from pprint import pprint as p

with open('examples/project.json') as proj:
    input = json.loads(proj.read())

with open('examples/schema.json') as s:
    schema = json.loads(s.read())

res = jsonschema.validate(input, schema)
res = Draft4Validator.check_schema(schema)
print res
