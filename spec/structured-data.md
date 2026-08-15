# YAML and XML structured data

Status: **experimental preview implemented in v0.2.0-alpha.5**.

YAML is a data-conversion API. XML is a document-structure API. Separan keeps
the two models separate instead of pretending that every XML document is an
ordinary object.

## YAML

```separan
config = yaml_file_to_object("monitor.yaml")
print config.targets.ec2.WEB01.instance_id

object_to_yaml_file(
    "generated/template.yaml",
    template,
    indent = 2,
    sort_keys = false
)
```

Implemented functions:

- `yaml_to_object(text)` / `object_to_yaml(value[, indent, sort_keys])`
- `yaml_file_to_object(path)` / `object_to_yaml_file(path, value[, options])`
- `yaml_to_objects(text)` / `objects_to_yaml(values[, options])`
- `yaml_file_to_objects(path)` / `objects_to_yaml_file(path, values[, options])`
- `yaml_validate(text)` / `yaml_validate_file(path)`

The names say `object` for a readable conversion direction, but scalar and list
document roots are also accepted. Empty input maps to `null`; an empty stream
maps to `[]`. A single-document API rejects a stream containing two or more
documents. A multi-document result must remain a homogeneous Separan list.

Mapping rules are `null -> null`, boolean -> `boolean`, integer/float ->
`number`, scalar text -> `string`, sequence -> homogeneous `list`, and mapping
-> insertion-ordered `object`. Mapping keys must be strings. Duplicate keys,
unsupported tags, non-finite numbers, mixed lists, recursive aliases, excessive
nesting, and excessive node counts are errors.

Scalar resolution follows an intentionally unambiguous YAML 1.2-style core
subset. Only `true` and `false` are booleans; `yes`, `no`, `on`, and `off` are
strings. `012` is decimal twelve. Binary, octal, and hexadecimal integers
require `0b`, `0o`, and `0x`. Timestamps remain strings until an explicit
Separan datetime conversion is called.

The loader accepts only safe standard YAML tags and never constructs arbitrary
Python objects. `indent` is 2 through 8. `sort_keys` defaults to `false`, so
object declaration order is retained. Conversion does not preserve comments,
blank lines, scalar style, anchors, or aliases. A future round-trip document API
may preserve those syntax details. CloudFormation tags belong to a separate
adapter and are not part of the generic YAML API.

## XML

```separan
document = xml_document_read("config.xml")
root = xml_root(document)
server = xml_find(document, "/config/servers/server")
print xml_get_attribute(server, "enabled")
xml_set_element_text(xml_child(server, "name"), "WEB01")
xml_document_write("generated.xml", document, indent = 2)
```

Core document functions:

- `xml_document_parse`, `xml_document_read`, `xml_document_to_text`,
  `xml_document_write`
- `xml_create_element`, `xml_root`
- `xml_element_name`, `xml_element_text`, `xml_set_element_text`
- `xml_get_attribute`, `xml_set_attribute`, `xml_remove_attribute`
- `xml_children`, `xml_child`, `xml_add_child`, `xml_remove_child`
- `xml_find`, `xml_find_all`
- `xml_namespace_uri`, `xml_namespace_prefix`
- `xml_escape_text`, `xml_escape_attribute`, `xml_unescape`

`xml_find` and `xml_find_all` use a deliberately small direct-child path
language: slash-separated local names and `*`. Absolute paths require an
`xml_document`. XPath predicates, descendant `//`, parent traversal, and
function calls are not accepted.

Attribute functions accept an optional explicit `namespace_uri`; prefixes are
never smuggled into the attribute name string.

The convenience conversion functions `xml_to_object`, `object_to_xml`,
`xml_file_to_object`, and `object_to_xml_file` use this explicit node shape:

```text
name: string
namespace_uri: string | null
attributes: object<string,string>
text: string
children: list<object>
```

This does not flatten attributes into child fields. Mixed content tails,
comments, processing instructions, and namespace prefix spelling are not part
of the object conversion contract. The document model preserves tree semantics,
comments, mixed content, and attribute order, but serializers may normalize
namespace prefix spelling and insignificant formatting. It is the correct API
when XML structure, rather than exact source bytes, matters.

Output is UTF-8 and automatically escapes text and attribute values. The XML
declaration is enabled by default; `indent` accepts 0 through 8. DTD and entity
declarations are rejected before parsing. External entity, network entity, and
DTD loading are never enabled. Documents also have byte, depth, and node-count
limits.

YAML diagnostics occupy `E940`-`E949`; XML diagnostics occupy `E950`-`E959`.
Both families are catchable through `yaml_error` and `xml_error`.
