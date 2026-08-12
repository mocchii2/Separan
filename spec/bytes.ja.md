# bytes — 不変binary型

状態: **実験的プレビュー実装あり。**

`bytes`はstringや`list<number>`とは別の不変型です。file、HTTP、process、secure randomの
binary値はすべて同じbytes型を使います。暗黙のtext変換はありません。

```separan
data = bytes_from_hex("89504E470D0A1A0A")
text = string_from_bytes(data, encoding = "utf-8")
encoded = base64_encode(data)
```

初期API:

- `bytes_from_string(value, encoding = "utf-8")`
- `string_from_bytes(value, encoding = "utf-8")`
- `bytes_get(value, index)` → `0..255`のnumber
- `slice_bytes(value, start, end)`
- `bytes_concat(left, right)`
- `hex_encode(value)`／`hex_decode(value)`／`bytes_from_hex(value)`
- `base64_encode(value)`／`base64_decode(value)`
- `length(value)`／`is_empty(value)`
- `bytes + bytes`

encodingは`utf-8`、`utf-16le`、`utf-16be`、`ascii`だけです。不正text、hex、Base64、
範囲外indexを黙って補正しません。bytes結果は67,108,864 byte以下に制限します。

部分書換えは提供しません。将来必要なら、不変bytesを弱めず別の`byte_buffer`型として
設計します。整数pack/unpackもendianを必須にする別APIとして追加します。
