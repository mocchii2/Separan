const vscode = require("vscode");
const { execFile } = require("child_process");
const fs = require("fs");
const builtinMetadata = require("./data/builtins.json");
const path = require("path");
const { promisify } = require("util");

const execFileAsync = promisify(execFile);

let autoClosing = false;
let reviewOutput;
let runtimeOutput;
let structureRefreshTimer;
let runStatus;
let checkStatus;
let structureDiagnostics;
let nativeDiagnostics;
let analysisDiagnostics;
let diagnosticTimer;
const diagnosticVersions = new Map();
const temporaryRuns = new Map();

const blockPairs = {
  SEP: "END_SEP", if: "endif", while: "endwhile", for: "endfor",
  object: "end_object", list: "end_list", try: "endtry", error: "end_error",
  transaction: "end_transaction", http_route: "end_http_route",
};

const builtinSignatureOverrides = {
  print: "print(value)", print_error: "print_error(value)", type_of: "type_of(value)", length: "length(value)",
  string: "string(value)", number: "number(value)", boolean: "boolean(value)", format: "format(template, values...)",
  trim: "trim(value)", upper: "upper(value)", lower: "lower(value)", substring: "substring(value, start, end?)",
  split: "split(value, separator)", join: "join(values, separator)", replace: "replace(value, old, new)",
  list_append: "list_append(values, value)", first: "first(values)", last: "last(values)", slice: "slice(values, start, end)",
  map: "map(values, function)", filter: "filter(values, function)", reduce: "reduce(values, function, initial)",
  object_get: "object_get(object, key)", object_set: "object_set(object, key, value)", object_has: "object_has(object, key)",
  json_encode: "json_encode(value)", json_decode: "json_decode(text)", read_text: "read_text(path)", write_text: "write_text(path, text)",
  bytes_from_string: "bytes_from_string(value, encoding?)", string_from_bytes: "string_from_bytes(value, encoding?)",
  regex_find: "regex_find(pattern, text)", regex_find_all: "regex_find_all(pattern, text)", regex_replace: "regex_replace(pattern, text, replacement)",
  db_connect: "db_connect(driver:, database:, host?:, port?:, user?:, password?:)", db_query: "db_query(connection, query, parameters, timeout?:)",
  exec: "exec(command, arguments, cwd?:, timeout?:)", http_get: "http_get(url, headers?:, timeout?:)",
  duration: "duration(value)", datetime_parse: "datetime_parse(value)", random_int: "random_int(minimum, maximum)",
  len: "len(value: string | list | bytes) -> number", is_empty: "is_empty(value: value) -> boolean",
  type: "type(value: value) -> string", is_number: "is_number(value: value) -> boolean",
  is_string: "is_string(value: value) -> boolean", is_boolean: "is_boolean(value: value) -> boolean",
  is_list: "is_list(value: value) -> boolean", is_object: "is_object(value: value) -> boolean",
  is_bytes: "is_bytes(value: value) -> boolean", is_datetime: "is_datetime(value: value) -> boolean",
  is_duration: "is_duration(value: value) -> boolean", is_secret: "is_secret(value: value) -> boolean",
  abs: "abs(value: number) -> number", ceil: "ceil(value: number) -> number", floor: "floor(value: number) -> number",
  round: "round(value: number) -> number", sqrt: "sqrt(value: number) -> number",
  sin: "sin(value: number) -> number", cos: "cos(value: number) -> number", tan: "tan(value: number) -> number",
  log: "log(value: number) -> number", log10: "log10(value: number) -> number", log2: "log2(value: number) -> number",
  exp: "exp(value: number) -> number", pow: "pow(base: number, exponent: number) -> number",
  min: "min(value: number, values?: number...) -> number", max: "max(value: number, values?: number...) -> number",
  range: "range(start_or_stop: number, stop?: number, step?: number) -> list<number>",
  number_range: "number_range(start_or_stop: number, stop?: number, step?: number) -> list<number>",
  input: "input(prompt?: string) -> string", contains: "contains(value: string | list, search: value) -> boolean",
  starts_with: "starts_with(value: string, prefix: string) -> boolean", ends_with: "ends_with(value: string, suffix: string) -> boolean",
  compare: "compare(left: string, right: string) -> number", compare_ignore_case: "compare_ignore_case(left: string, right: string) -> number",
  substring_after: "substring_after(value: string, search: string) -> string", substring_before: "substring_before(value: string, search: string) -> string",
  count_occurrences: "count_occurrences(value: string, search: string) -> number",
  local_datetime: "local_datetime(value: string) -> local_datetime", timezone: "timezone(value: string) -> timezone",
  datetime_now: "datetime_now(timezone?: timezone) -> datetime", datetime_format: "datetime_format(value: datetime, format: string) -> string",
  datetime_valid: "datetime_valid(value: string, format: string, timezone: timezone) -> boolean",
  datetime_from_local: "datetime_from_local(value: local_datetime, timezone: timezone) -> datetime",
  datetime_in_timezone: "datetime_in_timezone(value: datetime, timezone: timezone) -> datetime",
  unix_time: "unix_time(value?: datetime) -> number", datetime_from_unix: "datetime_from_unix(value: number, timezone?: timezone) -> datetime",
  unix_milliseconds_from_datetime: "unix_milliseconds_from_datetime(value: datetime) -> number",
  unix_seconds_from_datetime: "unix_seconds_from_datetime(value: datetime) -> number",
  datetime_year: "datetime_year(value: datetime) -> number", datetime_month: "datetime_month(value: datetime) -> number",
  datetime_day: "datetime_day(value: datetime) -> number", datetime_hour: "datetime_hour(value: datetime) -> number",
  datetime_minute: "datetime_minute(value: datetime) -> number", datetime_second: "datetime_second(value: datetime) -> number",
  datetime_millisecond: "datetime_millisecond(value: datetime) -> number", datetime_weekday: "datetime_weekday(value: datetime) -> number",
  duration_milliseconds: "duration_milliseconds(value: duration) -> number",
  random_seed: "random_seed(seed: number) -> VOID", random_number: "random_number() -> number",
  random_float: "random_float(minimum: number, maximum: number) -> number", random_bool: "random_bool() -> boolean",
  random_pick: "random_pick(values: list) -> value", random_shuffle: "random_shuffle(values: list) -> list",
  random_sample: "random_sample(values: list, count: number) -> list", secure_random_bytes: "secure_random_bytes(length: number) -> bytes",
  secure_random_int: "secure_random_int(minimum: number, maximum: number) -> number",
  secure_random_number: "secure_random_number(minimum: number, maximum: number) -> number",
  secure_random_string: "secure_random_string(length: number) -> string",
  append: "append(values: list, value: value) -> list", prepend: "prepend(values: list, value: value) -> list",
  remove: "remove(values: list, value: value) -> list", remove_at: "remove_at(values: list, index: number) -> list",
  size: "size(values: list) -> number", index_of: "index_of(values: list, value: value) -> number | EMPTY",
  last_index_of: "last_index_of(values: list, value: value) -> number | EMPTY", reverse: "reverse(values: list) -> list",
  unique: "unique(values: list) -> list", repeat: "repeat(value: string, count: number) -> string",
  pad_left: "pad_left(value: string, width: number, fill?: string) -> string", pad_right: "pad_right(value: string, width: number, fill?: string) -> string",
  object_remove: "object_remove(object: object, key: string) -> object", object_keys: "object_keys(object: object) -> list<string>",
  object_values: "object_values(object: object) -> list", append_text: "append_text(path: string, text: string) -> VOID",
  read_bytes: "read_bytes(path: string) -> bytes", write_bytes: "write_bytes(path: string, value: bytes) -> VOID",
  file_exists: "file_exists(path: string) -> boolean", directory_exists: "directory_exists(path: string) -> boolean",
  file_size: "file_size(path: string) -> number", copy_file: "copy_file(source: string, destination: string) -> VOID",
  move_file: "move_file(source: string, destination: string) -> VOID", delete_file: "delete_file(path: string) -> VOID",
  read_lines: "read_lines(path: string) -> list<string>", create_directory: "create_directory(path: string) -> VOID",
  delete_directory: "delete_directory(path: string) -> VOID", list_directory: "list_directory(path: string) -> list<string>",
  file_name: "file_name(path: string) -> string", file_extension: "file_extension(path: string) -> string",
  parent_directory: "parent_directory(path: string) -> string", absolute_path: "absolute_path(path: string) -> string",
  bytes_from_string: "bytes_from_string(value: string, encoding?: string) -> bytes",
  string_from_bytes: "string_from_bytes(value: bytes, encoding?: string) -> string",
  bytes_get: "bytes_get(value: bytes, index: number) -> number", slice_bytes: "slice_bytes(value: bytes, start: number, end: number) -> bytes",
  bytes_concat: "bytes_concat(left: bytes, right: bytes) -> bytes", hex_encode: "hex_encode(value: bytes) -> string",
  hex_decode: "hex_decode(value: string) -> bytes", bytes_from_hex: "bytes_from_hex(value: string) -> bytes",
  bytes_to_hexadecimal: "bytes_to_hexadecimal(value: bytes) -> string", hexadecimal_to_bytes: "hexadecimal_to_bytes(value: string) -> bytes",
  base64_encode: "base64_encode(value: bytes) -> string", base64_decode: "base64_decode(value: string) -> bytes",
  bytes_to_base64: "bytes_to_base64(value: bytes) -> string", base64_to_bytes: "base64_to_bytes(value: string) -> bytes",
  regex_match: "regex_match(pattern: string, text: string, ignore_case?: boolean, multiline?: boolean, dot_all?: boolean) -> boolean",
  regex_search: "regex_search(pattern: string, text: string, ignore_case?: boolean, multiline?: boolean, dot_all?: boolean) -> boolean",
  regex_find: "regex_find(pattern: string, text: string, ignore_case?: boolean, multiline?: boolean, dot_all?: boolean) -> regex_match_result | EMPTY",
  regex_find_all: "regex_find_all(pattern: string, text: string, ignore_case?: boolean, multiline?: boolean, dot_all?: boolean) -> list<regex_match_result>",
  regex_replace: "regex_replace(pattern: string, text: string, replacement: string, ignore_case?: boolean, multiline?: boolean, dot_all?: boolean) -> string",
  regex_split: "regex_split(pattern: string, text: string, ignore_case?: boolean, multiline?: boolean, dot_all?: boolean) -> list<string>",
  regex_text: "regex_text(match: regex_match_result) -> string", regex_start: "regex_start(match: regex_match_result) -> number",
  regex_end: "regex_end(match: regex_match_result) -> number", regex_group: "regex_group(match: regex_match_result, index: number) -> string | EMPTY",
  glob: "glob(pattern: string) -> list<string>", env_get: "env_get(name: string, default?: string) -> string | EMPTY",
  env_exists: "env_exists(name: string) -> boolean", env_set: "env_set(name: string, value: string) -> VOID",
  env_remove: "env_remove(name: string) -> VOID", command_args: "command_args() -> list<string>", script_path: "script_path() -> string",
  arg_exists: "arg_exists(name: string, names?: string...) -> boolean", arg_value: "arg_value(name: string, default?: string) -> string | EMPTY",
  command_exists: "command_exists(command: string) -> boolean", shell_exec: "shell_exec(command: string, cwd?: string, timeout?: duration) -> exec_result",
  exec_checked: "exec_checked(command: string, arguments: list<string>, cwd?: string, timeout?: duration) -> exec_result",
  sha256_hash: "sha256_hash(value: secret | string | bytes) -> bytes", sha512_hash: "sha512_hash(value: secret | string | bytes) -> bytes",
  sha3_256_hash: "sha3_256_hash(value: secret | string | bytes) -> bytes", sha3_512_hash: "sha3_512_hash(value: secret | string | bytes) -> bytes",
  sha256_hmac: "sha256_hmac(key: secret | string | bytes, value: secret | string | bytes) -> bytes",
  sha512_hmac: "sha512_hmac(key: secret | string | bytes, value: secret | string | bytes) -> bytes",
  constant_time_equal: "constant_time_equal(left: secret | string | bytes, right: secret | string | bytes) -> boolean",
  derive_key_from_password: "derive_key_from_password(password: secret | string | bytes, salt: bytes) -> secret",
  encrypt_authenticated: "encrypt_authenticated(key: secret | bytes, value: secret | string | bytes) -> bytes",
  decrypt_authenticated: "decrypt_authenticated(key: secret | bytes, value: bytes) -> value",
  encrypt_with_password: "encrypt_with_password(password: secret | string | bytes, value: secret | string | bytes) -> bytes",
  decrypt_with_password: "decrypt_with_password(password: secret | string | bytes, value: bytes) -> value",
  db_close: "db_close(connection: db_connection) -> VOID", db_query_one: "db_query_one(connection: db_connection, sql: string, parameters: list, timeout?: duration) -> object | EMPTY",
  db_scalar: "db_scalar(connection: db_connection, sql: string, parameters: list, timeout?: duration) -> value",
  db_execute: "db_execute(connection: db_connection, sql: string, parameters: list, timeout?: duration) -> number",
  db_begin: "db_begin(connection: db_connection) -> VOID", db_commit: "db_commit(connection: db_connection) -> VOID",
  db_rollback: "db_rollback(connection: db_connection) -> VOID", db_tables: "db_tables(connection: db_connection) -> list<string>",
  db_columns: "db_columns(connection: db_connection, table: string) -> list<object>", db_indexes: "db_indexes(connection: db_connection, table: string) -> list<object>",
  db_primary_key: "db_primary_key(connection: db_connection, table: string) -> object | EMPTY",
  db_server_info: "db_server_info(connection: db_connection) -> object | EMPTY", db_version: "db_version(connection: db_connection) -> string",
  yaml_to_object: "yaml_to_object(text: string) -> value | EMPTY", yaml_to_objects: "yaml_to_objects(text: string) -> list",
  yaml_file_to_object: "yaml_file_to_object(path: string) -> value | EMPTY", yaml_file_to_objects: "yaml_file_to_objects(path: string) -> list",
  object_to_yaml: "object_to_yaml(value: value, indent?: number, sort_keys?: boolean) -> string",
  objects_to_yaml: "objects_to_yaml(values: list, indent?: number, sort_keys?: boolean) -> string",
  object_to_yaml_file: "object_to_yaml_file(path: string, value: value, indent?: number, sort_keys?: boolean) -> VOID",
  objects_to_yaml_file: "objects_to_yaml_file(path: string, values: list, indent?: number, sort_keys?: boolean) -> VOID",
  yaml_validate_file: "yaml_validate_file(path: string) -> boolean",
  xml_to_object: "xml_to_object(text: string) -> object", xml_file_to_object: "xml_file_to_object(path: string) -> object",
  object_to_xml: "object_to_xml(value: object, indent?: number, declaration?: boolean) -> string",
  object_to_xml_file: "object_to_xml_file(path: string, value: object, indent?: number, declaration?: boolean) -> VOID",
  xml_document_write: "xml_document_write(path: string, document: xml_document, indent?: number, declaration?: boolean) -> VOID",
  xml_create_element: "xml_create_element(name: string, namespace_uri?: string) -> xml_element",
  xml_set_element_text: "xml_set_element_text(element: xml_element, text: string) -> VOID",
  xml_children: "xml_children(element: xml_element) -> list<xml_element>", xml_child: "xml_child(element: xml_element, name: string) -> xml_element | EMPTY",
  xml_add_child: "xml_add_child(parent: xml_element, child: xml_element) -> VOID", xml_remove_child: "xml_remove_child(parent: xml_element, child: xml_element) -> VOID",
  xml_namespace_uri: "xml_namespace_uri(element: xml_element) -> string | EMPTY", xml_namespace_prefix: "xml_namespace_prefix(element: xml_element) -> string | EMPTY",
  xml_escape_text: "xml_escape_text(value: string) -> string", xml_escape_attribute: "xml_escape_attribute(value: string) -> string",
  xml_unescape: "xml_unescape(value: string) -> string",
  mail_address: "mail_address(address: string, display_name?: string) -> mail_address", mail_create_message: "mail_create_message() -> mail_message",
  mail_set_sender: "mail_set_sender(message: mail_message, address: string | mail_address) -> VOID",
  mail_add_recipient: "mail_add_recipient(message: mail_message, address: string | mail_address) -> VOID",
  mail_add_cc_recipient: "mail_add_cc_recipient(message: mail_message, address: string | mail_address) -> VOID",
  mail_add_bcc_recipient: "mail_add_bcc_recipient(message: mail_message, address: string | mail_address) -> VOID",
  mail_set_subject: "mail_set_subject(message: mail_message, subject: string) -> VOID",
  mail_set_text_body: "mail_set_text_body(message: mail_message, body: string) -> VOID", mail_set_html_body: "mail_set_html_body(message: mail_message, body: string) -> VOID",
  mail_add_attachment: "mail_add_attachment(message: mail_message, path: string, content_type?: string) -> VOID",
  mail_add_attachment_bytes: "mail_add_attachment_bytes(message: mail_message, filename: string, content: bytes, content_type: string) -> VOID",
  mail_add_inline_attachment: "mail_add_inline_attachment(message: mail_message, path: string, content_id: string, content_type?: string) -> VOID",
  mail_add_inline_attachment_bytes: "mail_add_inline_attachment_bytes(message: mail_message, filename: string, content: bytes, content_type: string, content_id: string) -> VOID",
  mail_send_message: "mail_send_message(sender: mail_sender, message: mail_message) -> mail_send_result",
  cookie_jar: "cookie_jar() -> cookie_jar", cookie_get: "cookie_get(jar: cookie_jar, name: string) -> secret | EMPTY",
  cookie_set: "cookie_set(jar: cookie_jar, name: string, value: secret | string | bytes, domain?: string, path?: string, secure?: boolean, http_only?: boolean, same_site?: string) -> VOID",
  cookie_remove: "cookie_remove(jar: cookie_jar, name: string) -> VOID", cookie_clear: "cookie_clear(jar: cookie_jar) -> VOID",
  cookie_all: "cookie_all(jar: cookie_jar) -> object", cookie_save_secure: "cookie_save_secure(path: string, jar: cookie_jar, key?: secret | bytes, password?: secret | string | bytes) -> VOID",
  cookie_load_secure: "cookie_load_secure(path: string, key?: secret | bytes, password?: secret | string | bytes) -> cookie_jar",
  datetime_from_unix_milliseconds: "datetime_from_unix_milliseconds(value: number, timezone: timezone) -> datetime",
  datetime_from_unix_seconds: "datetime_from_unix_seconds(value: number, timezone: timezone) -> datetime",
  datetime_offset: "datetime_offset(value: datetime) -> duration", datetime_timezone: "datetime_timezone(value: datetime) -> timezone",
  hmac_sha256: "hmac_sha256(key: secret | string | bytes, message: secret | string | bytes) -> bytes",
  jwt_sign: "jwt_sign(claims: object, key: secret | string | bytes, algorithm?: string) -> string",
  jwt_verify: "jwt_verify(token: string, key: secret | string | bytes, algorithm?: string) -> object",
  password_hash: "password_hash(password: secret | string | bytes) -> string", password_verify: "password_verify(password: secret | string | bytes, hash: string) -> boolean",
  secret_get: "secret_get(name: string) -> secret", http_profile: "http_profile(name: string, language?: string, user_agent?: string, accept?: string, accept_encoding?: string) -> http_profile",
  http_profile_headers: "http_profile_headers(profile: http_profile) -> object", http_request: "http_request(url: string, method?: string, headers?: object, body?: string | bytes, timeout?: duration) -> http_response",
  request_method: "request_method() -> string", request_path: "request_path() -> string", request_header: "request_header(name: string) -> string | EMPTY",
  request_param: "request_param(name: string) -> string | EMPTY", request_query: "request_query(name: string) -> string | EMPTY",
  request_body: "request_body(encoding?: string) -> string", request_cookie: "request_cookie(name: string) -> secret | EMPTY",
  return_http: "return_http(status?: number, content_type?: string, headers?: object, body?: string | bytes) -> VOID",
  redirect_http: "redirect_http(location: string, status?: number) -> VOID",
  http_set_cookie: "http_set_cookie(name: string, value: secret | string, path?: string, secure?: boolean, http_only?: boolean, same_site?: string) -> VOID",
  http_host: "http_host(host?: string, port?: number) -> VOID", http_static: "http_static(url?: string, directory?: string) -> VOID",
  sort_descending: "sort_descending(items: list) -> list", sort_ignore_case: "sort_ignore_case(items: list<string>) -> list<string>",
  sort_ignore_case_descending: "sort_ignore_case_descending(items: list<string>) -> list<string>", sort_natural: "sort_natural(items: list<string>) -> list<string>",
  sort_natural_descending: "sort_natural_descending(items: list<string>) -> list<string>", sort_natural_ignore_case: "sort_natural_ignore_case(items: list<string>) -> list<string>",
  sort_natural_ignore_case_descending: "sort_natural_ignore_case_descending(items: list<string>) -> list<string>",
  sort_by_descending: "sort_by_descending(items: list<object>, field: string) -> list<object>",
  xml_remove_attribute: "xml_remove_attribute(element: xml_element, name: string, namespace_uri?: string) -> VOID",
  network_operation_unavailable: "network_operation_unavailable(message: string) -> error",
  mail_create_sender: "mail_create_sender(provider?: string, host?: string, port?: number, security?: string, username?: string, password?: secret, region?: string, timeout?: duration) -> mail_sender",
};
const builtinReturnTypeOverrides = {
  type_of: "string", length: "number", string: "string", number: "number", boolean: "boolean", format: "string",
  trim: "string", upper: "string", lower: "string", substring: "string", join: "string", replace: "string",
  split: "list<string>", list_append: "list", first: "value", last: "value", slice: "list", map: "list", filter: "list",
  object_get: "value", object_set: "object", object_has: "boolean", json_encode: "string", json_decode: "value",
  read_text: "string", bytes_from_string: "bytes", string_from_bytes: "string", regex_find: "regex_match_result",
  regex_find_all: "list<regex_match_result>", db_connect: "db_connection", db_query: "list<object>", exec: "exec_result",
  http_get: "http_response", duration: "duration", datetime_parse: "datetime", random_int: "number",
  len: "number", is_empty: "boolean", type: "string", is_number: "boolean", is_string: "boolean",
  is_boolean: "boolean", is_list: "boolean", is_object: "boolean", is_bytes: "boolean", is_datetime: "boolean",
  is_duration: "boolean", is_secret: "boolean", abs: "number", ceil: "number", floor: "number", round: "number",
  sqrt: "number", sin: "number", cos: "number", tan: "number", log: "number", log10: "number", log2: "number",
  exp: "number", pow: "number", min: "number", max: "number", range: "list<number>", number_range: "list<number>",
  input: "string", contains: "boolean", starts_with: "boolean", ends_with: "boolean", compare: "number",
  compare_ignore_case: "number", substring_after: "string", substring_before: "string", count_occurrences: "number",
  local_datetime: "local_datetime", timezone: "timezone", datetime_now: "datetime", datetime_format: "string",
  datetime_valid: "boolean", datetime_from_local: "datetime", datetime_in_timezone: "datetime", unix_time: "number",
  datetime_from_unix: "datetime", unix_milliseconds_from_datetime: "number", unix_seconds_from_datetime: "number",
  datetime_year: "number", datetime_month: "number", datetime_day: "number", datetime_hour: "number",
  datetime_minute: "number", datetime_second: "number", datetime_millisecond: "number", datetime_weekday: "number",
  duration_milliseconds: "number", random_seed: "VOID", random_number: "number", random_float: "number",
  random_bool: "boolean", random_pick: "value", random_shuffle: "list", random_sample: "list",
  secure_random_bytes: "bytes", secure_random_int: "number", secure_random_number: "number", secure_random_string: "string",
  append: "list", prepend: "list", remove: "list", remove_at: "list", size: "number", index_of: "number | EMPTY",
  last_index_of: "number | EMPTY", reverse: "list", unique: "list", repeat: "string", pad_left: "string", pad_right: "string",
  object_remove: "object", object_keys: "list<string>", object_values: "list", append_text: "VOID", read_bytes: "bytes",
  write_bytes: "VOID", file_exists: "boolean", directory_exists: "boolean", file_size: "number", copy_file: "VOID",
  move_file: "VOID", delete_file: "VOID", read_lines: "list<string>", create_directory: "VOID", delete_directory: "VOID",
  list_directory: "list<string>", file_name: "string", file_extension: "string", parent_directory: "string", absolute_path: "string",
  bytes_get: "number", slice_bytes: "bytes", bytes_concat: "bytes", hex_encode: "string", hex_decode: "bytes",
  bytes_from_hex: "bytes", bytes_to_hexadecimal: "string", hexadecimal_to_bytes: "bytes", base64_encode: "string",
  base64_decode: "bytes", bytes_to_base64: "string", base64_to_bytes: "bytes", regex_match: "boolean",
  regex_search: "boolean", regex_find: "regex_match_result | EMPTY", regex_find_all: "list<regex_match_result>",
  regex_replace: "string", regex_split: "list<string>", regex_text: "string", regex_start: "number", regex_end: "number",
  regex_group: "string | EMPTY", glob: "list<string>", env_get: "string | EMPTY", env_exists: "boolean", env_set: "VOID",
  env_remove: "VOID", command_args: "list<string>", script_path: "string", arg_exists: "boolean", arg_value: "string | EMPTY",
  command_exists: "boolean", shell_exec: "exec_result", exec_checked: "exec_result", sha256_hash: "bytes", sha512_hash: "bytes",
  sha3_256_hash: "bytes", sha3_512_hash: "bytes", sha256_hmac: "bytes", sha512_hmac: "bytes",
  constant_time_equal: "boolean", derive_key_from_password: "secret", encrypt_authenticated: "bytes",
  decrypt_authenticated: "value", encrypt_with_password: "bytes", decrypt_with_password: "value",
  db_close: "VOID", db_query_one: "object | EMPTY", db_scalar: "value", db_execute: "number", db_begin: "VOID",
  db_commit: "VOID", db_rollback: "VOID", db_tables: "list<string>", db_columns: "list<object>", db_indexes: "list<object>",
  db_primary_key: "object | EMPTY", db_server_info: "object | EMPTY", db_version: "string",
  yaml_to_object: "value | EMPTY", yaml_to_objects: "list", yaml_file_to_object: "value | EMPTY", yaml_file_to_objects: "list",
  object_to_yaml: "string", objects_to_yaml: "string", object_to_yaml_file: "VOID", objects_to_yaml_file: "VOID", yaml_validate_file: "boolean",
  xml_to_object: "object", xml_file_to_object: "object", object_to_xml: "string", object_to_xml_file: "VOID", xml_document_write: "VOID",
  xml_create_element: "xml_element", xml_set_element_text: "VOID", xml_children: "list<xml_element>", xml_child: "xml_element | EMPTY",
  xml_add_child: "VOID", xml_remove_child: "VOID", xml_namespace_uri: "string | EMPTY", xml_namespace_prefix: "string | EMPTY",
  xml_escape_text: "string", xml_escape_attribute: "string", xml_unescape: "string", mail_address: "mail_address",
  mail_create_message: "mail_message", mail_set_sender: "VOID", mail_add_recipient: "VOID", mail_add_cc_recipient: "VOID",
  mail_add_bcc_recipient: "VOID", mail_set_subject: "VOID", mail_set_text_body: "VOID", mail_set_html_body: "VOID",
  mail_add_attachment: "VOID", mail_add_attachment_bytes: "VOID", mail_add_inline_attachment: "VOID",
  mail_add_inline_attachment_bytes: "VOID", mail_send_message: "mail_send_result",
  cookie_jar: "cookie_jar", cookie_get: "secret | EMPTY", cookie_set: "VOID", cookie_remove: "VOID", cookie_clear: "VOID",
  cookie_all: "object", cookie_save_secure: "VOID", cookie_load_secure: "cookie_jar", datetime_from_unix_milliseconds: "datetime",
  datetime_from_unix_seconds: "datetime", datetime_offset: "duration", datetime_timezone: "timezone", hmac_sha256: "bytes",
  jwt_sign: "string", jwt_verify: "object", password_hash: "string", password_verify: "boolean", secret_get: "secret",
  http_profile: "http_profile", http_profile_headers: "object", http_request: "http_response", request_method: "string",
  request_path: "string", request_header: "string | EMPTY", request_param: "string | EMPTY", request_query: "string | EMPTY",
  request_body: "string", request_cookie: "secret | EMPTY", return_http: "VOID", redirect_http: "VOID", http_set_cookie: "VOID",
  http_host: "VOID", http_static: "VOID", sort_descending: "list", sort_ignore_case: "list<string>",
  sort_ignore_case_descending: "list<string>", sort_natural: "list<string>", sort_natural_descending: "list<string>",
  sort_natural_ignore_case: "list<string>", sort_natural_ignore_case_descending: "list<string>", sort_by_descending: "list<object>",
  xml_remove_attribute: "VOID", network_operation_unavailable: "error",
  mail_create_sender: "mail_sender",
};
const builtinNamedArguments = Object.fromEntries(Object.entries({
  datetime: "timezone", regex_match: "dot_all ignore_case multiline", regex_search: "dot_all ignore_case multiline",
  regex_find: "dot_all ignore_case multiline", regex_find_all: "dot_all ignore_case multiline",
  regex_replace: "dot_all ignore_case multiline", regex_split: "dot_all ignore_case multiline",
  env_get: "default", arg_value: "default",
  exec: "cwd encoding env inherit_env input max_stderr_bytes max_stdout_bytes timeout",
  exec_checked: "cwd encoding env inherit_env input max_stderr_bytes max_stdout_bytes timeout",
  shell_exec: "cwd encoding env inherit_env input max_stderr_bytes max_stdout_bytes timeout",
  http_profile: "accept accept_encoding language user_agent",
  http_request: "auth body cookie_jar cookies encoding headers max_bytes max_redirects method profile redirect timeout",
  http_get: "auth cookie_jar cookies encoding headers max_bytes max_redirects profile redirect timeout",
  bytes_from_string: "encoding", string_from_bytes: "encoding", api_key_auth: "location",
  jwt_sign: "algorithm", jwt_verify: "algorithm", oauth_client_credentials: "scope", mail_address: "display_name",
  mail_add_attachment: "content_type", mail_add_inline_attachment: "content_type",
  mail_create_sender: "host password port provider region security timeout username",
  object_to_yaml: "indent sort_keys", object_to_yaml_file: "indent sort_keys",
  objects_to_yaml: "indent sort_keys", objects_to_yaml_file: "indent sort_keys",
  object_to_xml: "declaration indent", object_to_xml_file: "declaration indent",
  xml_document_to_text: "declaration indent", xml_document_write: "declaration indent",
  xml_create_element: "namespace_uri", xml_get_attribute: "namespace_uri", xml_set_attribute: "namespace_uri",
  xml_remove_attribute: "namespace_uri", cookie_set: "domain http_only path same_site secure",
  cookie_save_secure: "key password", cookie_load_secure: "key password", request_body: "encoding",
  return_http: "body content_type headers status", redirect_http: "status",
  http_set_cookie: "http_only path same_site secure", http_host: "host port", http_static: "directory url",
  db_connect: "charset database driver host mode password port ssl timeout user",
  db_query: "timeout", db_query_one: "timeout", db_scalar: "timeout", db_execute: "timeout",
  i2c_open: "scl sda", spi_open: "chip_select clock miso mosi", uart_open: "rx tx",
  tcp_connect: "timeout", tcp_receive: "timeout", udp_open: "local_address local_port timeout", udp_receive: "timeout",
  wifi_start_access_point: "channel password ssid",
  dhcp_server_start: "dns_servers gateway lease_time pool_end pool_start prefix reservations server_address",
  dns_server_start: "catch_all records server_address",
}).map(([name, names]) => [name, new Set(names.split(" "))]));
for (const name of Object.keys(builtinMetadata)) if (name.endsWith("_error")) {
  builtinSignatureOverrides[name] = `${name}(message: string) -> error`;
  builtinReturnTypeOverrides[name] = "error";
}
const builtinSignatures = Object.fromEntries(Object.entries(builtinMetadata).map(([name, value]) => [name, builtinSignatureOverrides[name] || value.signature]));
const builtinReturnTypes = Object.fromEntries(Object.entries(builtinMetadata).map(([name, value]) => [name, builtinReturnTypeOverrides[name] || value.returnType]));

