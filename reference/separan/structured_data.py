"""Strict YAML data conversion and a safe XML document model."""

from copy import deepcopy
from dataclasses import dataclass
from html import escape as html_escape
from io import StringIO
import math
import re
import unicodedata
import xml.etree.ElementTree as ET

import yaml

from .errors import error
from .io_json import _atomic_write
from .objects import ObjectValue
from .system_utilities import UtilityFunction


MAX_DOCUMENT_BYTES = 8_000_000
MAX_NODES = 100_000
MAX_DEPTH = 100
UNSAFE_XML = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
XML_ENTITY = re.compile(r"&(?:lt|gt|amp|quot|apos|#[0-9]+|#x[0-9A-Fa-f]+);")


class StrictYamlLoader(yaml.SafeLoader):
    pass


# Dates are strings in Separan unless the program explicitly calls datetime_parse().
StrictYamlLoader.yaml_implicit_resolvers = {
    key: [(tag, expression) for tag, expression in values if tag not in {
        "tag:yaml.org,2002:timestamp", "tag:yaml.org,2002:bool",
        "tag:yaml.org,2002:int", "tag:yaml.org,2002:float",
    }]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}

StrictYamlLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"),
)
StrictYamlLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int",
    re.compile(r"^[-+]?(?:[0-9][0-9_]*|0[bB][0-1_]+|0[oO][0-7_]+|0[xX][0-9A-Fa-f_]+)$"),
    list("-+0123456789"),
)
StrictYamlLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^[-+]?(?:(?:[0-9][0-9_]*)?\.[0-9_]+(?:[eE][-+]?[0-9]+)?|[0-9][0-9_]*[eE][-+]?[0-9]+|\.(?:inf|Inf|INF|nan|NaN|NAN))$"),
    list("-+0123456789."),
)


def _yaml_integer(loader, node):
    text = loader.construct_scalar(node).replace("_", "")
    sign = -1 if text.startswith("-") else 1
    unsigned = text[1:] if text[:1] in "+-" else text
    lowered = unsigned.lower()
    if lowered.startswith("0b"): return sign * int(unsigned[2:], 2)
    if lowered.startswith("0o"): return sign * int(unsigned[2:], 8)
    if lowered.startswith("0x"): return sign * int(unsigned[2:], 16)
    return sign * int(unsigned, 10)


def _yaml_float(loader, node):
    text = loader.construct_scalar(node).replace("_", "").lower()
    if text in (".inf", "+.inf"): return float("inf")
    if text == "-.inf": return float("-inf")
    if text in (".nan", "+.nan", "-.nan"): return float("nan")
    return float(text)


StrictYamlLoader.add_constructor("tag:yaml.org,2002:int", _yaml_integer)
StrictYamlLoader.add_constructor("tag:yaml.org,2002:float", _yaml_float)


def _strict_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if type(key) is not str:
            raise yaml.constructor.ConstructorError("while constructing a mapping", node.start_mark, "mapping keys must be strings", key_node.start_mark)
        if key in result:
            raise yaml.constructor.ConstructorError("while constructing a mapping", node.start_mark, f"duplicate mapping key: {key}", key_node.start_mark)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


StrictYamlLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _strict_mapping)


