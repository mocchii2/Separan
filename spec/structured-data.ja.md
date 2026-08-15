# YAML／XML構造化データ

状態: **v0.2.0-alpha.5で実験的previewを実装済み。**

YAMLはデータ変換API、XMLは文書構造APIです。XMLを無理に通常objectへ潰さず、用途を
分離します。

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

実装済み関数:

- `yaml_to_object(text)`／`object_to_yaml(value[, indent, sort_keys])`
- `yaml_file_to_object(path)`／`object_to_yaml_file(path, value[, options])`
- `yaml_to_objects(text)`／`objects_to_yaml(values[, options])`
- `yaml_file_to_objects(path)`／`objects_to_yaml_file(path, values[, options])`
- `yaml_validate(text)`／`yaml_validate_file(path)`

変換方向を読めるよう関数名には`object`を使いますが、document rootにはscalarとlistも
利用できます。空入力は`null`、空streamは`[]`です。単一document APIは複数documentを
拒否し、複数documentの戻り値もSeparanの同型list規則を維持します。

型対応は、YAML null→null、boolean→boolean、integer／float→number、text→string、
sequence→同型list、mapping→宣言順を保持するobjectです。mapping keyはstring限定です。
重複key、未対応tag、非有限数、混在list、再帰alias、過大な深さ・node数はerrorです。

scalar解決は曖昧さを避けたYAML 1.2 core寄りのsubsetです。booleanは`true`／`false`だけ。
`yes`、`no`、`on`、`off`はstringです。`012`は10進の12で、2／8／16進数は`0b`、`0o`、
`0x`を必須にします。timestampは、明示的なSeparan datetime変換を呼ぶまでstringです。

loaderは安全な標準YAML tagだけを受け付け、任意Python objectを生成しません。`indent`は
2..8、`sort_keys`はdefault falseで、object宣言順を保持します。コメント、空行、scalar
style、anchor、aliasの完全往復は保証しません。将来のround-trip document APIへ分離します。
CloudFormation固有tagもgeneric YAMLへ混ぜず、別adapterの責務とします。

## XML

```separan
document = xml_document_read("config.xml")
root = xml_root(document)
server = xml_find(document, "/config/servers/server")
print xml_get_attribute(server, "enabled")
xml_set_element_text(xml_child(server, "name"), "WEB01")
xml_document_write("generated.xml", document, indent = 2)
```

document model関数:

- `xml_document_parse`、`xml_document_read`、`xml_document_to_text`、`xml_document_write`
- `xml_create_element`、`xml_root`
- `xml_element_name`、`xml_element_text`、`xml_set_element_text`
- `xml_get_attribute`、`xml_set_attribute`、`xml_remove_attribute`
- `xml_children`、`xml_child`、`xml_add_child`、`xml_remove_child`
- `xml_find`、`xml_find_all`
- `xml_namespace_uri`、`xml_namespace_prefix`
- `xml_escape_text`、`xml_escape_attribute`、`xml_unescape`

検索pathは、local nameと`*`を`/`で区切る小さなdirect-child pathです。絶対pathは
`xml_document`だけで使えます。XPath predicate、子孫`//`、親移動、関数は受け付けません。

attribute関数は明示的な`namespace_uri` optionを受け付けます。prefixをattribute名stringへ
暗黙に埋め込みません。

簡易変換`xml_to_object`、`object_to_xml`、`xml_file_to_object`、
`object_to_xml_file`は、次の明示node形を使います。

```text
name: string
namespace_uri: string | null
attributes: object<string,string>
text: string
children: list<object>
```

attributeをchild fieldへ暗黙展開しません。mixed contentのtail、comment、processing
instruction、namespace prefixの綴りはobject変換の保持対象外です。document modelはtree意味、
comment、mixed content、attribute順を保持しますが、serializerはnamespace prefixの綴りや
意味を持たないformatを正規化する場合があります。source byteの完全一致ではなくXML構造の
保持が重要な場合に使用します。

出力はUTF-8で、textとattributeを自動escapeします。XML宣言はdefaultで有効、`indent`は
0..8です。DTDとentity宣言はparse前に拒否し、external entity、network entity、DTD
loadingを有効化するoptionは提供しません。byte数、深さ、node数にも上限があります。

YAML診断は`E940`～`E949`、XML診断は`E950`～`E959`です。それぞれ`yaml_error`と
`xml_error`でcatchできます。