function runtimeConfiguration(resource) {
  const config = vscode.workspace.getConfiguration("separan", resource);
  return {
    executable: config.get("executablePath", "separan"),
    arguments: config.get("runtimeArguments", []),
    environment: config.get("environment", {}),
  };
}

async function executeSeparanTask(name, resource, arguments_) {
  const config = runtimeConfiguration(resource);
  const folder = resource ? vscode.workspace.getWorkspaceFolder(resource) : undefined;
  const scope = folder || vscode.TaskScope.Workspace;
  const execution = new vscode.ProcessExecution(config.executable, [...config.arguments, ...arguments_], {
    cwd: folder ? folder.uri.fsPath : undefined,
    env: { ...process.env, ...config.environment },
  });
  const task = new vscode.Task({ type: "separan", task: name }, scope, name, "Separan", execution);
  task.presentationOptions = { reveal: vscode.TaskRevealKind.Always, panel: vscode.TaskPanelKind.Dedicated, clear: true };
  return vscode.tasks.executeTask(task);
}

function currentEditor() {
  const editor = vscode.window.activeTextEditor;
  return editor && editor.document.languageId === "separan" ? editor : undefined;
}

function codeText(text) {
  let quoted = false; let escaped = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
    } else if (char === '"') quoted = true;
    else if (char === "#") return text.slice(0, index).trimEnd();
  }
  return text;
}