def _text(value, name, position, runtime):
    if type(value) is not str:
        runtime.type_error(position, "string", runtime.type_name(value), f"{name}() requires a string.")
    if len(value.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise error("E943", "yaml_limit_error", f"{name}() input exceeds the document size limit.", position, expected=f"at most {MAX_DOCUMENT_BYTES} UTF-8 bytes")
    return value


def _yaml_error(exc, position, path=None):
    mark = getattr(exc, "problem_mark", None)
    location = None if mark is None else f"line {mark.line + 1}, column {mark.column + 1}"
    description = getattr(exc, "problem", None) or str(exc)
    if path: description = f"{path}: {description}"
    raise error("E940", "yaml_parse_error", description, position, actual=location)


def _yaml_documents(text, position, runtime, path=None):
    _text(text, "yaml_to_object", position, runtime)
    try:
        loaded = list(yaml.load_all(text, Loader=StrictYamlLoader))
    except yaml.YAMLError as exc:
        _yaml_error(exc, position, path)
    budget = [0]
    return [_from_yaml(value, position, runtime, set(), 0, budget) for value in loaded]


def _from_yaml(value, position, runtime, ancestors, depth, budget):
    budget[0] += 1
    if budget[0] > MAX_NODES or depth > MAX_DEPTH:
        raise error("E943", "yaml_limit_error", "YAML structure exceeds the node or nesting limit.", position)
    if value is None or type(value) in (str, bool, int): return value
    if type(value) is float:
        if not math.isfinite(value): raise error("E942", "yaml_type_error", "YAML non-finite numbers are not supported.", position)
        return value
    if type(value) in (list, dict):
        identity = id(value)
        if identity in ancestors: raise error("E943", "yaml_limit_error", "Recursive YAML aliases are not supported.", position)
        nested = set(ancestors); nested.add(identity)
        if type(value) is list:
            result = [_from_yaml(item, position, runtime, nested, depth + 1, budget) for item in value]
            from .interpreter import list_element_type
            try: list_element_type(result, position)
            except Exception as exc:
                if getattr(exc, "code", None) == "E203":
                    raise error("E942", "yaml_type_error", "YAML sequence contains mixed Separan value types.", position, expected=exc.expected, actual=exc.actual)
                raise
            return result
        return ObjectValue.create({key: _from_yaml(item, position, runtime, nested, depth + 1, budget) for key, item in value.items()})
    raise error("E942", "yaml_type_error", f"YAML value type '{type(value).__name__}' is not supported.", position)


def _to_data(value, position, ancestors=None, depth=0, budget=None):
    ancestors = set() if ancestors is None else ancestors
    budget = [0] if budget is None else budget
    budget[0] += 1
    if budget[0] > MAX_NODES or depth > MAX_DEPTH:
        raise error("E943", "yaml_limit_error", "Value exceeds the YAML node or nesting limit.", position)
    if value is None or type(value) in (str, bool, int): return value
    if type(value) is float:
        if not math.isfinite(value): raise error("E941", "yaml_encode_error", "YAML cannot encode a non-finite number.", position)
        return value
    if type(value) is list:
        identity = id(value)
        if identity in ancestors: raise error("E943", "yaml_limit_error", "Recursive lists cannot be encoded as YAML.", position)
        return [_to_data(item, position, ancestors | {identity}, depth + 1, budget) for item in value]
    if isinstance(value, ObjectValue):
        identity = id(value)
        if identity in ancestors: raise error("E943", "yaml_limit_error", "Recursive objects cannot be encoded as YAML.", position)
        return {key: _to_data(item, position, ancestors | {identity}, depth + 1, budget) for key, item in value.fields.items()}
    raise error("E941", "yaml_encode_error", f"Type '{runtime_type(value)}' is not YAML-compatible.", position)


def runtime_type(value): return type(value).__name__


def _yaml_options(named, position, runtime):
    indent, sort_keys = named.get("indent", 2), named.get("sort_keys", False)
    if type(indent) is not int or not 2 <= indent <= 8:
        runtime.type_error(position, "integer indent from 2 through 8", runtime.type_name(indent), "YAML indent must be an integer from 2 through 8.")
    if type(sort_keys) is not bool:
        runtime.type_error(position, "boolean sort_keys", runtime.type_name(sort_keys), "YAML sort_keys must be boolean.")
    return indent, sort_keys


def _dump_yaml(values, named, position, runtime, multiple=False):
    indent, sort_keys = _yaml_options(named, position, runtime)
    try:
        if multiple:
            data = [_to_data(value, position) for value in values]
            return yaml.safe_dump_all(data, allow_unicode=True, sort_keys=sort_keys, indent=indent, explicit_start=True)
        return yaml.safe_dump(_to_data(values, position), allow_unicode=True, sort_keys=sort_keys, indent=indent)
    except yaml.YAMLError as exc: raise error("E941", "yaml_encode_error", str(exc), position)


def _read_file(path_text, name, position, runtime, limit_code="E943", limit_category="yaml_limit_error"):
    runtime.capabilities.require(runtime.capabilities.read_files, name, position)
    path = runtime.capabilities.path(path_text, name, position)
    try:
        if path.stat().st_size > MAX_DOCUMENT_BYTES: raise error(limit_code, limit_category, "Structured-data file exceeds the size limit.", position, actual=path_text)
        return path.read_text(encoding="utf-8")
    except OSError as exc: raise error("E722", "I/O error", str(exc), position, actual=path_text)
    except UnicodeError as exc: raise error("E722", "I/O error", f"File is not valid UTF-8: {exc}", position, actual=path_text)


def _write_file(path_text, text, name, position, runtime):
    runtime.capabilities.require(runtime.capabilities.write_files, name, position)
    path = runtime.capabilities.path(path_text, name, position)
    _atomic_write(path, text.encode("utf-8"), position)
    return None


def yaml_to_object(args, named, position, runtime):
    documents = _yaml_documents(args[0], position, runtime)
    if len(documents) > 1: raise error("E940", "yaml_parse_error", "yaml_to_object() accepts exactly one YAML document; use yaml_to_objects() for a stream.", position, expected="0 or 1 document", actual=str(len(documents)))
    return documents[0] if documents else None


def yaml_to_objects(args, named, position, runtime):
    documents = _yaml_documents(args[0], position, runtime)
    from .interpreter import list_element_type
    try: list_element_type(documents, position)
    except Exception as exc:
        if getattr(exc, "code", None) == "E203": raise error("E942", "yaml_type_error", "YAML stream documents must have one Separan value type.", position, expected=exc.expected, actual=exc.actual)
        raise
    return documents


def object_to_yaml(args, named, position, runtime): return _dump_yaml(args[0], named, position, runtime)
def objects_to_yaml(args, named, position, runtime):
    if type(args[0]) is not list: runtime.type_error(position, "list", runtime.type_name(args[0]), "objects_to_yaml() requires a list of documents.")
    return _dump_yaml(args[0], named, position, runtime, True)


def yaml_file_to_object(args, named, position, runtime):
    documents = _yaml_documents(_read_file(args[0], "yaml_file_to_object", position, runtime), position, runtime, args[0])
    if len(documents) > 1: raise error("E940", "yaml_parse_error", "YAML file contains multiple documents; use yaml_file_to_objects().", position, actual=str(len(documents)))
    return documents[0] if documents else None


def yaml_file_to_objects(args, named, position, runtime):
    documents = _yaml_documents(_read_file(args[0], "yaml_file_to_objects", position, runtime), position, runtime, args[0])
    from .interpreter import list_element_type
    try: list_element_type(documents, position)
    except Exception as exc:
        if getattr(exc, "code", None) == "E203": raise error("E942", "yaml_type_error", "YAML stream documents must have one Separan value type.", position, expected=exc.expected, actual=exc.actual)
        raise
    return documents


def object_to_yaml_file(args, named, position, runtime):
    return _write_file(args[0], _dump_yaml(args[1], named, position, runtime), "object_to_yaml_file", position, runtime)


def objects_to_yaml_file(args, named, position, runtime):
    if type(args[1]) is not list: runtime.type_error(position, "list", runtime.type_name(args[1]), "objects_to_yaml_file() requires a list of documents.")
    return _write_file(args[0], _dump_yaml(args[1], named, position, runtime, True), "objects_to_yaml_file", position, runtime)


def yaml_validate(args, named, position, runtime): _yaml_documents(args[0], position, runtime); return True
def yaml_validate_file(args, named, position, runtime): _yaml_documents(_read_file(args[0], "yaml_validate_file", position, runtime), position, runtime, args[0]); return True


@dataclass(eq=False)
class XmlDocumentValue:
    root: object
    namespaces: dict


@dataclass(eq=False)
class XmlElementValue:
    element: object
    namespaces: dict


def _xml_source(text, name, position, runtime):
    if type(text) is not str: runtime.type_error(position, "string", runtime.type_name(text), f"{name}() requires XML text.")
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES: raise error("E953", "xml_limit_error", "XML document exceeds the size limit.", position)
    if UNSAFE_XML.search(text): raise error("E952", "xml_security_error", "DTD and entity declarations are disabled.", position)
    return text


def _xml_parse(text, name, position, runtime, path=None):
    text = _xml_source(text, name, position, runtime)
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        root = ET.fromstring(text, parser=parser)
        namespaces = {}
        for _, (prefix, uri) in ET.iterparse(StringIO(text), events=("start-ns",)):
            namespaces.setdefault(uri, prefix or "")
        _check_xml_tree(root, position)
        return XmlDocumentValue(root, namespaces)
    except ET.ParseError as exc:
        line, column = getattr(exc, "position", (None, None))
        where = None if line is None else f"line {line}, column {column + 1}"
        description = f"{path}: {exc}" if path else str(exc)
        raise error("E950", "xml_parse_error", description, position, actual=where)


def _check_xml_tree(root, position):
    count, stack = 0, [(root, 0)]
    while stack:
        node, depth = stack.pop(); count += 1
        if count > MAX_NODES or depth > MAX_DEPTH: raise error("E953", "xml_limit_error", "XML structure exceeds the node or nesting limit.", position)
        stack.extend((child, depth + 1) for child in list(node))


def _document(value, name, position, runtime):
    if not isinstance(value, XmlDocumentValue): runtime.type_error(position, "xml_document", runtime.type_name(value), f"{name}() requires an XML document.")
    return value


def _element(value, name, position, runtime):
    if not isinstance(value, XmlElementValue): runtime.type_error(position, "xml_element", runtime.type_name(value), f"{name}() requires an XML element.")
    return value


def _local_name(tag): return tag.split("}", 1)[1] if type(tag) is str and tag.startswith("{") else tag
def _namespace_uri(tag): return tag[1:].split("}", 1)[0] if type(tag) is str and tag.startswith("{") else None


def _valid_xml_name(value):
    if type(value) is not str or not value or ":" in value: return False
    first = value[0]
    if first != "_" and not first.isalpha(): return False
    return all(character in "_.-" or character.isalpha() or character.isdigit() or unicodedata.category(character).startswith("M") for character in value[1:])


def _name(value, label, position):
    if not _valid_xml_name(value): raise error("E951", "xml_model_error", f"{label} must be an XML name without a namespace prefix.", position, actual=repr(value))
    return value


def _qualified_name(value, namespace, label, position, runtime):
    local = _name(value, label, position)
    if namespace is None: return local
    if type(namespace) is not str or not namespace:
        runtime.type_error(position, "non-empty string namespace_uri", runtime.type_name(namespace), "namespace_uri must be a non-empty string.")
    return f"{{{namespace}}}{local}"


def xml_document_parse(args, named, position, runtime): return _xml_parse(args[0], "xml_document_parse", position, runtime)
def xml_document_read(args, named, position, runtime): return _xml_parse(_read_file(args[0], "xml_document_read", position, runtime, "E953", "xml_limit_error"), "xml_document_read", position, runtime, args[0])
def xml_root(args, named, position, runtime):
    document = _document(args[0], "xml_root", position, runtime); return XmlElementValue(document.root, document.namespaces)


def _xml_format(document, named, position, runtime):
    indent, declaration = named.get("indent", 2), named.get("declaration", True)
    if type(indent) is not int or not 0 <= indent <= 8: runtime.type_error(position, "integer indent from 0 through 8", runtime.type_name(indent), "XML indent must be an integer from 0 through 8.")
    if type(declaration) is not bool: runtime.type_error(position, "boolean declaration", runtime.type_name(declaration), "XML declaration must be boolean.")
    root = deepcopy(document.root)
    if indent: ET.indent(root, space=" " * indent)
    body = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' if declaration else "") + body


def xml_document_to_text(args, named, position, runtime): return _xml_format(_document(args[0], "xml_document_to_text", position, runtime), named, position, runtime)
def xml_document_write(args, named, position, runtime): return _write_file(args[0], _xml_format(_document(args[1], "xml_document_write", position, runtime), named, position, runtime), "xml_document_write", position, runtime)


def _node_to_object(element, namespaces, position, depth=0, budget=None):
    budget = [0] if budget is None else budget; budget[0] += 1
    if budget[0] > MAX_NODES or depth > MAX_DEPTH: raise error("E953", "xml_limit_error", "XML structure exceeds the conversion limit.", position)
    children = [_node_to_object(child, namespaces, position, depth + 1, budget) for child in list(element) if type(child.tag) is str]
    fields = {
        "name": _local_name(element.tag),
        "namespace_uri": _namespace_uri(element.tag),
        "attributes": ObjectValue.create(dict(element.attrib)),
        "text": element.text or "",
        "children": children,
    }
    return ObjectValue.create(fields)


def xml_to_object(args, named, position, runtime):
    document = _xml_parse(args[0], "xml_to_object", position, runtime); return _node_to_object(document.root, document.namespaces, position)
def xml_file_to_object(args, named, position, runtime):
    document = _xml_parse(_read_file(args[0], "xml_file_to_object", position, runtime, "E953", "xml_limit_error"), "xml_file_to_object", position, runtime, args[0]); return _node_to_object(document.root, document.namespaces, position)


def _object_to_element(value, position, runtime, depth=0, budget=None):
    budget = [0] if budget is None else budget; budget[0] += 1
    if budget[0] > MAX_NODES or depth > MAX_DEPTH: raise error("E953", "xml_limit_error", "XML object exceeds the conversion limit.", position)
    if not isinstance(value, ObjectValue): runtime.type_error(position, "XML node object", runtime.type_name(value), "XML node must be an object.")
    required = {"name", "attributes", "text", "children"}
    missing = required - set(value.fields)
    if missing: raise error("E951", "xml_model_error", "XML node object is missing required fields.", position, actual=sorted(missing)[0])
    name = _name(value.fields["name"], "XML element name", position); namespace = value.fields.get("namespace_uri")
    if namespace is not None and (type(namespace) is not str or not namespace): runtime.type_error(position, "string or null namespace_uri", runtime.type_name(namespace), "XML namespace_uri must be a non-empty string or null.")
    attributes = value.fields["attributes"]
    if not isinstance(attributes, ObjectValue): runtime.type_error(position, "object<string,string> attributes", runtime.type_name(attributes), "XML attributes must be an object.")
    clean_attributes = {}
    for key, item in attributes.fields.items():
        if key.startswith("{") and "}" in key:
            uri, local = key[1:].split("}", 1)
            if not uri: raise error("E951", "xml_model_error", "XML attribute namespace URI cannot be empty.", position, actual=key)
            _name(local, "XML attribute name", position)
        else: _name(key, "XML attribute name", position)
        if type(item) is not str: runtime.type_error(position, "string attribute value", runtime.type_name(item), "XML attribute values must be strings.")
        clean_attributes[key] = item
    text, children = value.fields["text"], value.fields["children"]
    if type(text) is not str: runtime.type_error(position, "string text", runtime.type_name(text), "XML element text must be a string.")
    if type(children) is not list: runtime.type_error(position, "list<object> children", runtime.type_name(children), "XML children must be a list.")
    element = ET.Element(f"{{{namespace}}}{name}" if namespace else name, clean_attributes); element.text = text
    for child in children: element.append(_object_to_element(child, position, runtime, depth + 1, budget))
    return element


def object_to_xml(args, named, position, runtime):
    document = XmlDocumentValue(_object_to_element(args[0], position, runtime), {}); return _xml_format(document, named, position, runtime)
def object_to_xml_file(args, named, position, runtime): return _write_file(args[0], object_to_xml([args[1]], named, position, runtime), "object_to_xml_file", position, runtime)


def xml_create_element(args, named, position, runtime):
    name = _name(args[0], "XML element name", position); namespace = named.get("namespace_uri")
    if namespace is not None and (type(namespace) is not str or not namespace): runtime.type_error(position, "string namespace_uri", runtime.type_name(namespace), "namespace_uri must be a non-empty string.")
    return XmlElementValue(ET.Element(f"{{{namespace}}}{name}" if namespace else name), {})


def xml_element_name(args, named, position, runtime): return _local_name(_element(args[0], "xml_element_name", position, runtime).element.tag)
def xml_element_text(args, named, position, runtime): return _element(args[0], "xml_element_text", position, runtime).element.text or ""
def xml_set_element_text(args, named, position, runtime):
    item = _element(args[0], "xml_set_element_text", position, runtime)
    if type(args[1]) is not str: runtime.type_error(position, "string", runtime.type_name(args[1]), "XML element text must be a string.")
    item.element.text = args[1]; return None


def xml_get_attribute(args, named, position, runtime):
    item = _element(args[0], "xml_get_attribute", position, runtime); key = _qualified_name(args[1], named.get("namespace_uri"), "XML attribute name", position, runtime); return item.element.attrib.get(key)
def xml_set_attribute(args, named, position, runtime):
    item = _element(args[0], "xml_set_attribute", position, runtime); key = _qualified_name(args[1], named.get("namespace_uri"), "XML attribute name", position, runtime)
    if type(args[2]) is not str: runtime.type_error(position, "string", runtime.type_name(args[2]), "XML attribute value must be a string.")
    item.element.set(key, args[2]); return None
def xml_remove_attribute(args, named, position, runtime):
    item = _element(args[0], "xml_remove_attribute", position, runtime); key = _qualified_name(args[1], named.get("namespace_uri"), "XML attribute name", position, runtime)
    if key not in item.element.attrib: raise error("E951", "xml_model_error", "XML attribute does not exist.", position, actual=key)
    del item.element.attrib[key]; return None


def xml_children(args, named, position, runtime):
    item = _element(args[0], "xml_children", position, runtime); return [XmlElementValue(child, item.namespaces) for child in list(item.element) if type(child.tag) is str]
def xml_child(args, named, position, runtime):
    item = _element(args[0], "xml_child", position, runtime); name = _name(args[1], "XML child name", position)
    found = next((child for child in list(item.element) if type(child.tag) is str and _local_name(child.tag) == name), None)
    return None if found is None else XmlElementValue(found, item.namespaces)
def xml_add_child(args, named, position, runtime):
    parent = _element(args[0], "xml_add_child", position, runtime); child = _element(args[1], "xml_add_child", position, runtime)
    if child.element in list(parent.element): raise error("E951", "xml_model_error", "XML element is already a direct child of the parent.", position)
    parent.element.append(child.element); return None
def xml_remove_child(args, named, position, runtime):
    parent = _element(args[0], "xml_remove_child", position, runtime); child = _element(args[1], "xml_remove_child", position, runtime)
    if child.element not in list(parent.element): raise error("E951", "xml_model_error", "XML element is not a direct child of the parent.", position)
    parent.element.remove(child.element); return None


def xml_namespace_uri(args, named, position, runtime): return _namespace_uri(_element(args[0], "xml_namespace_uri", position, runtime).element.tag)
def xml_namespace_prefix(args, named, position, runtime):
    item = _element(args[0], "xml_namespace_prefix", position, runtime); uri = _namespace_uri(item.element.tag)
    return None if uri is None else item.namespaces.get(uri)


def _path_parts(path, position, runtime):
    if type(path) is not str: runtime.type_error(position, "string path", runtime.type_name(path), "XML search path must be a string.")
    if not path or "//" in path or path.endswith("/"): raise error("E954", "xml_path_error", "XML path must be a simple slash-separated element path.", position, actual=path)
    absolute = path.startswith("/"); parts = path.lstrip("/").split("/")
    for part in parts:
        if part != "*": _name(part, "XML path segment", position)
    return absolute, parts


def _find_all(args, position, runtime):
    target, path = args; absolute, parts = _path_parts(path, position, runtime)
    if isinstance(target, XmlDocumentValue): roots, namespaces = [target.root], target.namespaces
    elif isinstance(target, XmlElementValue):
        if absolute: raise error("E954", "xml_path_error", "Absolute XML paths require an xml_document.", position, actual=path)
        roots, namespaces = [target.element], target.namespaces
    else: runtime.type_error(position, "xml_document or xml_element", runtime.type_name(target), "XML search requires a document or element.")
    if absolute:
        first = parts.pop(0)
        if first != "*" and _local_name(roots[0].tag) != first: return []
    for part in parts:
        roots = [child for root in roots for child in list(root) if type(child.tag) is str and (part == "*" or _local_name(child.tag) == part)]
    return [XmlElementValue(item, namespaces) for item in roots]


def xml_find_all(args, named, position, runtime): return _find_all(args, position, runtime)
def xml_find(args, named, position, runtime):
    found = _find_all(args, position, runtime); return found[0] if found else None


def xml_escape_text(args, named, position, runtime):
    value = args[0]
    if type(value) is not str: runtime.type_error(position, "string", runtime.type_name(value), "xml_escape_text() requires a string.")
    if len(value.encode("utf-8")) > MAX_DOCUMENT_BYTES: raise error("E953", "xml_limit_error", "XML text exceeds the size limit.", position)
    return html_escape(value, quote=False)
def xml_escape_attribute(args, named, position, runtime):
    value = args[0]
    if type(value) is not str: runtime.type_error(position, "string", runtime.type_name(value), "xml_escape_attribute() requires a string.")
    if len(value.encode("utf-8")) > MAX_DOCUMENT_BYTES: raise error("E953", "xml_limit_error", "XML attribute text exceeds the size limit.", position)
    return html_escape(value, quote=True)


def _xml_character(code, position):
    if code > 0x10FFFF or 0xD800 <= code <= 0xDFFF or (code < 0x20 and code not in (9, 10, 13)):
        raise error("E955", "xml_escape_error", "XML character reference is outside the allowed XML character set.", position, actual=str(code))
    return chr(code)


def xml_unescape(args, named, position, runtime):
    value = args[0]
    if type(value) is not str: runtime.type_error(position, "string", runtime.type_name(value), "xml_unescape() requires a string.")
    if len(value.encode("utf-8")) > MAX_DOCUMENT_BYTES: raise error("E953", "xml_limit_error", "XML escaped text exceeds the size limit.", position)
    index = 0
    while True:
        index = value.find("&", index)
        if index < 0: break
        match = XML_ENTITY.match(value, index)
        if match is None: raise error("E955", "xml_escape_error", "XML text contains an unknown or unfinished entity reference.", position, actual=value[index:index + 16])
        index = match.end()
    names = {"&lt;": "<", "&gt;": ">", "&amp;": "&", "&quot;": '"', "&apos;": "'"}
    def replace(match):
        token = match.group(0)
        if token in names: return names[token]
        body = token[2:-1]
        return _xml_character(int(body[1:], 16) if body.startswith("x") else int(body), position)
    return XML_ENTITY.sub(replace, value)


YAML_OPTIONS = ("indent", "sort_keys")
XML_OPTIONS = ("indent", "declaration")
XML_NAMESPACE_OPTION = ("namespace_uri",)
STRUCTURED_DATA_BUILTINS = (
    UtilityFunction("yaml_to_object", 1, 1, yaml_to_object), UtilityFunction("object_to_yaml", 1, 1, object_to_yaml, YAML_OPTIONS),
    UtilityFunction("yaml_file_to_object", 1, 1, yaml_file_to_object), UtilityFunction("object_to_yaml_file", 2, 2, object_to_yaml_file, YAML_OPTIONS),
    UtilityFunction("yaml_to_objects", 1, 1, yaml_to_objects), UtilityFunction("objects_to_yaml", 1, 1, objects_to_yaml, YAML_OPTIONS),
    UtilityFunction("yaml_file_to_objects", 1, 1, yaml_file_to_objects), UtilityFunction("objects_to_yaml_file", 2, 2, objects_to_yaml_file, YAML_OPTIONS),
    UtilityFunction("yaml_validate", 1, 1, yaml_validate), UtilityFunction("yaml_validate_file", 1, 1, yaml_validate_file),
    UtilityFunction("xml_to_object", 1, 1, xml_to_object), UtilityFunction("object_to_xml", 1, 1, object_to_xml, XML_OPTIONS),
    UtilityFunction("xml_file_to_object", 1, 1, xml_file_to_object), UtilityFunction("object_to_xml_file", 2, 2, object_to_xml_file, XML_OPTIONS),
    UtilityFunction("xml_document_parse", 1, 1, xml_document_parse), UtilityFunction("xml_document_read", 1, 1, xml_document_read),
    UtilityFunction("xml_document_to_text", 1, 1, xml_document_to_text, XML_OPTIONS), UtilityFunction("xml_document_write", 2, 2, xml_document_write, XML_OPTIONS),
    UtilityFunction("xml_create_element", 1, 1, xml_create_element, ("namespace_uri",)), UtilityFunction("xml_root", 1, 1, xml_root),
    UtilityFunction("xml_element_name", 1, 1, xml_element_name), UtilityFunction("xml_element_text", 1, 1, xml_element_text), UtilityFunction("xml_set_element_text", 2, 2, xml_set_element_text),
    UtilityFunction("xml_get_attribute", 2, 2, xml_get_attribute, XML_NAMESPACE_OPTION), UtilityFunction("xml_set_attribute", 3, 3, xml_set_attribute, XML_NAMESPACE_OPTION), UtilityFunction("xml_remove_attribute", 2, 2, xml_remove_attribute, XML_NAMESPACE_OPTION),
    UtilityFunction("xml_children", 1, 1, xml_children), UtilityFunction("xml_child", 2, 2, xml_child), UtilityFunction("xml_add_child", 2, 2, xml_add_child), UtilityFunction("xml_remove_child", 2, 2, xml_remove_child),
    UtilityFunction("xml_find", 2, 2, xml_find), UtilityFunction("xml_find_all", 2, 2, xml_find_all),
    UtilityFunction("xml_namespace_uri", 1, 1, xml_namespace_uri), UtilityFunction("xml_namespace_prefix", 1, 1, xml_namespace_prefix),
    UtilityFunction("xml_escape_text", 1, 1, xml_escape_text), UtilityFunction("xml_escape_attribute", 1, 1, xml_escape_attribute), UtilityFunction("xml_unescape", 1, 1, xml_unescape),
)