function multilineCommentDelimiter(text) {
  const candidate = text.trim();
  if (candidate === "##") return "";
  const found = /^##([\p{L}_][\p{L}\p{M}\p{N}_]*)$/u.exec(candidate);
  return found ? found[1] : undefined;
}

function labelAt(editor) {
  const line = codeText(editor.document.lineAt(editor.selection.active.line).text);
  const cursor = editor.selection.active.character;
  const matcher = /:([^\s:()]+)/gu;
  for (const found of line.matchAll(matcher)) {
    const start = found.index + 1;
    if (start <= cursor && cursor <= start + found[1].length) return found[1];
  }
  return undefined;
}

function labelAtPosition(document, position) {
  const line = codeText(document.lineAt(position.line).text); const matcher = /:([^\s:()]+)/gu;
  for (const found of line.matchAll(matcher)) {
    const start = found.index + 1; const end = start + found[1].length;
    if (start <= position.character && position.character <= end) return { name: found[1], range: new vscode.Range(position.line, start, position.line, end) };
  }
  return undefined;
}

function functionBoundaryAtPosition(document, position) {
  const text = codeText(document.lineAt(position.line).text);
  const found = /^\s*(?:SEP|END_SEP):([\p{L}_][\p{L}\p{M}\p{N}_]*)/u.exec(text);
  if (!found) return undefined;
  const start = text.indexOf(found[1], found.index); const end = start + found[1].length;
  return start <= position.character && position.character <= end
    ? { name: found[1], range: new vscode.Range(position.line, start, position.line, end) }
    : undefined;
}

function identifierAtPosition(document, position) {
  const range = document.getWordRangeAtPosition(position, /[\p{L}_][\p{L}\p{M}\p{N}_]*/u);
  return range ? { name: document.getText(range), range } : undefined;
}

function tagAtPosition(document, position) {
  const text = codeText(document.lineAt(position.line).text); const matcher = /@([\p{L}_][\p{L}\p{M}\p{N}_]*)/gu;
  for (const found of text.matchAll(matcher)) {
    const start = found.index + 1; const end = start + found[1].length;
    if (start <= position.character && position.character <= end) return { name: found[1], range: new vscode.Range(position.line, start, position.line, end) };
  }
  return undefined;
}

function tagLocations(document, name) {
  const locations = []; const escaped = name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"); const pattern = new RegExp(`@${escaped}\\b`, "gu");
  for (let line = 0; line < document.lineCount; line += 1) for (const match of codeText(document.lineAt(line).text).matchAll(pattern))
    locations.push(new vscode.Location(document.uri, new vscode.Range(line, match.index + 1, line, match.index + 1 + name.length)));
  return locations;
}

function allLabelLocations(document, name) {
  const locations = []; const pattern = new RegExp(`:${name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&")}(?=\\s|\\(|$)`, "gu");
  for (let line = 0; line < document.lineCount; line += 1) {
    const text = codeText(document.lineAt(line).text);
    for (const match of text.matchAll(pattern)) locations.push(new vscode.Location(document.uri, new vscode.Range(line, match.index + 1, line, match.index + 1 + name.length)));
  }
  return locations;
}

async function workspaceLabelLocations(document, name) {
  const documents = await workspaceSeparanDocuments();
  const unique = new Map([[document.uri.toString(), document], ...documents.map((candidate) => [candidate.uri.toString(), candidate])]);
  return [...unique.values()].flatMap((candidate) => allLabelLocations(candidate, name));
}

function functionDefinitions(document) {
  const definitions = new Map();
  for (const item of flattenStructures(documentStructure(document.getText()).roots)) {
    if (item.kind === "SEP") definitions.set(item.label, new vscode.Location(document.uri,
      new vscode.Position(item.start_line - 1, item.start_column - 1)));
  }
  return definitions;
}

function functionLocations(document, name) {
  const locations = []; const definition = flattenStructures(documentStructure(document.getText()).roots).find((item) => item.kind === "SEP" && item.label === name);
  if (!definition) return locations;
  for (const line of [definition.start_line - 1, definition.end_line - 1]) {
    const text = codeText(document.lineAt(line).text); const at = text.indexOf(`:${name}`);
    if (at >= 0) locations.push(new vscode.Location(document.uri, new vscode.Range(line, at + 1, line, at + 1 + name.length)));
  }
  const pattern = new RegExp(`\\b${name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&")}\\s*(?=\\()`, "gu");
  for (let line = 0; line < document.lineCount; line += 1) for (const match of codeText(document.lineAt(line).text).matchAll(pattern))
    locations.push(new vscode.Location(document.uri, new vscode.Range(line, match.index, line, match.index + name.length)));
  const unique = new Map();
  for (const location of locations) unique.set(`${location.range.start.line}:${location.range.start.character}`, location);
  return [...unique.values()];
}

async function workspaceSeparanDocuments() {
  const files = await vscode.workspace.findFiles("**/*.sep", "**/{.git,node_modules,build,dist}/**", 2000);
  const documents = await Promise.all(files.map((uri) => vscode.workspace.openTextDocument(uri)));
  const unique = new Map(documents.map((document) => [document.uri.toString(), document]));
  for (const document of vscode.workspace.textDocuments)
    if (document.languageId === "separan" && document.uri.scheme === "file") unique.set(document.uri.toString(), document);
  return [...unique.values()];
}

function importAliases(document) {
  const aliases = new Map(); const pattern = /^\s*import\s+"([^"]+)"\s+as\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*$/u;
  for (let line = 0; line < document.lineCount; line += 1) { const found = pattern.exec(codeText(document.lineAt(line).text)); if (found) aliases.set(found[2], found[1]); }
  return aliases;
}

function importDeclarations(document) {
  const declarations = []; const pattern = /^\s*import\s+"([^"]+)"\s+as\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*$/u;
  for (let line = 0; line < document.lineCount; line += 1) {
    const text = codeText(document.lineAt(line).text); const found = pattern.exec(text);
    if (found) declarations.push({ path: found[1], alias: found[2], line,
      pathRange: new vscode.Range(line, found.index + text.indexOf(found[1]), line, found.index + text.indexOf(found[1]) + found[1].length),
      aliasRange: new vscode.Range(line, text.lastIndexOf(found[2]), line, text.lastIndexOf(found[2]) + found[2].length) });
  }
  return declarations;
}

function importAtPosition(document, position) {
  return importDeclarations(document).find((item) => item.pathRange.contains(position));
}

function moduleUri(document, relative) {
  if (!relative || document.uri.scheme !== "file") return undefined;
  const candidate = path.resolve(path.dirname(document.uri.fsPath), relative.endsWith(".sep") ? relative : relative + ".sep");
  return vscode.Uri.file(candidate);
}

function importedUri(document, alias) {
  return moduleUri(document, importAliases(document).get(alias));
}

function qualifiedFunctionLocations(document, alias, name) {
  const locations = []; const escapedAlias = alias.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
  const escapedName = name.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
  const pattern = new RegExp("\\b" + escapedAlias + "\\.(" + escapedName + ")\\s*(?=\\()", "gu");
  for (let line = 0; line < document.lineCount; line += 1) for (const match of codeText(document.lineAt(line).text).matchAll(pattern)) {
    const start = match.index + alias.length + 1;
    locations.push(new vscode.Location(document.uri, new vscode.Range(line, start, line, start + name.length)));
  }
  return locations;
}

async function importedFunctionLocations(targetDocument, name, sourceDocument) {
  const workspaceDocuments = await workspaceSeparanDocuments();
  const documents = new Map([[targetDocument.uri.toString(), targetDocument], [sourceDocument.uri.toString(), sourceDocument],
    ...workspaceDocuments.map((candidate) => [candidate.uri.toString(), candidate])]);
  const locations = functionLocations(targetDocument, name);
  for (const candidate of documents.values()) for (const alias of importAliases(candidate).keys()) {
    const uri = importedUri(candidate, alias);
    if (uri && uri.fsPath.toLocaleLowerCase() === targetDocument.uri.fsPath.toLocaleLowerCase())
      locations.push(...qualifiedFunctionLocations(candidate, alias, name));
  }
  return locations;
}

async function importedDocument(document, alias) {
  const relative = importAliases(document).get(alias); if (!relative || document.uri.scheme !== "file") return undefined;
  const candidate = path.resolve(path.dirname(document.uri.fsPath), relative.endsWith(".sep") ? relative : `${relative}.sep`);
  try { return await vscode.workspace.openTextDocument(vscode.Uri.file(candidate)); } catch (_) { return undefined; }
}

async function importReaches(document, targetUri, visited = new Set()) {
  const key = document.uri.toString().toLocaleLowerCase();
  if (key === targetUri.toString().toLocaleLowerCase()) return true;
  if (visited.has(key)) return false;
  visited.add(key);
  for (const declaration of importDeclarations(document)) {
    const uri = moduleUri(document, declaration.path); if (!uri) continue;
    if (uri.toString().toLocaleLowerCase() === targetUri.toString().toLocaleLowerCase()) return true;
    try {
      const imported = await vscode.workspace.openTextDocument(uri);
      if (await importReaches(imported, targetUri, visited)) return true;
    } catch (_) { /* Missing imports are diagnosed separately. */ }
  }
  return false;
}

async function importRenameEdit(files) {
  const renamed = new Map(files.filter((file) => file.oldUri.scheme === "file" && file.newUri.scheme === "file")
    .map((file) => [file.oldUri.fsPath.toLocaleLowerCase(), file.newUri.fsPath]));
  const edit = new vscode.WorkspaceEdit(); if (!renamed.size) return edit;
  for (const document of await workspaceSeparanDocuments()) {
    const futureDocumentPath = renamed.get(document.uri.fsPath.toLocaleLowerCase()) || document.uri.fsPath;
    for (const declaration of importDeclarations(document)) {
      const target = moduleUri(document, declaration.path); const renamedTarget = target && renamed.get(target.fsPath.toLocaleLowerCase());
      if (!renamedTarget) continue;
      let relative = path.relative(path.dirname(futureDocumentPath), renamedTarget).replace(/\\/gu, "/");
      if (relative.endsWith(".sep")) relative = relative.slice(0, -4);
      if (!relative.startsWith(".")) relative = "./" + relative;
      edit.replace(document.uri, declaration.pathRange, relative);
    }
  }
  return edit;
}

function qualifiedIdentifierAt(document, position) {
  const text = codeText(document.lineAt(position.line).text); const pattern = /([\p{L}_][\p{L}\p{M}\p{N}_]*)\.([\p{L}_][\p{L}\p{M}\p{N}_]*)/gu;
  for (const found of text.matchAll(pattern)) {
    const memberStart = found.index + found[1].length + 1; const memberEnd = memberStart + found[2].length;
    if (memberStart <= position.character && position.character <= memberEnd) return { alias: found[1], name: found[2] };
  }
  return undefined;
}

class SeparanCompletionProvider {
  async provideCompletionItems(document, position) {
    const prefix = document.lineAt(position.line).text.slice(0, position.character);
    const importPath = /^\s*import\s+"([^"]*)$/u.exec(prefix);
    if (importPath && document.uri.scheme === "file") {
      const fragment = importPath[1]; const slash = Math.max(fragment.lastIndexOf("/"), fragment.lastIndexOf("\\"));
      const directoryPart = slash >= 0 ? fragment.slice(0, slash + 1) : "";
      const namePart = fragment.slice(slash + 1); const directory = path.resolve(path.dirname(document.uri.fsPath), directoryPart || ".");
      try {
        const entries = await fs.promises.readdir(directory, { withFileTypes: true }); const start = position.character - fragment.length;
        return entries.filter((entry) => (entry.isDirectory() || entry.name.endsWith(".sep")) && entry.name.startsWith(namePart)).map((entry) => {
          const name = entry.isDirectory() ? entry.name + "/" : entry.name.slice(0, -4);
          const completion = new vscode.CompletionItem(directoryPart.replace(/\\/gu, "/") + name,
            entry.isDirectory() ? vscode.CompletionItemKind.Folder : vscode.CompletionItemKind.Module);
          completion.range = new vscode.Range(position.line, start, position.line, position.character);
          completion.insertText = directoryPart.replace(/\\/gu, "/") + name; return completion;
        });
      } catch (_) { return []; }
    }
    const imported = /([\p{L}_][\p{L}\p{M}\p{N}_]*)\.$/u.exec(prefix);
    if (imported) {
      const target = await importedDocument(document, imported[1]); if (!target) return [];
      return [...functionDefinitions(target).keys()].map((name) => new vscode.CompletionItem(name, vscode.CompletionItemKind.Function));
    }
    if (/^\s*:end\w*$/u.test(prefix)) {
      const open = flattenStructures(documentStructure(document.getText(new vscode.Range(new vscode.Position(0, 0), position))).roots)
        .filter((item) => item.start_line <= position.line + 1 && item.end_line >= position.line + 1)
        .sort((a, b) => b.start_line - a.start_line);
      return open.map((item, index) => {
        const closer = `${blockPairs[item.kind]}:${item.label}`;
        const completion = new vscode.CompletionItem(closer, vscode.CompletionItemKind.Keyword);
        completion.detail = `Closes ${item.kind}:${item.label} from line ${item.start_line}`;
        completion.sortText = String(index).padStart(4, "0"); completion.insertText = closer; return completion;
      });
    }
    const functions = [...functionDefinitions(document).keys()].map((name) => {
      const completion = new vscode.CompletionItem(name, vscode.CompletionItemKind.Function);
      completion.detail = `Separan function SEP:${name}`; completion.insertText = new vscode.SnippetString(`${name}($0)`); return completion;
    });
    const builtins = Object.entries(builtinSignatures).map(([name, signature]) => {
      const completion = new vscode.CompletionItem(name, vscode.CompletionItemKind.Function);
      completion.detail = signature; completion.insertText = new vscode.SnippetString(`${name}($0)`); return completion;
    });
    return [...functions, ...builtins];
  }
}

function activeCall(document, position) {
  const text = document.lineAt(position.line).text.slice(0, position.character); let depth = 0;
  for (let index = text.length - 1; index >= 0; index -= 1) {
    if (text[index] === ")") depth += 1;
    else if (text[index] === "(") {
      if (depth) { depth -= 1; continue; }
      const before = text.slice(0, index); const found = /((?:[\p{L}_][\p{L}\p{M}\p{N}_]*\.)?[\p{L}_][\p{L}\p{M}\p{N}_]*)\s*$/u.exec(before);
      if (!found) return undefined;
      const argumentsText = text.slice(index + 1); let commas = 0; let nested = 0; let quotedText = false; let escaped = false;
      for (const char of argumentsText) {
        if (quotedText) { if (escaped) escaped = false; else if (char === "\\") escaped = true; else if (char === '"') quotedText = false; }
        else if (char === '"') quotedText = true; else if (char === "(") nested += 1; else if (char === ")") nested -= 1; else if (char === "," && nested === 0) commas += 1;
      }
      return { name: found[1], activeParameter: commas };
    }
  }
  return undefined;
}

class SeparanSignatureHelpProvider {
  async provideSignatureHelp(document, position) {
    const call = activeCall(document, position); if (!call) return undefined;
    const qualified = /^([^.]+)\.(.+)$/u.exec(call.name); let local;
    if (qualified) {
      const target = await importedDocument(document, qualified[1]);
      local = target && flattenStructures(documentStructure(target.getText()).roots).find((item) => item.kind === "SEP" && item.label === qualified[2]);
    } else local = flattenStructures(documentStructure(document.getText()).roots).find((item) => item.kind === "SEP" && item.label === call.name);
    const label = local ? `${call.name}(${local.parameters.join(", ")})` : builtinSignatures[call.name];
    if (!label) return undefined;
    const signature = new vscode.SignatureInformation(label);
    const parameterText = label.slice(label.indexOf("(") + 1, label.lastIndexOf(")"));
    signature.parameters = parameterText ? parameterText.split(",").map((value) => new vscode.ParameterInformation(value.trim())) : [];
    const help = new vscode.SignatureHelp(); help.signatures = [signature]; help.activeSignature = 0;
    help.activeParameter = Math.min(call.activeParameter, Math.max(0, signature.parameters.length - 1)); return help;
  }
}

class SeparanWorkspaceSymbolProvider {
  async provideWorkspaceSymbols(query) {
    const symbols = []; const files = await vscode.workspace.findFiles("**/*.sep", "**/{.git,node_modules,build,dist}/**", 2000);
    for (const uri of files) {
      const document = await vscode.workspace.openTextDocument(uri);
      for (const item of flattenStructures(documentStructure(document.getText()).roots)) {
        if (query && !item.label.toLocaleLowerCase().includes(query.toLocaleLowerCase())) continue;
        const kind = item.kind === "SEP" ? vscode.SymbolKind.Function : item.kind === "object" ? vscode.SymbolKind.Object : vscode.SymbolKind.Namespace;
        symbols.push(new vscode.SymbolInformation(`${item.kind}:${item.label}`, kind, item.path,
          new vscode.Location(uri, new vscode.Position(item.start_line - 1, item.start_column - 1))));
      }
    }
    return symbols;
  }
}

function splitTopLevelValues(source) {
  const values = []; let start = 0; let depth = 0; let quoted = false; let escaped = false;
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (quoted) { if (escaped) escaped = false; else if (character === "\\") escaped = true; else if (character === '"') quoted = false; }
    else if (character === '"') quoted = true;
    else if ("([{".includes(character)) depth += 1;
    else if (")]}".includes(character)) depth -= 1;
    else if (character === "," && depth === 0) { values.push(source.slice(start, index).trim()); start = index + 1; }
  }
  values.push(source.slice(start).trim()); return values.filter(Boolean);
}

function callsOnLine(source) {
  const identifier = "[\\p{L}_][\\p{L}\\p{M}\\p{N}_]*";
  const calls = []; const pattern = new RegExp("(" + identifier + "(?:\\." + identifier + ")?)\\s*\\(", "gu");
  for (const match of source.matchAll(pattern)) {
    const open = source.indexOf("(", match.index); let depth = 1; let quoted = false; let escaped = false; let close = -1;
    for (let index = open + 1; index < source.length; index += 1) {
      const character = source[index];
      if (quoted) { if (escaped) escaped = false; else if (character === "\\") escaped = true; else if (character === '"') quoted = false; }
      else if (character === '"') quoted = true;
      else if (character === "(") depth += 1;
      else if (character === ")" && --depth === 0) { close = index; break; }
    }
    if (close >= 0) calls.push({ name: match[1], start: match.index, arguments: splitTopLevelValues(source.slice(open + 1, close)) });
  }
  return calls;
}

function inferredExpressionType(expression, customReturns = new Map(), variables = new Map()) {
  const value = expression.trim();
  if (/^-?(?:\d+(?:\.\d+)?|\.\d+)$/u.test(value)) return "number";
  if (/^(?:true|false)$/u.test(value)) return "boolean";
  if (/^"(?:[^"\\]|\\.)*"$/u.test(value)) return "string";
  if (/^\[.*\]$/su.test(value)) {
    const members = splitTopLevelValues(value.slice(1, -1)).map((member) => inferredExpressionType(member, customReturns, variables));
    if (!members.length) return "list";
    return members.every((member) => member && member === members[0]) ? "list<" + members[0] + ">" : "list";
  }
  if (/^\{/u.test(value)) return "object";
  if (/^EMPTY$/u.test(value)) return "EMPTY";
  if (/^EMPTYS$/u.test(value)) return "list";
  if (/^(?:.+)\s+(?:==|!=|<|<=|>|>=|is(?:\s+not)?)\s+(?:.+)$/u.test(value)) return "boolean";
  const call = /^((?:[\p{L}_][\p{L}\p{M}\p{N}_]*\.)?[\p{L}_][\p{L}\p{M}\p{N}_]*)\s*\(/u.exec(value);
  if (call) {
    const parsed = callsOnLine(value)[0]; const firstArgument = parsed && parsed.arguments[0];
    const firstType = firstArgument && inferredExpressionType(firstArgument, customReturns, variables);
    const preserveList = new Set(["list_append", "append", "prepend", "list_remove", "remove", "remove_at", "slice", "reverse", "sort", "sort_descending", "sort_ignore_case", "sort_ignore_case_descending", "sort_natural", "sort_natural_descending", "sort_natural_ignore_case", "sort_natural_ignore_case_descending", "unique", "random_shuffle", "random_sample"]);
    if (preserveList.has(call[1]) && firstType && /^list(?:<.+>)?$/u.test(firstType)) return firstType;
    if (["first", "last", "random_pick"].includes(call[1])) {
      const element = firstType && /^list<(.+)>$/u.exec(firstType); if (element) return element[1];
    }
    return builtinReturnTypes[call[1]] || customReturns.get(call[1]);
  }
  const identifier = /^([\p{L}_][\p{L}\p{M}\p{N}_]*)$/u.exec(value);
  if (identifier) return variables.get(identifier[1]);
  const member = /^([\p{L}_][\p{L}\p{M}\p{N}_]*\.[\p{L}_][\p{L}\p{M}\p{N}_]*)$/u.exec(value);
  if (member) return variables.get(member[1]);
  const arithmetic = /^(.+?)\s*(?:\+|-|\*|\/|%)\s*(.+)$/u.exec(value);
  if (arithmetic) {
    const left = inferredExpressionType(arithmetic[1], customReturns, variables);
    const right = inferredExpressionType(arithmetic[2], customReturns, variables);
    if (left === "number" && right === "number") return "number";
    if (left === "string" && right === "string" && value.includes("+")) return "string";
  }
  return undefined;
}

function mergeInferredTypes(types) {
  const members = [];
  for (const type of types.filter(Boolean)) for (const member of type.split(/\s*\|\s*/u)) if (!members.includes(member)) members.push(member);
  if (!members.length) return undefined;
  if (members.length === 1) return members[0];
  const concrete = members.filter((member) => member !== "EMPTY");
  if (concrete.length === 1 && members.includes("EMPTY")) return concrete[0] + " | EMPTY";
  return members.join(" | ");
}

function typeAccepts(expected, actual) {
  if (!expected || !actual || expected === "value" || actual === "value") return true;
  const expectedMembers = new Set(expected.split(/\s*\|\s*/u));
  const actualMembers = actual.split(/\s*\|\s*/u);
  return actualMembers.every((member) => member === "EMPTY" || expectedMembers.has(member));
}

function inferredFunctionReturns(document) {
  const result = new Map(); const functions = flattenStructures(documentStructure(document.getText()).roots).filter((entry) => entry.kind === "SEP");
  for (let pass = 0; pass < functions.length + 1; pass += 1) {
    let changed = false;
    for (const item of functions) {
      const variables = new Map();
      for (const parameter of item.parameters) {
        const typed = /^([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*:\s*(.+)$/u.exec(parameter);
        if (typed) variables.set(typed[1], typed[2].trim());
      }
      const returns = [];
      for (const line of item.source.split(/\r?\n/u)) {
        const typedAssignment = /^\s*((?:list<[^>]+>|[\p{L}_][\p{L}\p{M}\p{N}_]*))\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(codeText(line));
        if (typedAssignment) { variables.set(typedAssignment[2], typedAssignment[1]); continue; }
        const assignment = /^\s*([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(codeText(line));
        if (assignment) {
          const type = inferredExpressionType(assignment[2], result, variables);
          if (type) variables.set(assignment[1], mergeInferredTypes([variables.get(assignment[1]), type]));
        }
        const returned = /^\s*return\s+(.+)$/u.exec(codeText(line));
        if (returned) returns.push(inferredExpressionType(returned[1], result, variables));
      }
      const inferred = mergeInferredTypes(returns);
      if (inferred && result.get(item.label) !== inferred) {
        result.set(item.label, inferred); changed = true;
      }
    }
    if (!changed) break;
  }
  return result;
}

class SeparanInlayHintsProvider {
  async provideInlayHints(document, range) {
    if (!vscode.workspace.getConfiguration("separan", document.uri).get("inlayHints.types", true)) return [];
    const hints = []; const customReturns = inferredFunctionReturns(document); let variables = new Map();
    for (const structure of flattenStructures(documentStructure(document.getText()).roots).filter((item) => item.kind === "object")) {
      variables.set(structure.label, "object");
      for (const line of structure.source.split(/\r?\n/u)) {
        const typed = /^\s*((?:list<[^>]+>|[\p{L}_][\p{L}\p{M}\p{N}_]*))\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=/u.exec(codeText(line));
        const assignment = typed || /^\s*([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(codeText(line));
        if (assignment) variables.set(structure.label + "." + (typed ? typed[2] : assignment[1]),
          typed ? typed[1] : inferredExpressionType(assignment[2], customReturns, variables));
      }
    }
    const objectTypes = new Map(variables);
    for (const alias of importAliases(document).keys()) {
      const imported = await importedDocument(document, alias); if (imported) for (const [name, type] of inferredFunctionReturns(imported)) customReturns.set(`${alias}.${name}`, type);
    }
    for (let line = range.start.line; line <= Math.min(range.end.line, document.lineCount - 1); line += 1) {
      const text = codeText(document.lineAt(line).text);
      const functionStart = /^\s*SEP:[^\s:()]+\s*(?:\(([^)]*)\))?/u.exec(text);
      if (functionStart) {
        variables = new Map(objectTypes);
        for (const parameter of splitTopLevelValues(functionStart[1] || "")) {
          const typed = /^([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*:\s*(.+)$/u.exec(parameter);
          if (typed) variables.set(typed[1], typed[2].trim());
        }
        continue;
      }
      const typedAssignment = /^\s*((?:list<[^>]+>|[\p{L}_][\p{L}\p{M}\p{N}_]*))\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(text);
      if (typedAssignment) { variables.set(typedAssignment[2], typedAssignment[1]); continue; }
      const loop = /^\s*for\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s+in\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\b/u.exec(text);
      if (loop) {
        const collection = variables.get(loop[2]); const element = collection && /^list<(.+)>$/u.exec(collection);
        if (element) variables.set(loop[1], element[1]);
        continue;
      }
      const assignment = /^\s*([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(text);
      if (!assignment) continue;
      let expression = assignment[2].trim(); const qualified = /^([\p{L}_][\p{L}\p{M}\p{N}_]*\.[\p{L}_][\p{L}\p{M}\p{N}_]*)\s*\(/u.exec(expression);
      const type = qualified ? customReturns.get(qualified[1]) : inferredExpressionType(expression, customReturns, variables); if (!type) continue;
      variables.set(assignment[1], type);
      const column = text.indexOf(assignment[1]) + assignment[1].length;
      const hint = new vscode.InlayHint(new vscode.Position(line, column), `: ${type}`, vscode.InlayHintKind.Type);
      hint.paddingLeft = true; hints.push(hint);
    }
    return hints;
  }
}

function functionItem(document, structure) {
  const start = new vscode.Position(structure.start_line - 1, structure.start_column - 1);
  const endLine = Math.min(document.lineCount - 1, structure.end_line - 1);
  return new vscode.CallHierarchyItem(vscode.SymbolKind.Function, structure.label, structure.path, document.uri,
    new vscode.Range(new vscode.Position(structure.start_line - 1, 0), new vscode.Position(endLine, document.lineAt(endLine).text.length)),
    new vscode.Range(start, start.translate(0, structure.label.length)));
}

function callRanges(document, structure, name) {
  const ranges = []; const escaped = name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"); const pattern = new RegExp(`\\b${escaped}\\s*(?=\\()`, "gu");
  for (let line = structure.start_line - 1; line < Math.min(document.lineCount, structure.end_line); line += 1)
    for (const match of codeText(document.lineAt(line).text).matchAll(pattern)) ranges.push(new vscode.Range(line, match.index, line, match.index + name.length));
  return ranges;
}

function qualifiedCallRanges(document, structure, alias, name) {
  const ranges = []; const escapedAlias = alias.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
  const escapedName = name.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
  const pattern = new RegExp("\\b" + escapedAlias + "\\." + escapedName + "\\s*(?=\\()", "gu");
  for (let line = structure.start_line - 1; line < Math.min(document.lineCount, structure.end_line); line += 1)
    for (const match of codeText(document.lineAt(line).text).matchAll(pattern)) {
      const start = match.index + alias.length + 1;
      ranges.push(new vscode.Range(line, start, line, start + name.length));
    }
  return ranges;
}

class SeparanCallHierarchyProvider {
  async prepareCallHierarchy(document, position) {
    const qualified = qualifiedIdentifierAt(document, position);
    if (qualified) {
      const targetDocument = await importedDocument(document, qualified.alias);
      const target = targetDocument && flattenStructures(documentStructure(targetDocument.getText()).roots)
        .find((item) => item.kind === "SEP" && item.label === qualified.name);
      if (target) return functionItem(targetDocument, target);
    }
    const identifier = identifierAtPosition(document, position); const label = labelAtPosition(document, position); const name = label ? label.name : identifier && identifier.name;
    const structure = name && flattenStructures(documentStructure(document.getText()).roots).find((item) => item.kind === "SEP" && item.label === name);
    return structure ? functionItem(document, structure) : undefined;
  }
  async provideCallHierarchyIncomingCalls(item) {
    const sourceDocument = await vscode.workspace.openTextDocument(item.uri); const workspaceDocuments = await workspaceSeparanDocuments();
    const documents = new Map([[sourceDocument.uri.toString(), sourceDocument], ...workspaceDocuments.map((document) => [document.uri.toString(), document])]);
    const result = []; for (const document of documents.values()) {
      for (const structure of flattenStructures(documentStructure(document.getText()).roots).filter((entry) => entry.kind === "SEP")) {
        const ranges = document.uri.toString() === item.uri.toString() ? callRanges(document, structure, item.name) : [];
        for (const alias of importAliases(document).keys()) {
          const target = importedUri(document, alias);
          if (target && target.fsPath.toLocaleLowerCase() === item.uri.fsPath.toLocaleLowerCase())
            ranges.push(...qualifiedCallRanges(document, structure, alias, item.name));
        }
        if (ranges.length) result.push(new vscode.CallHierarchyIncomingCall(functionItem(document, structure), ranges));
      }
    }
    return result;
  }
  async provideCallHierarchyOutgoingCalls(item) {
    const document = await vscode.workspace.openTextDocument(item.uri);
    const source = flattenStructures(documentStructure(document.getText()).roots).find((entry) => entry.kind === "SEP" && entry.label === item.name);
    if (!source) return [];
    const definitions = new Map();
    for (const structure of flattenStructures(documentStructure(document.getText()).roots))
      if (structure.kind === "SEP") definitions.set(structure.label, structure);
    const result = [];
    for (const called of source.calls) {
      const target = definitions.get(called); if (target) result.push(new vscode.CallHierarchyOutgoingCall(functionItem(document, target), callRanges(document, source, called)));
    }
    for (const alias of importAliases(document).keys()) {
      const targetDocument = await importedDocument(document, alias); if (!targetDocument) continue;
      for (const target of flattenStructures(documentStructure(targetDocument.getText()).roots).filter((entry) => entry.kind === "SEP")) {
        const ranges = qualifiedCallRanges(document, source, alias, target.label);
        if (ranges.length) result.push(new vscode.CallHierarchyOutgoingCall(functionItem(targetDocument, target), ranges));
      }
    }
    return result;
  }
}

class SeparanCodeLensProvider {
  async provideCodeLenses(document) {
    const lenses = []; const structures = flattenStructures(documentStructure(document.getText()).roots).filter((item) => item.kind === "SEP");
    const workspaceDocuments = await workspaceSeparanDocuments();
    const documents = new Map([[document.uri.toString(), document], ...workspaceDocuments.map((candidate) => [candidate.uri.toString(), candidate])]);
    for (const structure of structures) {
      const range = new vscode.Range(structure.start_line - 1, 0, structure.start_line - 1, 0);
      let references = 0;
      for (const candidate of documents.values()) references += functionLocations(candidate, structure.label).filter((location) => !(location.uri.toString() === document.uri.toString() && location.range.start.line === structure.start_line - 1)).length;
      lenses.push(new vscode.CodeLens(range, { title: `${references} reference${references === 1 ? "" : "s"}`, command: "editor.action.showReferences",
        arguments: [document.uri, new vscode.Position(structure.start_line - 1, structure.start_column - 1), await new SeparanReferenceProvider().provideReferences(document, new vscode.Position(structure.start_line - 1, structure.start_column - 1))] }));
      if (structure.parameters.length === 0 && structure.label !== "main") lenses.push(new vscode.CodeLens(range, { title: "$(play) Run Function", command: "separan.runFunction", arguments: [document.uri, structure.label] }));
      if (structure.parameters.length === 0 && structure.label.startsWith("test_")) lenses.push(new vscode.CodeLens(range, { title: "$(beaker) Run Test", command: "separan.runFunction", arguments: [document.uri, structure.label] }));
    }
    return lenses;
  }
}

class SeparanHoverProvider {
  async provideHover(document, position) {
    const label = labelAtPosition(document, position);
    if (label) {
      const item = flattenStructures(documentStructure(document.getText()).roots).find((entry) => entry.label === label.name);
      if (!item) return undefined;
      return new vscode.Hover(new vscode.MarkdownString(`**${item.kind}:${item.label}**  \nPath: \`${item.path}\`  \nLines ${item.start_line}–${item.end_line}`), label.range);
    }
    const qualified = qualifiedIdentifierAt(document, position);
    if (qualified) {
      const target = await importedDocument(document, qualified.alias); const importedDefinition = target && functionDefinitions(target).get(qualified.name);
      if (importedDefinition) return new vscode.Hover("Imported function " + qualified.alias + "." + qualified.name + " in " + path.basename(target.uri.fsPath));
    }
    const identifier = identifierAtPosition(document, position); const definition = identifier && functionDefinitions(document).get(identifier.name);
    return definition ? new vscode.Hover(new vscode.MarkdownString(`**Function** \`SEP:${identifier.name}\`  \nDefined on line ${definition.range.start.line + 1}`), identifier.range) : undefined;
  }
}

function localBindingAt(document, position, name) {
  const scope = flattenStructures(documentStructure(document.getText()).roots)
    .filter((item) => item.kind === "SEP" && item.start_line <= position.line + 1 && item.end_line >= position.line + 1)
    .sort((left, right) => (left.end_line - left.start_line) - (right.end_line - right.start_line))[0];
  if (!scope) return undefined;
  const positionLine = codeText(document.lineAt(position.line).text); const after = positionLine.slice(position.character + name.length);
  if (/^\s*\(/u.test(after)) return undefined;
  const parameterNames = new Set(scope.parameters.map((parameter) => parameter.split(":", 1)[0].trim()));
  let bound = parameterNames.has(name); let definition;
  const locations = []; const escaped = name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"); const pattern = new RegExp("\\b" + escaped + "\\b", "gu");
  for (let line = scope.start_line - 1; line < Math.min(document.lineCount, scope.end_line); line += 1) {
    const raw = document.lineAt(line).text; const text = codeText(raw);
    const assignment = /^\s*(?:(?:list<[^>]+>|[\p{L}_][\p{L}\p{M}\p{N}_]*)\s+)?([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=/u.exec(text);
    const loop = /^\s*for\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s+in\b/u.exec(text);
    if ((assignment && assignment[1] === name) || (loop && loop[1] === name)) bound = true;
    for (const match of text.matchAll(pattern)) {
      const before = text[match.index - 1]; if (before === "." || before === ":" || before === "@") continue;
      let quoted = false; let escapedCharacter = false;
      for (let index = 0; index < match.index; index += 1) {
        if (escapedCharacter) escapedCharacter = false;
        else if (text[index] === "\\" && quoted) escapedCharacter = true;
        else if (text[index] === '"') quoted = !quoted;
      }
      if (quoted) continue;
      const location = new vscode.Location(document.uri, new vscode.Range(line, match.index, line, match.index + name.length)); locations.push(location);
      if (!definition && (parameterNames.has(name) && line === scope.start_line - 1 || assignment && assignment[1] === name || loop && loop[1] === name)) definition = location;
    }
  }
  return bound && locations.length ? { definition: definition || locations[0], locations } : undefined;
}

class SeparanDefinitionProvider {
  async provideDefinition(document, position) {
    const imported = importAtPosition(document, position);
    if (imported) {
      const uri = importedUri(document, imported.alias);
      if (uri) try {
        await vscode.workspace.fs.stat(uri);
        return new vscode.Location(uri, new vscode.Position(0, 0));
      } catch (_) { return undefined; }
    }
    const boundary = functionBoundaryAtPosition(document, position);
    if (boundary) return functionDefinitions(document).get(boundary.name);
    const label = labelAtPosition(document, position);
    if (label) return allLabelLocations(document, label.name)[0];
    const qualified = qualifiedIdentifierAt(document, position);
    if (qualified) { const target = await importedDocument(document, qualified.alias); return target && functionDefinitions(target).get(qualified.name); }
    const identifier = identifierAtPosition(document, position); if (!identifier) return undefined;
    const binding = localBindingAt(document, position, identifier.name); if (binding) return binding.definition;
    const local = functionDefinitions(document).get(identifier.name); if (local) return local;
    return undefined;
  }
}

class SeparanReferenceProvider {
  async provideReferences(document, position) {
    const boundary = functionBoundaryAtPosition(document, position);
    if (boundary && functionDefinitions(document).has(boundary.name)) return importedFunctionLocations(document, boundary.name, document);
    const label = labelAtPosition(document, position);
    if (label) return workspaceLabelLocations(document, label.name);
    const qualified = qualifiedIdentifierAt(document, position);
    if (qualified) {
      const target = await importedDocument(document, qualified.alias);
      return target ? importedFunctionLocations(target, qualified.name, document) : [];
    }
    const identifier = identifierAtPosition(document, position); if (!identifier) return [];
    const binding = localBindingAt(document, position, identifier.name); if (binding) return binding.locations;
    if (!functionDefinitions(document).has(identifier.name)) return [];
    return importedFunctionLocations(document, identifier.name, document);
  }
}

class SeparanRenameProvider {
  async prepareRename(document, position) {
    const tag = tagAtPosition(document, position); if (tag) return { range: tag.range, placeholder: tag.name };
    const boundary = functionBoundaryAtPosition(document, position);
    if (boundary && functionDefinitions(document).has(boundary.name)) return { range: boundary.range, placeholder: boundary.name };
    const label = labelAtPosition(document, position); if (label) return { range: label.range, placeholder: label.name };
    const qualified = qualifiedIdentifierAt(document, position);
    if (qualified) {
      const target = await importedDocument(document, qualified.alias);
      if (target && functionDefinitions(target).has(qualified.name)) {
        const identifier = identifierAtPosition(document, position);
        return { range: identifier.range, placeholder: qualified.name };
      }
    }
    const identifier = identifierAtPosition(document, position);
    if (identifier) {
      const binding = localBindingAt(document, position, identifier.name); if (binding) return { range: identifier.range, placeholder: identifier.name };
      if (functionDefinitions(document).has(identifier.name)) return { range: identifier.range, placeholder: identifier.name };
    }
    throw new Error("Place the cursor on a Separan label or function.");
  }
  async provideRenameEdits(document, position, newName) {
    if (!/^[\p{L}_][\p{L}\p{M}\p{N}_]*$/u.test(newName)) throw new Error("Separan labels must be valid identifiers.");
    const tag = tagAtPosition(document, position); const boundary = functionBoundaryAtPosition(document, position); const label = labelAtPosition(document, position);
    const qualified = qualifiedIdentifierAt(document, position); const identifier = identifierAtPosition(document, position); let locations = [];
    if (tag) {
      const documents = await workspaceSeparanDocuments();
      const uniqueDocuments = new Map([[document.uri.toString(), document], ...documents.map((candidate) => [candidate.uri.toString(), candidate])]);
      for (const candidate of uniqueDocuments.values()) locations.push(...tagLocations(candidate, tag.name));
    }
    else if (boundary && functionDefinitions(document).has(boundary.name)) locations = await importedFunctionLocations(document, boundary.name, document);
    else if (label) locations = await workspaceLabelLocations(document, label.name);
    else if (qualified) {
      const target = await importedDocument(document, qualified.alias);
      if (target && functionDefinitions(target).has(qualified.name)) locations = await importedFunctionLocations(target, qualified.name, document);
    }
    else if (identifier) {
      const binding = localBindingAt(document, position, identifier.name);
      if (binding) locations = binding.locations;
      else if (functionDefinitions(document).has(identifier.name)) locations = await importedFunctionLocations(document, identifier.name, document);
    }
    if (!locations.length) return undefined;
    const edit = new vscode.WorkspaceEdit(); for (const location of locations) edit.replace(location.uri, location.range, newName); return edit;
  }
}

class SeparanDocumentSymbolProvider {
  provideDocumentSymbols(document) {
    const convert = (item) => {
      const kind = item.kind === "SEP" ? vscode.SymbolKind.Function : item.kind === "object" ? vscode.SymbolKind.Object : item.kind === "list" ? vscode.SymbolKind.Array : vscode.SymbolKind.Namespace;
      const start = new vscode.Position(item.start_line - 1, 0); const endLine = Math.min(document.lineCount - 1, item.end_line - 1);
      const symbol = new vscode.DocumentSymbol(`${item.kind}:${item.label}`, item.path, kind,
        new vscode.Range(start, new vscode.Position(endLine, document.lineAt(endLine).text.length)),
        new vscode.Range(start, new vscode.Position(item.start_line - 1, document.lineAt(item.start_line - 1).text.length)));
      symbol.children = (item.children || []).map(convert); return symbol;
    };
    return documentStructure(document.getText()).roots.map(convert);
  }
}

function formatSource(source, indentation = "    ") {
  const result = []; let depth = 0; let commentLabel;
  const open = /^(?:SEP|if|while|for|object|list|try|error|http_route|transaction)\b.*:[^\s:()]+(?:\([^)]*\))?\s*$/u;
  const close = /^(?:END_SEP|endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):[^\s:()]+\s*$/u;
  const branch = /^(?:elseif\b|else:|catch\b|finally:)/u;
  const trailingNewline = source.endsWith("\n") || source.endsWith("\r");
  for (const raw of source.split(/\r?\n/u)) {
    const stripped = raw.trim();
    if (!stripped) { result.push(""); continue; }
    const delimiter = multilineCommentDelimiter(stripped);
    if (delimiter !== undefined) {
      result.push(indentation.repeat(depth) + stripped);
      commentLabel = commentLabel === delimiter ? undefined : (commentLabel === undefined ? delimiter : commentLabel);
      continue;
    }
    if (commentLabel !== undefined) { result.push(indentation.repeat(depth) + stripped); continue; }
    const code = codeText(stripped);
    if (close.test(code) || branch.test(code)) depth = Math.max(0, depth - 1);
    result.push(indentation.repeat(depth) + stripped);
    if (open.test(code) || branch.test(code)) depth += 1;
  }
  if (trailingNewline && result[result.length - 1] === "") result.pop();
  return result.join("\n") + (trailingNewline ? "\n" : "");
}

class SeparanFormattingProvider {
  provideDocumentFormattingEdits(document, options) {
    const indentation = options.insertSpaces ? " ".repeat(options.tabSize) : "\t";
    const formatted = formatSource(document.getText(), indentation); if (formatted === document.getText()) return [];
    const end = document.lineAt(document.lineCount - 1).rangeIncludingLineBreak.end;
    return [vscode.TextEdit.replace(new vscode.Range(new vscode.Position(0, 0), end), formatted)];
  }
}

class SeparanCodeActionProvider {
  provideCodeActions(document, range, context) {
    const actions = [];
    for (const diagnostic of context.diagnostics) {
      if (diagnostic.code === "structure") {
        const expected = /^Expected\s+([^:]+):([^\.]+)\./u.exec(diagnostic.message);
        if (expected) {
          const line = diagnostic.range.start.line; const raw = document.lineAt(line).text;
          const indentation = /^\s*/u.exec(raw)[0]; const replacement = indentation + expected[1] + ":" + expected[2];
          const action = new vscode.CodeAction("Replace with " + expected[1] + ":" + expected[2], vscode.CodeActionKind.QuickFix);
          action.diagnostics = [diagnostic]; action.isPreferred = true; action.edit = new vscode.WorkspaceEdit();
          action.edit.replace(document.uri, document.lineAt(line).range, replacement); actions.push(action);
        }
      } else if (diagnostic.code === "unused-import") {
        const action = new vscode.CodeAction("Remove unused import", vscode.CodeActionKind.QuickFix);
        action.diagnostics = [diagnostic]; action.isPreferred = true; action.edit = new vscode.WorkspaceEdit();
        action.edit.delete(document.uri, document.lineAt(diagnostic.range.start.line).rangeIncludingLineBreak); actions.push(action);
      } else if (diagnostic.code === "undefined-function") {
        const match = /^Function '([^']+)' is not defined\./u.exec(diagnostic.message); if (!match) continue;
        const action = new vscode.CodeAction("Create function '" + match[1] + "'", vscode.CodeActionKind.QuickFix);
        action.diagnostics = [diagnostic]; action.edit = new vscode.WorkspaceEdit();
        const end = document.lineAt(document.lineCount - 1).rangeIncludingLineBreak.end;
        action.edit.insert(document.uri, end, `\nSEP:${match[1]}\nEND_SEP:${match[1]}\n`); actions.push(action);
      } else if (diagnostic.code === "missing-import") {
        const declaration = importDeclarations(document).find((item) => item.pathRange.intersection(diagnostic.range));
        const uri = declaration && moduleUri(document, declaration.path); if (!uri) continue;
        const action = new vscode.CodeAction("Create module '" + declaration.path + "'", vscode.CodeActionKind.QuickFix);
        action.diagnostics = [diagnostic]; action.edit = new vscode.WorkspaceEdit(); action.edit.createFile(uri, { ignoreIfExists: true }); actions.push(action);
      }
    }
    return actions;
  }
}
SeparanCodeActionProvider.providedCodeActionKinds = [vscode.CodeActionKind.QuickFix];

async function goToMatchingLabel() {
  const editor = currentEditor(); if (!editor) return;
  const label = labelAt(editor); if (!label) return vscode.window.showInformationMessage("Place the cursor on a Separan label.");
  const stack = []; const completed = [];
  const openPattern = /^\s*(SEP|sep|if|while|for|object|list|try|error|http_route|transaction)\b.*?:([^\s:()]+)\s*(?:\([^)]*\))?\s*$/u;
  const closePattern = /^\s*(END_SEP|end_sep|endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):([^\s:()]+)\s*$/u;
  const closerKinds = { endif: "if", endwhile: "while", endfor: "for", end_object: "object", end_list: "list", endtry: "try", end_error: "error", end_http_route: "http_route", end_transaction: "transaction" };
  let commentLabel;
  for (let line = 0; line < editor.document.lineCount; line += 1) {
    const raw = editor.document.lineAt(line).text; const delimiter = multilineCommentDelimiter(raw);
    if (delimiter !== undefined) { commentLabel = commentLabel === delimiter ? undefined : (commentLabel === undefined ? delimiter : commentLabel); continue; }
    if (commentLabel !== undefined) continue;
    const text = codeText(raw); const opened = openPattern.exec(text); const closed = closePattern.exec(text);
    if (opened) stack.push({ kind: opened[1], label: opened[2], open: line });
    else if (closed && stack.length && stack[stack.length - 1].kind === closerKinds[closed[1]] && stack[stack.length - 1].label === closed[2]) {
      const item = stack.pop(); item.close = line; completed.push(item);
    }
  }
  const currentLine = editor.selection.active.line;
  const block = completed.find((item) => item.label === label && (item.open === currentLine || item.close === currentLine));
  if (!block) return vscode.window.showInformationMessage(`No matching endpoint found for :${label}.`);
  const targetLine = block.open === currentLine ? block.close : block.open;
  const text = editor.document.lineAt(targetLine).text; const start = text.lastIndexOf(`:${label}`) + 1;
  const target = new vscode.Position(targetLine, start);
  if (target) { editor.selection = new vscode.Selection(target, target); editor.revealRange(new vscode.Range(target, target)); }
}

async function goToLabel() {
  const editor = currentEditor(); if (!editor) return;
  const items = []; const stack = [];
  const pattern = /^\s*(SEP|sep|if|while|for|object|list|try|error|http_route|transaction)\b.*?:([^\s:()]+)\s*(?:\([^)]*\))?\s*$/u;
  const closePattern = /^\s*(endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):([^\s:()]+)\s*$/u;
  let commentLabel;
  for (let line = 0; line < editor.document.lineCount; line += 1) {
    const raw = editor.document.lineAt(line).text; const delimiter = multilineCommentDelimiter(raw);
    if (delimiter !== undefined) { commentLabel = commentLabel === delimiter ? undefined : (commentLabel === undefined ? delimiter : commentLabel); continue; }
    if (commentLabel !== undefined) continue;
    const text = codeText(raw); const match = pattern.exec(text); const closed = closePattern.exec(text);
    if (match) {
      const parent = stack.length ? `${stack.map((item) => item.label).join(" › ")} › ` : "";
      items.push({ label: match[2], description: `${parent}${match[1]} — line ${line + 1}`, line }); stack.push({ label: match[2] });
    } else if (closed && stack.length && stack[stack.length - 1].label === closed[2]) stack.pop();
  }
  const selected = await vscode.window.showQuickPick(items, { placeHolder: "Go to a labeled structure" });
  if (selected) { const position = new vscode.Position(selected.line, 0); editor.selection = new vscode.Selection(position, position); editor.revealRange(new vscode.Range(position, position)); }
}

async function runFile() {
  const editor = currentEditor(); if (!editor) return;
  await editor.document.save();
  await executeSeparanTask("Run File", editor.document.uri, [editor.document.uri.fsPath]);
}

async function checkFile() {
  const editor = currentEditor();
  if (!editor) return vscode.window.showInformationMessage("Open a Separan file before checking it.");
  await editor.document.save();
  await executeSeparanTask("Check Current File", editor.document.uri, ["--check", editor.document.uri.fsPath]);
}

async function runFunction(uri, name) {
  if (!uri || !name) {
    const editor = currentEditor(); if (!editor) return vscode.window.showInformationMessage("Open a Separan file and place the cursor inside a function.");
    const scope = await scopeAt(editor); if (!scope || scope.kind !== "SEP") return vscode.window.showInformationMessage("Place the cursor inside a Separan function.");
    uri = editor.document.uri; name = scope.label;
  }
  const document = await vscode.workspace.openTextDocument(uri); if (document.isDirty) await document.save();
  const structures = flattenStructures(documentStructure(document.getText()).roots);
  const target = structures.find((item) => item.kind === "SEP" && item.label === name);
  if (!target) return vscode.window.showErrorMessage(`Function ${name} was not found.`);
  if (target.parameters.length) return vscode.window.showErrorMessage(`Run Function currently requires zero parameters; ${name} has ${target.parameters.length}.`);
  return runFunctionList(document, structures, [name], `Run ${name}`);
}

async function runFunctionList(document, structures, names, title) {
  const uri = document.uri;
  const lines = document.getText().split(/\r?\n/u); const main = structures.find((item) => item.kind === "SEP" && item.label === "main");
  if (main) lines.splice(main.start_line - 1, main.end_line - main.start_line + 1);
  lines.push("", "SEP:main", ...names.map((functionName) => `${functionName}()`), "END_SEP:main", "");
  const temporary = path.join(path.dirname(uri.fsPath), `.separan-vscode-run-${process.pid}-${Date.now()}.sep`);
  await fs.promises.writeFile(temporary, lines.join("\n"), "utf8");
  try {
    const execution = await executeSeparanTask(title, uri, [temporary]);
    temporaryRuns.set(execution, temporary);
  } catch (error) {
    await fs.promises.rm(temporary, { force: true }); throw error;
  }
}

async function runTests() {
  const editor = currentEditor(); if (!editor) return vscode.window.showInformationMessage("Open a Separan file containing test_ functions.");
  if (editor.document.isDirty) await editor.document.save();
  const structures = flattenStructures(documentStructure(editor.document.getText()).roots);
  const tests = structures.filter((item) => item.kind === "SEP" && item.label.startsWith("test_") && item.parameters.length === 0).map((item) => item.label);
  if (!tests.length) return vscode.window.showInformationMessage("No zero-argument test_ functions were found in the active file.");
  return runFunctionList(editor.document, structures, tests, `Run ${tests.length} Separan Tests`);
}

async function diagnoseRuntime() {
  const editor = currentEditor();
  const resource = editor && editor.document.uri;
  const config = runtimeConfiguration(resource);
  runtimeOutput.clear();
  runtimeOutput.appendLine(`Executable: ${config.executable}`);
  runtimeOutput.appendLine(`Workspace: ${resource && vscode.workspace.getWorkspaceFolder(resource) ? vscode.workspace.getWorkspaceFolder(resource).uri.fsPath : "(none)"}`);
  try {
    const folder = resource ? vscode.workspace.getWorkspaceFolder(resource) : undefined;
    const result = await execFileAsync(config.executable, [...config.arguments, "--help"], {
      cwd: folder ? folder.uri.fsPath : undefined,
      env: { ...process.env, ...config.environment },
      encoding: "utf8",
      windowsHide: true,
    });
    runtimeOutput.appendLine("");
    runtimeOutput.append(result.stdout.trimEnd());
    if (result.stderr) runtimeOutput.appendLine(`\n${result.stderr.trimEnd()}`);
    runtimeOutput.show(true);
    vscode.window.showInformationMessage("Separan native runtime is available.");
  } catch (error) {
    runtimeOutput.appendLine("");
    runtimeOutput.appendLine(error.stderr || error.message);
    runtimeOutput.show(true);
    vscode.window.showErrorMessage("Separan runtime could not be started. See the Separan Runtime output.");
  }
}

async function copyAiScope() {
  const editor = currentEditor(); if (!editor) return;
  const scope = await scopeAt(editor);
  if (!scope) return vscode.window.showInformationMessage("Place the cursor on a Separan label.");
  await vscode.env.clipboard.writeText(`Modify only Separan scope ${scope.path}`);
  vscode.window.showInformationMessage(`Copied AI edit scope ${scope.path}`);
}

function documentStructure(source) {
  const roots = []; const stack = []; const diagnostics = []; let commentLabel;
  const lines = source.split(/\r?\n/u);
  const openPattern = /^\s*(SEP|if|while|for|object|list|try|error|http_route|transaction)\b.*?:([^\s:()]+)\s*(?:\([^)]*\))?\s*$/u;
  const closePattern = /^\s*(END_SEP|endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):([^\s:()]+)\s*$/u;
  const closerKinds = { END_SEP: "SEP", endif: "if", endwhile: "while", endfor: "for", end_object: "object", end_list: "list", endtry: "try", end_error: "error", end_http_route: "http_route", end_transaction: "transaction" };
  for (let line = 0; line < lines.length; line += 1) {
    const delimiter = multilineCommentDelimiter(lines[line]);
    if (delimiter !== undefined) { commentLabel = commentLabel === delimiter ? undefined : (commentLabel === undefined ? delimiter : commentLabel); continue; }
    if (commentLabel !== undefined) continue;
    const text = codeText(lines[line]); const opened = openPattern.exec(text); const closed = closePattern.exec(text);
    if (opened) {
      const parent = stack[stack.length - 1];
      const pathName = parent ? `${parent.path}/${opened[2]}` : opened[2];
      const node = { id: `${opened[1]}:${pathName}:${line + 1}`, kind: opened[1], label: opened[2], path: pathName,
        start_line: line + 1, start_column: Math.max(1, lines[line].indexOf(`:${opened[2]}`) + 2), end_line: line + 1,
        tags: [], parameters: [], reads: [], writes: [], calls: [], children: [], source: "" };
      if (opened[1] === "SEP") {
        const parameters = new RegExp(`^\\s*SEP:${opened[2].replace(/[.*+?^${}()|[\]\\]/gu, "\\$&")}\\s*\\(([^)]*)\\)`, "u").exec(text);
        if (parameters && parameters[1].trim()) node.parameters = parameters[1].split(",").map((value) => value.trim()).filter(Boolean);
      }
      if (parent) parent.children.push(node); else roots.push(node);
      stack.push(node);
    } else if (closed) {
      const expectedKind = closerKinds[closed[1]]; const top = stack[stack.length - 1];
      if (!top) diagnostics.push({ line, column: Math.max(0, lines[line].indexOf(closed[0].trim())), message: `Unexpected closing label :${closed[2]}.` });
      else if (top.kind !== expectedKind || top.label !== closed[2]) diagnostics.push({ line, column: Math.max(0, lines[line].indexOf(`:${closed[2]}`)), message: `Expected ${blockPairs[top.kind]}:${top.label}.` });
      else {
        const node = stack.pop(); node.end_line = line + 1; node.source = lines.slice(node.start_line - 1, line + 1).join("\n");
        const callPattern = /\b([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*(?=\()/gu;
        node.calls = [...new Set([...node.source.matchAll(callPattern)].map((match) => match[1]).filter((name) => name !== node.label))];
      }
    } else if (/^\s*@[^\s]+\s*$/u.test(text) && stack.length) stack[stack.length - 1].tags.push(text.trim().slice(1));
  }
  for (const node of stack) {
    node.end_line = lines.length; node.source = lines.slice(node.start_line - 1).join("\n");
    const callPattern = /\b([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*(?=\()/gu;
    node.calls = [...new Set([...node.source.matchAll(callPattern)].map((match) => match[1]).filter((name) => name !== node.label))];
    diagnostics.push({ line: node.start_line - 1, column: node.start_column - 1, message: `Missing ${blockPairs[node.kind]}:${node.label}.` });
  }
  return { roots, diagnostics };
}

function publishStructureDiagnostics(document) {
  if (document.languageId !== "separan") return;
  const report = documentStructure(document.getText());
  const items = report.diagnostics.map((item) => {
    const line = Math.min(item.line, Math.max(0, document.lineCount - 1));
    const start = new vscode.Position(line, Math.min(item.column, document.lineAt(line).text.length));
    const end = new vscode.Position(line, Math.min(document.lineAt(line).text.length, start.character + 1));
    const diagnostic = new vscode.Diagnostic(new vscode.Range(start, end), item.message, vscode.DiagnosticSeverity.Error);
    diagnostic.source = "Separan Structure"; diagnostic.code = "structure"; return diagnostic;
  });
  structureDiagnostics.set(document.uri, items);
}

async function publishNativeDiagnostics(document) {
  if (document.languageId !== "separan" || document.isDirty || document.uri.scheme !== "file") return;
  const version = document.version; diagnosticVersions.set(document.uri.toString(), version);
  const config = runtimeConfiguration(document.uri); const folder = vscode.workspace.getWorkspaceFolder(document.uri);
  try {
    await execFileAsync(config.executable, [...config.arguments, "--check", document.uri.fsPath], {
      cwd: folder ? folder.uri.fsPath : undefined, env: { ...process.env, ...config.environment }, encoding: "utf8", windowsHide: true,
    });
    if (diagnosticVersions.get(document.uri.toString()) === version) nativeDiagnostics.delete(document.uri);
  } catch (error) {
    if (diagnosticVersions.get(document.uri.toString()) !== version) return;
    const output = `${error.stderr || ""}\n${error.stdout || ""}`; const items = [];
    const pattern = /SEPARAN\s+(E\d+):\s*(.*?)\s+at line\s+(\d+),\s*column\s+(\d+)/gu;
    for (const match of output.matchAll(pattern)) {
      const line = Math.max(0, Math.min(document.lineCount - 1, Number(match[3]) - 1));
      const column = Math.max(0, Math.min(document.lineAt(line).text.length, Number(match[4]) - 1));
      const start = new vscode.Position(line, column);
      const end = new vscode.Position(line, Math.min(document.lineAt(line).text.length, column + 1));
      const diagnostic = new vscode.Diagnostic(new vscode.Range(start, end), match[2], vscode.DiagnosticSeverity.Error);
      diagnostic.source = "Separan Native"; diagnostic.code = match[1]; items.push(diagnostic);
    }
    if (!items.length) {
      const start = new vscode.Position(0, 0); const message = output.trim() || error.message;
      const diagnostic = new vscode.Diagnostic(new vscode.Range(start, start), message, vscode.DiagnosticSeverity.Error);
      diagnostic.source = "Separan Native"; items.push(diagnostic);
    }
    nativeDiagnostics.set(document.uri, items);
  }
}

async function publishAnalysisDiagnostics(document) {
  if (document.languageId !== "separan" || document.uri.scheme !== "file") return;
  const version = document.version; const items = []; const declarations = importDeclarations(document); const seen = new Map();
  const customReturns = inferredFunctionReturns(document);
  const structures = flattenStructures(documentStructure(document.getText()).roots).filter((item) => item.kind === "SEP");
  const customFunctions = new Map(); const definitionsByName = new Map();
  for (const structure of structures) {
    customFunctions.set(structure.label, structure.parameters);
    const previous = definitionsByName.get(structure.label) || []; previous.push(structure); definitionsByName.set(structure.label, previous);
  }
  for (const [name, definitions] of definitionsByName) if (definitions.length > 1) for (const structure of definitions) {
    const line = structure.start_line - 1; const start = Math.max(0, document.lineAt(line).text.indexOf(name));
    const diagnostic = new vscode.Diagnostic(new vscode.Range(line, start, line, start + name.length), "Function '" + name + "' is defined more than once.", vscode.DiagnosticSeverity.Error);
    diagnostic.source = "Separan Analysis"; diagnostic.code = "duplicate-function"; items.push(diagnostic);
  }
  const calledFunctions = new Set(structures.flatMap((structure) => structure.calls));
  for (const structure of structures) {
    if (structure.label !== "main" && !structure.label.startsWith("test_") && !calledFunctions.has(structure.label)) {
      const line = structure.start_line - 1; const start = Math.max(0, document.lineAt(line).text.indexOf(structure.label));
      const diagnostic = new vscode.Diagnostic(new vscode.Range(line, start, line, start + structure.label.length), "Function '" + structure.label + "' is never used.", vscode.DiagnosticSeverity.Hint);
      diagnostic.source = "Separan Analysis"; diagnostic.code = "unused-function"; diagnostic.tags = [vscode.DiagnosticTag.Unnecessary]; items.push(diagnostic);
    }
    const sourceLines = structure.source.split(/\r?\n/u); let terminated = false;
    for (let offset = 1; offset < sourceLines.length - 1; offset += 1) {
      const text = codeText(sourceLines[offset]); const trimmed = text.trim(); const absoluteLine = structure.start_line - 1 + offset;
      if (/^(?:elseif\b|else:|catch\b|finally:|end(?:if|while|for|try|_transaction):)/u.test(trimmed)) { terminated = false; continue; }
      if (terminated && trimmed && !/^@/u.test(trimmed)) {
        const start = Math.max(0, document.lineAt(absoluteLine).text.search(/\S/u));
        const diagnostic = new vscode.Diagnostic(new vscode.Range(absoluteLine, start, absoluteLine, document.lineAt(absoluteLine).text.length), "Code after return is unreachable.", vscode.DiagnosticSeverity.Warning);
        diagnostic.source = "Separan Analysis"; diagnostic.code = "unreachable-code"; diagnostic.tags = [vscode.DiagnosticTag.Unnecessary]; items.push(diagnostic);
      }
      if (/^return(?:\s|$)/u.test(trimmed)) terminated = true;
      const assignment = /^\s*(?:(?:list<[^>]+>|[\p{L}_][\p{L}\p{M}\p{N}_]*)\s+)?([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=/u.exec(text);
      if (assignment && !assignment[1].startsWith("_")) {
        const escaped = assignment[1].replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
        const occurrences = [...structure.source.matchAll(new RegExp("\\b" + escaped + "\\b", "gu"))].length;
        if (occurrences === 1) {
          const start = Math.max(0, document.lineAt(absoluteLine).text.indexOf(assignment[1]));
          const diagnostic = new vscode.Diagnostic(new vscode.Range(absoluteLine, start, absoluteLine, start + assignment[1].length), "Variable '" + assignment[1] + "' is never used.", vscode.DiagnosticSeverity.Hint);
          diagnostic.source = "Separan Analysis"; diagnostic.code = "unused-variable"; diagnostic.tags = [vscode.DiagnosticTag.Unnecessary]; items.push(diagnostic);
        }
      }
    }
  }
  for (const declaration of declarations) {
    if (seen.has(declaration.alias)) {
      const diagnostic = new vscode.Diagnostic(declaration.aliasRange, "Duplicate import alias '" + declaration.alias + "'.", vscode.DiagnosticSeverity.Error);
      diagnostic.source = "Separan Analysis"; diagnostic.code = "duplicate-import-alias"; items.push(diagnostic);
      continue;
    }
    seen.set(declaration.alias, declaration);
    const uri = moduleUri(document, declaration.path);
    try {
      await vscode.workspace.fs.stat(uri);
      const target = await vscode.workspace.openTextDocument(uri); const definitions = functionDefinitions(target);
      if (await importReaches(target, document.uri)) {
        const diagnostic = new vscode.Diagnostic(declaration.pathRange, "Import creates a cycle through '" + declaration.path + "'.", vscode.DiagnosticSeverity.Error);
        diagnostic.source = "Separan Analysis"; diagnostic.code = "cyclic-import"; items.push(diagnostic);
      }
      for (const [name, type] of inferredFunctionReturns(target)) customReturns.set(declaration.alias + "." + name, type);
      for (const structure of flattenStructures(documentStructure(target.getText()).roots).filter((item) => item.kind === "SEP"))
        customFunctions.set(declaration.alias + "." + structure.label, structure.parameters);
      const escaped = declaration.alias.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
      const pattern = new RegExp("\\b" + escaped + "\\.([\\p{L}_][\\p{L}\\p{M}\\p{N}_]*)\\s*(?=\\()", "gu");
      for (let line = 0; line < document.lineCount; line += 1) for (const match of codeText(document.lineAt(line).text).matchAll(pattern)) {
        if (definitions.has(match[1])) continue;
        const start = match.index + declaration.alias.length + 1;
        const range = new vscode.Range(line, start, line, start + match[1].length);
        const diagnostic = new vscode.Diagnostic(range, "Module '" + declaration.path + "' has no function '" + match[1] + "'.", vscode.DiagnosticSeverity.Error);
        diagnostic.source = "Separan Analysis"; diagnostic.code = "unknown-import-member"; items.push(diagnostic);
      }
    } catch (_) {
      const diagnostic = new vscode.Diagnostic(declaration.pathRange, "Imported module '" + declaration.path + "' was not found.", vscode.DiagnosticSeverity.Error);
      diagnostic.source = "Separan Analysis"; diagnostic.code = "missing-import"; items.push(diagnostic);
    }
  }
  for (const declaration of declarations) {
    const escaped = declaration.alias.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
    let used = false;
    const pattern = new RegExp("\\b" + escaped + "\\.", "u");
    for (let line = 0; line < document.lineCount && !used; line += 1)
      if (line !== declaration.line && pattern.test(codeText(document.lineAt(line).text))) used = true;
    if (!used) {
      const diagnostic = new vscode.Diagnostic(declaration.aliasRange, "Import alias '" + declaration.alias + "' is never used.", vscode.DiagnosticSeverity.Warning);
      diagnostic.source = "Separan Analysis"; diagnostic.code = "unused-import"; items.push(diagnostic);
    }
  }
  const variables = new Map();
  for (let line = 0; line < document.lineCount; line += 1) {
    const text = codeText(document.lineAt(line).text);
    for (const call of callsOnLine(text)) {
      const metadata = builtinMetadata[call.name]; const parameters = customFunctions.get(call.name);
      if (!metadata && !parameters) {
        if (!call.name.includes(".") && !new RegExp("^\\s*SEP:" + call.name.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&") + "\\s*\\(", "u").test(text)) {
          const range = new vscode.Range(line, call.start, line, call.start + call.name.length);
          const diagnostic = new vscode.Diagnostic(range, "Function '" + call.name + "' is not defined.", vscode.DiagnosticSeverity.Error);
          diagnostic.source = "Separan Analysis"; diagnostic.code = "undefined-function"; items.push(diagnostic);
        }
        continue;
      }
      const namedArguments = call.arguments.map((argument) => /^([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=/u.exec(argument)).filter(Boolean);
      const count = metadata ? call.arguments.length - namedArguments.length : call.arguments.length;
      const minimum = metadata ? metadata.minimum : parameters.length; const maximum = metadata ? metadata.maximum : parameters.length;
      const range = new vscode.Range(line, call.start, line, call.start + call.name.length);
      if (count < minimum || count > maximum) {
        const expected = minimum === maximum ? String(minimum) : minimum + "–" + maximum;
        const diagnostic = new vscode.Diagnostic(range, "'" + call.name + "' expects " + expected + " argument(s), but received " + count + ".", vscode.DiagnosticSeverity.Error);
        diagnostic.source = "Separan Analysis"; diagnostic.code = "argument-count"; items.push(diagnostic);
      }
      if (parameters) {
        const names = new Set(parameters.map((parameter) => parameter.split(":", 1)[0].trim()));
        for (const argument of call.arguments) {
          const named = /^([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=/u.exec(argument);
          if (named && !names.has(named[1])) {
            const diagnostic = new vscode.Diagnostic(range, "'" + call.name + "' has no parameter named '" + named[1] + "'.", vscode.DiagnosticSeverity.Error);
            diagnostic.source = "Separan Analysis"; diagnostic.code = "unknown-named-argument"; items.push(diagnostic);
          }
        }
      } else if (metadata && namedArguments.length) {
        const accepted = builtinNamedArguments[call.name] || new Set();
        for (const named of namedArguments) if (!accepted.has(named[1])) {
          const diagnostic = new vscode.Diagnostic(range, "'" + call.name + "' has no named argument '" + named[1] + "'.", vscode.DiagnosticSeverity.Error);
          diagnostic.source = "Separan Analysis"; diagnostic.code = "unknown-named-argument"; items.push(diagnostic);
        }
      }
    }
    const typed = /^\s*((?:list<[^>]+>|[\p{L}_][\p{L}\p{M}\p{N}_]*))\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(text);
    const assignment = typed || /^\s*([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(text);
    if (!assignment) continue;
    const name = typed ? typed[2] : assignment[1]; const expression = typed ? typed[3] : assignment[2];
    const actual = inferredExpressionType(expression, customReturns, variables); const expected = typed ? typed[1] : variables.get(name);
    if (!typeAccepts(expected, actual)) {
      const start = text.indexOf(name); const range = new vscode.Range(line, start, line, start + name.length);
      const diagnostic = new vscode.Diagnostic(range, "Cannot assign " + actual + " to " + expected + " variable '" + name + "'.", vscode.DiagnosticSeverity.Error);
      diagnostic.source = "Separan Analysis"; diagnostic.code = "type-mismatch"; items.push(diagnostic);
    }
    if (typed) variables.set(name, typed[1]); else if (actual) variables.set(name, actual);
  }
  if (document.version === version) analysisDiagnostics.set(document.uri, items);
}

function refreshDiagnostics(document, runNative = false) {
  if (!document || document.languageId !== "separan") return;
  publishStructureDiagnostics(document);
  void publishAnalysisDiagnostics(document);
  if (runNative) void publishNativeDiagnostics(document);
}

function flattenStructures(roots, result = []) {
  for (const node of roots) { result.push(node); flattenStructures(node.children || [], result); }
  return result;
}

function structuralDiff(before, after) {
  const oldItems = new Map(flattenStructures(documentStructure(before).roots).map((item) => [item.path, item]));
  const newItems = new Map(flattenStructures(documentStructure(after).roots).map((item) => [item.path, item]));
  const changes = [];
  for (const [pathName, item] of newItems) {
    const old = oldItems.get(pathName); const status = !old ? "added" : old.source === item.source ? "unchanged" : "modified";
    changes.push({ id: item.id, path: pathName, status }); oldItems.delete(pathName);
  }
  for (const [pathName, item] of oldItems) changes.push({ id: item.id, path: pathName, status: "removed" });
  const summary = { added: 0, removed: 0, modified: 0, unchanged: 0 };
  for (const item of changes) summary[item.status] += 1;
  return { changes, summary };
}

async function scopeAt(editor) {
  const line = editor.selection.active.line + 1;
  return flattenStructures(documentStructure(editor.document.getText()).roots)
    .filter((item) => item.start_line <= line && line <= item.end_line)
    .sort((a, b) => b.start_line - a.start_line)[0];
}

async function headSource(editor) {
  const folder = vscode.workspace.getWorkspaceFolder(editor.document.uri);
  if (!folder) throw new Error("Open the file inside a Git workspace first.");
  try {
    const rootResult = await execFileAsync("git", ["-C", folder.uri.fsPath, "rev-parse", "--show-toplevel"], { encoding: "utf8", windowsHide: true });
    const gitRoot = rootResult.stdout.trim();
    const relative = path.relative(gitRoot, editor.document.uri.fsPath).replace(/\\/g, "/");
    if (!relative || relative === ".." || relative.startsWith("../") || path.isAbsolute(relative)) throw new Error("The active file is outside the Git worktree.");
    const result = await execFileAsync("git", ["-C", gitRoot, "show", `HEAD:${relative}`], { encoding: "utf8", windowsHide: true });
    return result.stdout;
  } catch (error) {
    throw new Error("Could not read this file from Git HEAD. Commit the file once before comparing it.");
  }
}

function renderDiff(report) {
  const symbols = { added: "+", removed: "-", modified: "~", unchanged: "=" };
  const lines = ["Separan structural diff against HEAD", ""];
  if (!report.changes.length) lines.push("No structural changes.");
  for (const item of report.changes) lines.push(`${symbols[item.status]} ${item.path} (${item.status})`);
  const s = report.summary;
  lines.push("", `Added ${s.added}, removed ${s.removed}, modified ${s.modified}, unchanged ${s.unchanged}`);
  return lines.join("\n");
}

function showReview(title, content) {
  reviewOutput.clear(); reviewOutput.appendLine(title); reviewOutput.appendLine(""); reviewOutput.appendLine(content); reviewOutput.show(true);
}

const structureIcons = {
  SEP: "symbol-namespace", if: "symbol-boolean", while: "sync", for: "list-ordered",
  object: "symbol-object", list: "symbol-array", try: "shield", error: "error",
  transaction: "database", http_route: "globe",
};

class StructureTreeItem {
  constructor(data, parent = undefined) {
    this.data = data; this.parent = parent;
    this.children = (data.children || []).map((child) => new StructureTreeItem(child, this));
    this.insights = [];
    for (const [key, title, icon] of [["tags", "Tags", "tag"], ["parameters", "Parameters", "symbol-parameter"], ["reads", "Reads", "eye"], ["writes", "Writes", "edit"], ["calls", "Calls", "call-outgoing"]]) {
      if (data[key] && data[key].length) this.insights.push(new InsightGroup(title, icon, data[key], this));
    }
  }

  treeItem() {
    const label = this.data.kind === "SEP" ? `SEP:${this.data.label}` : `:${this.data.label}`;
    const item = new vscode.TreeItem(label, this.children.length || this.insights.length ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None);
    item.id = this.data.id; item.contextValue = "separanStructure";
    item.description = this.data.status ? `${this.data.kind} • ${this.data.status}` : this.data.kind;
    item.iconPath = new vscode.ThemeIcon(this.data.status === "modified" ? "diff-modified" : this.data.status === "added" ? "diff-added" : (structureIcons[this.data.kind] || "symbol-namespace"));
    const details = [`**${this.data.path}**`, `Lines ${this.data.start_line}–${this.data.end_line}`];
    for (const [key, title] of [["tags", "Tags"], ["parameters", "Parameters"], ["reads", "Reads"], ["writes", "Writes"], ["calls", "Calls"]]) {
      if (this.data[key] && this.data[key].length) details.push(`${title}: \`${this.data[key].join("`, `")}\``);
    }
    item.tooltip = new vscode.MarkdownString(details.join("  \n"));
    item.command = { command: "separan.revealStructure", title: "Reveal Separan Structure", arguments: [this.data] };
    return item;
  }
}

class InsightGroup {
  constructor(label, icon, values, parent) {
    this.label = label; this.icon = icon; this.parent = parent;
    this.children = values.map((value) => new InsightValue(value, this));
  }
  treeItem() {
    const item = new vscode.TreeItem(`${this.label} (${this.children.length})`, vscode.TreeItemCollapsibleState.Collapsed);
    item.iconPath = new vscode.ThemeIcon(this.icon); item.contextValue = "separanInsightGroup"; return item;
  }
}

class InsightValue {
  constructor(value, parent) { this.value = value; this.parent = parent; this.children = []; }
  treeItem() { const tag = this.parent.label === "Tags"; const item = new vscode.TreeItem(tag ? `@${this.value}` : this.value, vscode.TreeItemCollapsibleState.None); item.iconPath = new vscode.ThemeIcon(tag ? "tag" : "symbol-variable"); return item; }
}

class RemovedGroup {
  constructor(changes) {
    this.parent = undefined;
    this.children = changes.map((change) => new RemovedItem(change, this));
  }
  treeItem() {
    const item = new vscode.TreeItem(`Removed from HEAD (${this.children.length})`, vscode.TreeItemCollapsibleState.Collapsed);
    item.iconPath = new vscode.ThemeIcon("diff-removed"); item.contextValue = "separanRemovedGroup"; return item;
  }
}

class RemovedItem {
  constructor(change, parent) { this.change = change; this.parent = parent; this.children = []; }
  treeItem() {
    const item = new vscode.TreeItem(this.change.path, vscode.TreeItemCollapsibleState.None);
    item.description = "removed"; item.iconPath = new vscode.ThemeIcon("diff-removed"); return item;
  }
}

class SemanticTagItem {
  constructor(name, locations, provider) { this.name = name; this.locations = locations; this.provider = provider; }
  treeItem() {
    const item = new vscode.TreeItem(`@${this.name}`, vscode.TreeItemCollapsibleState.Collapsed);
    item.description = `${this.locations.length} location${this.locations.length === 1 ? "" : "s"}`;
    item.iconPath = new vscode.ThemeIcon("tag"); item.contextValue = "separanSemanticTag"; return item;
  }
}

class SemanticTagLocationItem {
  constructor(tag, location) { this.tag = tag; this.location = location; }
  treeItem() {
    const folder = vscode.workspace.getWorkspaceFolder(this.location.uri); const relative = folder ? path.relative(folder.uri.fsPath, this.location.uri.fsPath) : this.location.uri.fsPath;
    const item = new vscode.TreeItem(`${relative}:${this.location.range.start.line + 1}`, vscode.TreeItemCollapsibleState.None);
    item.iconPath = new vscode.ThemeIcon("go-to-file"); item.contextValue = "separanSemanticTagLocation";
    item.command = { command: "separan.revealLocation", title: "Reveal Semantic Tag", arguments: [this.location] }; return item;
  }
}

class SemanticTagProvider {
  constructor() { this.emitter = new vscode.EventEmitter(); this.onDidChangeTreeData = this.emitter.event; this.tags = undefined; }
  refresh() { this.tags = undefined; this.emitter.fire(undefined); }
  getTreeItem(element) { return element.treeItem(); }
  async getChildren(element) {
    if (element instanceof SemanticTagItem) return element.locations.map((location) => new SemanticTagLocationItem(element.name, location));
    if (element) return [];
    if (!this.tags) {
      const tags = new Map();
      for (const document of await workspaceSeparanDocuments()) {
        const pattern = /@([\p{L}_][\p{L}\p{M}\p{N}_]*)/gu;
        for (let line = 0; line < document.lineCount; line += 1) for (const match of codeText(document.lineAt(line).text).matchAll(pattern)) {
          const location = new vscode.Location(document.uri, new vscode.Range(line, match.index + 1, line, match.index + 1 + match[1].length));
          if (!tags.has(match[1])) tags.set(match[1], []); tags.get(match[1]).push(location);
        }
      }
      this.tags = [...tags.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([name, locations]) => new SemanticTagItem(name, locations, this));
    }
    return this.tags;
  }
}

async function revealLocation(location) {
  const document = await vscode.workspace.openTextDocument(location.uri); const editor = await vscode.window.showTextDocument(document);
  editor.selection = new vscode.Selection(location.range.start, location.range.start); editor.revealRange(location.range, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
}

async function renameSemanticTag(item) {
  if (!item || !item.name) return;
  const name = await vscode.window.showInputBox({ title: `Rename @${item.name}`, value: item.name, validateInput: (value) => /^[\p{L}_][\p{L}\p{M}\p{N}_]*$/u.test(value) ? undefined : "Enter a valid identifier." });
  if (!name || name === item.name) return;
  const edit = new vscode.WorkspaceEdit();
  for (const document of await workspaceSeparanDocuments()) for (const location of tagLocations(document, item.name)) edit.replace(location.uri, location.range, name);
  await vscode.workspace.applyEdit(edit);
}

class StructureProvider {
  constructor() {
    this.emitter = new vscode.EventEmitter(); this.onDidChangeTreeData = this.emitter.event;
    this.roots = []; this.loadedKey = undefined; this.nodesById = new Map();
  }

  refresh() { this.loadedKey = undefined; this.emitter.fire(undefined); }
  getTreeItem(element) { return element.treeItem(); }
  getParent(element) { return element.parent; }
  async getChildren(element) {
    if (element) return element.children || [];
    await this.load(); return this.roots;
  }

  async load() {
    const editor = currentEditor();
    if (!editor) { this.roots = []; this.loadedKey = undefined; return; }
    const key = `${editor.document.uri}:${editor.document.version}`;
    if (this.loadedKey === key) return;
    const report = documentStructure(editor.document.getText());
    const statuses = new Map(); let removed = [];
    try {
      const before = await headSource(editor);
      const diff = structuralDiff(before, editor.document.getText());
      for (const change of diff.changes) {
        if (change.status === "removed") removed.push(change);
        else statuses.set(change.path, change.status);
      }
    } catch (_) { /* Untracked files still have a useful structure tree. */ }
    const applyStatus = (node) => {
      node.status = statuses.get(node.path);
      for (const child of node.children || []) applyStatus(child);
      return node;
    };
    this.roots = report.roots.map((root) => new StructureTreeItem(applyStatus(root)));
    if (removed.length) this.roots.push(new RemovedGroup(removed));
    this.nodesById.clear();
    const index = (node) => { if (node.data) this.nodesById.set(node.data.id, node); for (const child of node.children || []) index(child); };
    for (const root of this.roots) index(root);
    this.loadedKey = key;
  }

  async activeNode(line) {
    await this.load(); let best;
    for (const node of this.nodesById.values()) {
      if (node.data.start_line - 1 <= line && line <= node.data.end_line - 1 && (!best || node.data.start_line >= best.data.start_line)) best = node;
    }
    return best;
  }
}

async function revealStructure(data) {
  const editor = currentEditor(); if (!editor || !data || !data.start_line) return;
  const position = new vscode.Position(data.start_line - 1, Math.max(0, data.start_column - 1));
  editor.selection = new vscode.Selection(position, position);
  editor.revealRange(new vscode.Range(position, position), vscode.TextEditorRevealType.InCenterIfOutsideViewport);
}

async function showStructuralDiff() {
  const editor = currentEditor(); if (!editor) return;
  try {
    const before = await headSource(editor);
    const report = structuralDiff(before, editor.document.getText());
    showReview("Separan v0.4 — Structural Diff", renderDiff(report));
  } catch (error) { vscode.window.showErrorMessage(error.message); }
}

async function verifyAiEditScope() {
  const editor = currentEditor(); if (!editor) return;
  try {
    const scope = await scopeAt(editor);
    if (!scope) return vscode.window.showInformationMessage("Place the cursor on the label that defines the allowed AI edit scope.");
    const before = await headSource(editor);
    const diff = structuralDiff(before, editor.document.getText());
    const violations = diff.changes.filter((item) => item.status !== "unchanged" && item.path !== scope.path && !item.path.startsWith(`${scope.path}/`));
    const allowedChanges = diff.changes.filter((item) => item.status !== "unchanged").length - violations.length;
    const report = { passed: violations.length === 0, violations: violations.map((item) => ({ path: item.path, reason: `${item.status} outside allowed scope` })), summary: { allowed_changes: allowedChanges, violations: violations.length } };
    const lines = [report.passed ? "PASS: AI edit scope verified." : "FAIL: AI edit scope violation.", `Allowed: ${scope.path}`];
    for (const item of report.violations) lines.push(`! ${item.path}: ${item.reason}`);
    lines.push(`Allowed changes ${report.summary.allowed_changes}, violations ${report.summary.violations}`);
    showReview("Separan v0.4 — AI Edit Scope Verification", lines.join("\n"));
    if (report.passed) vscode.window.showInformationMessage(`Verified: changes stay inside ${scope.path}`);
    else vscode.window.showErrorMessage(`AI scope violation: ${report.summary.violations} out-of-scope change(s).`);
  } catch (error) { vscode.window.showErrorMessage(error.message); }
}

async function autoClose(event) {
  if (autoClosing || event.document.languageId !== "separan" || !vscode.workspace.getConfiguration("separan").get("autoCloseLabels", true)) return;
  if (event.contentChanges.length !== 1 || !/^\r?\n[ \t]*$/u.test(event.contentChanges[0].text)) return;
  const editor = currentEditor(); if (!editor || editor.document !== event.document) return;
  const lineNumber = Math.max(0, editor.selection.active.line - 1); const text = codeText(event.document.lineAt(lineNumber).text);
  const match = /^\s*(SEP|if|while|for|object|list|try|error|transaction|http_route)\b.*?:([^\s:()]+)\s*(?:\([^)]*\))?\s*$/u.exec(text);
  if (!match || !blockPairs[match[1]]) return;
  const closer = `${blockPairs[match[1]]}:${match[2]}`;
  if (event.document.lineAt(editor.selection.active.line).text.trim() === closer) return;
  const indent = text.match(/^\s*/)[0]; const insertion = editor.selection.active; autoClosing = true;
  try {
    await editor.edit((builder) => builder.insert(insertion, `\n${indent}${closer}`));
    editor.selection = new vscode.Selection(insertion, insertion);
  } finally { autoClosing = false; }
}

function activate(context) {
  reviewOutput = vscode.window.createOutputChannel("Separan Review");
  runtimeOutput = vscode.window.createOutputChannel("Separan Runtime");
  structureDiagnostics = vscode.languages.createDiagnosticCollection("separan-structure");
  nativeDiagnostics = vscode.languages.createDiagnosticCollection("separan-native");
  analysisDiagnostics = vscode.languages.createDiagnosticCollection("separan-analysis");
  runStatus = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 90);
  runStatus.text = "$(play) Separan"; runStatus.tooltip = "Run the active Separan file"; runStatus.command = "separan.runFile";
  checkStatus = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 89);
  checkStatus.text = "$(check) Check"; checkStatus.tooltip = "Check the active Separan file"; checkStatus.command = "separan.checkFile";
  const updateStatus = () => {
    const visible = Boolean(currentEditor());
    if (visible) { runStatus.show(); checkStatus.show(); } else { runStatus.hide(); checkStatus.hide(); }
  };
  updateStatus();
  if (currentEditor()) refreshDiagnostics(currentEditor().document, !currentEditor().document.isDirty);
  const structureProvider = new StructureProvider();
  const semanticTagProvider = new SemanticTagProvider();
  const selector = { scheme: "file", language: "separan" };
  const structureView = vscode.window.createTreeView("separan.structureExplorer", { treeDataProvider: structureProvider, showCollapseAll: true });
  const semanticTagView = vscode.window.createTreeView("separan.semanticTags", { treeDataProvider: semanticTagProvider, showCollapseAll: true });
  const refreshStructureSoon = (event) => {
    if (event && event.document && event.document.languageId !== "separan") return;
    clearTimeout(structureRefreshTimer); structureRefreshTimer = setTimeout(() => structureProvider.refresh(), 250);
  };
  context.subscriptions.push(
    vscode.commands.registerCommand("separan.runFile", runFile),
    vscode.commands.registerCommand("separan.checkFile", checkFile),
    vscode.commands.registerCommand("separan.diagnoseRuntime", diagnoseRuntime),
    vscode.commands.registerCommand("separan.goToMatchingLabel", goToMatchingLabel),
    vscode.commands.registerCommand("separan.goToLabel", goToLabel),
    vscode.commands.registerCommand("separan.copyAiEditScope", copyAiScope),
    vscode.commands.registerCommand("separan.showStructuralDiff", showStructuralDiff),
    vscode.commands.registerCommand("separan.verifyAiEditScope", verifyAiEditScope),
    vscode.commands.registerCommand("separan.refreshStructureExplorer", () => structureProvider.refresh()),
    vscode.commands.registerCommand("separan.revealStructure", revealStructure),
    vscode.commands.registerCommand("separan.revealLocation", revealLocation),
    vscode.commands.registerCommand("separan.renameSemanticTag", renameSemanticTag),
    vscode.commands.registerCommand("separan.refreshSemanticTags", () => semanticTagProvider.refresh()),
    vscode.commands.registerCommand("separan.runFunction", runFunction),
    vscode.commands.registerCommand("separan.runTests", runTests),
    vscode.languages.registerCompletionItemProvider(selector, new SeparanCompletionProvider(), ":", ".", "\""),
    vscode.languages.registerSignatureHelpProvider(selector, new SeparanSignatureHelpProvider(), "(", ","),
    vscode.languages.registerHoverProvider(selector, new SeparanHoverProvider()),
    vscode.languages.registerDefinitionProvider(selector, new SeparanDefinitionProvider()),
    vscode.languages.registerReferenceProvider(selector, new SeparanReferenceProvider()),
    vscode.languages.registerRenameProvider(selector, new SeparanRenameProvider()),
    vscode.languages.registerDocumentSymbolProvider(selector, new SeparanDocumentSymbolProvider()),
    vscode.languages.registerDocumentFormattingEditProvider(selector, new SeparanFormattingProvider()),
    vscode.languages.registerCodeActionsProvider(selector, new SeparanCodeActionProvider(), { providedCodeActionKinds: SeparanCodeActionProvider.providedCodeActionKinds }),
    vscode.languages.registerWorkspaceSymbolProvider(new SeparanWorkspaceSymbolProvider()),
    vscode.languages.registerInlayHintsProvider(selector, new SeparanInlayHintsProvider()),
    vscode.languages.registerCallHierarchyProvider(selector, new SeparanCallHierarchyProvider()),
    vscode.languages.registerCodeLensProvider(selector, new SeparanCodeLensProvider()),
    reviewOutput,
    runtimeOutput,
    structureDiagnostics,
    nativeDiagnostics,
    analysisDiagnostics,
    runStatus,
    checkStatus,
    structureView,
    semanticTagView,
    vscode.workspace.onDidChangeTextDocument(autoClose),
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.document.languageId !== "separan") return;
      clearTimeout(diagnosticTimer);
      diagnosticTimer = setTimeout(() => refreshDiagnostics(event.document, false), 150);
    }),
    vscode.workspace.onDidChangeTextDocument(refreshStructureSoon),
    vscode.workspace.onWillRenameFiles((event) => {
      event.waitUntil(importRenameEdit(event.files));
    }),
    vscode.workspace.onDidSaveTextDocument((document) => { if (document.languageId === "separan") { structureProvider.refresh(); semanticTagProvider.refresh(); refreshDiagnostics(document, true); } }),
    vscode.workspace.onDidCloseTextDocument((document) => { structureDiagnostics.delete(document.uri); nativeDiagnostics.delete(document.uri); analysisDiagnostics.delete(document.uri); diagnosticVersions.delete(document.uri.toString()); }),
    vscode.window.onDidChangeActiveTextEditor((editor) => { structureProvider.refresh(); updateStatus(); if (editor) refreshDiagnostics(editor.document, !editor.document.isDirty); }),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (!event.affectsConfiguration("separan.executablePath") && !event.affectsConfiguration("separan.runtimeArguments") && !event.affectsConfiguration("separan.environment")) return;
      for (const document of vscode.workspace.textDocuments) refreshDiagnostics(document, !document.isDirty);
    }),
    vscode.tasks.onDidEndTaskProcess(async (event) => {
      const temporary = temporaryRuns.get(event.execution); if (!temporary) return;
      temporaryRuns.delete(event.execution); await fs.promises.rm(temporary, { force: true });
    }),
    vscode.window.onDidChangeTextEditorSelection(async (event) => {
      if (event.textEditor.document.languageId !== "separan" || !structureView.visible) return;
      const node = await structureProvider.activeNode(event.selections[0].active.line);
      if (node) structureView.reveal(node, { select: true, focus: false, expand: true });
    }),
  );
}

function deactivate() {
  for (const temporary of temporaryRuns.values()) { try { fs.rmSync(temporary, { force: true }); } catch (_) { /* Best-effort cleanup during shutdown. */ } }
  temporaryRuns.clear();
}
module.exports = { activate, deactivate };
