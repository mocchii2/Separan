import unicodedata

from .errors import error
from .token import SourcePosition, Token, TokenType


KEYWORDS = {
    "function": TokenType.FUNCTION, "end_function": TokenType.END_FUNCTION,
    "if": TokenType.IF, "elseif": TokenType.ELSEIF, "else": TokenType.ELSE,
    "endif": TokenType.ENDIF, "while": TokenType.WHILE,
    "endwhile": TokenType.ENDWHILE, "for": TokenType.FOR, "in": TokenType.IN,
    "endfor": TokenType.ENDFOR, "print": TokenType.PRINT, "return": TokenType.RETURN,
    "print_error": TokenType.PRINT_ERROR,
    "const": TokenType.CONST,
    "not": TokenType.NOT,
    "object": TokenType.OBJECT, "end_object": TokenType.END_OBJECT,
    "list": TokenType.LIST, "end_list": TokenType.END_LIST,
    "import": TokenType.IMPORT, "as": TokenType.AS,
    "try": TokenType.TRY, "catch": TokenType.CATCH, "finally": TokenType.FINALLY,
    "endtry": TokenType.ENDTRY, "throw": TokenType.THROW,
    "error": TokenType.ERROR, "end_error": TokenType.END_ERROR,
    "http_route": TokenType.HTTP_ROUTE, "end_http_route": TokenType.END_HTTP_ROUTE,
    "transaction": TokenType.TRANSACTION, "end_transaction": TokenType.END_TRANSACTION,
    "true": TokenType.TRUE, "false": TokenType.FALSE, "null": TokenType.NULL,
}


class Lexer:
    def __init__(self, source: str, filename: str = "<source>"):
        self.source, self.filename = source, filename

    def scan_tokens(self) -> list[Token]:
        tokens: list[Token] = []
        lines = self.source.splitlines()
        comment_label = None
        comment_open = None
        for line_no, text in enumerate(lines, 1):
            stripped = text.lstrip()
            column_offset = len(text) - len(stripped)
            delimiter = self._comment_delimiter(stripped)
            if delimiter is not None:
                label = delimiter
                pos = SourcePosition(self.filename, line_no, column_offset + 1, text)
                if comment_label is None:
                    comment_label, comment_open = label, pos
                elif label == comment_label:
                    comment_label, comment_open = None, None
                else:
                    raise error("E104", "Multiline comment label mismatch", "Nested comments are not supported and the closing label must match.", pos, expected=f"##{comment_label}", actual=f"##{label}", related=comment_open)
                tokens.append(Token(TokenType.NEWLINE, "\n", None, pos))
                continue
            if comment_label is not None:
                pos = SourcePosition(self.filename, line_no, 1, text)
                tokens.append(Token(TokenType.NEWLINE, "\n", None, pos))
                continue
            self._scan_line(text, line_no, tokens)
            tokens.append(Token(TokenType.NEWLINE, "\n", None, SourcePosition(self.filename, line_no, len(text) + 1, text)))
        if comment_label is not None:
            raise error("E106", "Unclosed comment", f"Multiline comment ##{comment_label} was not closed.", comment_open, expected=f"##{comment_label}")
        eof_line = len(lines) + 1
        tokens.append(Token(TokenType.EOF, "", None, SourcePosition(self.filename, eof_line, 1, "")))
        return tokens

    @staticmethod
    def _valid_name(value):
        return bool(value) and value.isidentifier() and unicodedata.is_normalized("NFC", value)

    @classmethod
    def _comment_delimiter(cls, stripped):
        """Return the exact ## label, or None for an ordinary # line comment."""
        candidate = stripped.rstrip()
        if candidate == "##":
            return ""
        if candidate.startswith("##") and cls._valid_name(candidate[2:]):
            return candidate[2:]
        return None

    @staticmethod
    def _name_start(value):
        return value == "_" or value.isidentifier()

    @staticmethod
    def _name_continue(value):
        return ("_" + value).isidentifier()

    def _scan_line(self, text, line_no, out):
        i = 0
        single = {"+": TokenType.PLUS, "-": TokenType.MINUS, "*": TokenType.STAR,
                  "/": TokenType.SLASH, "%": TokenType.PERCENT, "(": TokenType.LPAREN,
                  ")": TokenType.RPAREN, "[": TokenType.LBRACKET, "]": TokenType.RBRACKET,
                  ",": TokenType.COMMA, ":": TokenType.COLON, ".": TokenType.DOT}
        while i < len(text):
            c = text[i]
            if c in " \t\r": i += 1; continue
            pos = SourcePosition(self.filename, line_no, i + 1, text)
            if c == "#":
                break
            if c == "@":
                start = i; i += 1
                if i >= len(text) or not self._name_start(text[i]):
                    raise error("E216", "Invalid function tag", "Expected an NFC-normalized tag name immediately after '@'.", pos, actual=text[start:i])
                name_start = i
                while i < len(text) and self._name_continue(text[i]): i += 1
                name = text[name_start:i]
                if not self._valid_name(name):
                    raise error("E216", "Invalid function tag", "Function tags must be NFC-normalized identifiers without whitespace.", pos, actual="@" + name)
                out.append(Token(TokenType.TAG, name, name, pos)); continue
            triples = {"//=": TokenType.FLOOR_DIV_EQUAL, "**=": TokenType.POWER_EQUAL}
            triple = text[i:i+3]
            if triple in triples:
                out.append(Token(triples[triple], triple, None, pos)); i += 3; continue
            pairs = {"==": TokenType.EQUAL_EQUAL, "!=": TokenType.BANG_EQUAL,
                     ">=": TokenType.GREATER_EQUAL, "<=": TokenType.LESS_EQUAL,
                     "&&": TokenType.AND, "||": TokenType.OR,
                     "**": TokenType.POWER, "//": TokenType.FLOOR_DIV,
                     "??": TokenType.NULL_COALESCE, "+=": TokenType.PLUS_EQUAL,
                     "-=": TokenType.MINUS_EQUAL, "*=": TokenType.STAR_EQUAL,
                     "/=": TokenType.SLASH_EQUAL, "%=": TokenType.PERCENT_EQUAL}
            pair = text[i:i+2]
            if pair in pairs:
                out.append(Token(pairs[pair], pair, None, pos)); i += 2; continue
            if c in single:
                out.append(Token(single[c], c, None, pos)); i += 1; continue
            singles = {"=": TokenType.EQUAL, "!": TokenType.BANG, ">": TokenType.GREATER, "<": TokenType.LESS}
            if c in singles:
                out.append(Token(singles[c], c, None, pos)); i += 1; continue
            raw = c == "r" and i + 1 < len(text) and text[i + 1] == '"'
            if c == '"' or raw:
                start = i; i += 2 if raw else 1; chars = []
                escapes = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", '"': '"', "\\": "\\"}
                while i < len(text) and text[i] != '"':
                    if text[i] == "\\" and not raw:
                        escape_position = SourcePosition(self.filename, line_no, i + 1, text)
                        i += 1
                        if i >= len(text):
                            raise error("E219", "Unknown escape sequence", "A backslash must be followed by a supported escape.", escape_position, actual="\\")
                        marker = text[i]
                        if marker in ("u", "U"):
                            digits = 4 if marker == "u" else 8
                            value = text[i + 1:i + 1 + digits]
                            actual = "\\" + marker + value
                            if len(value) != digits or any(ch not in "0123456789abcdefABCDEF" for ch in value):
                                raise error("E220", "Invalid Unicode escape", f"\\{marker} must be followed by exactly {digits} hexadecimal digits.", escape_position, actual=actual)
                            codepoint = int(value, 16)
                            if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
                                raise error("E220", "Invalid Unicode escape", "Unicode escapes must identify a valid Unicode scalar value.", escape_position, actual=actual)
                            chars.append(chr(codepoint)); i += digits
                        elif marker in escapes:
                            chars.append(escapes[marker])
                        else:
                            raise error("E219", "Unknown escape sequence", "Unknown escapes are errors; use a raw string when backslashes are literal.", escape_position, actual="\\" + marker)
                    else: chars.append(text[i])
                    i += 1
                if i >= len(text):
                    raise error("E103", "Unterminated string", "Strings must close on the same line.", pos)
                i += 1
                out.append(Token(TokenType.STRING, text[start:i], "".join(chars), pos)); continue
            if c.isdigit():
                start = i
                while i < len(text) and text[i].isdigit(): i += 1
                if i < len(text) and text[i] == ".":
                    i += 1
                    if i >= len(text) or not text[i].isdigit():
                        raise error("E101", "Invalid number", "A decimal point must be followed by digits.", pos)
                    while i < len(text) and text[i].isdigit(): i += 1
                lex = text[start:i]
                out.append(Token(TokenType.NUMBER, lex, float(lex) if "." in lex else int(lex), pos)); continue
            if self._name_start(c):
                start = i
                while i < len(text) and self._name_continue(text[i]): i += 1
                lex = text[start:i]
                if not all(ch.isascii() for ch in lex):
                    follows_colon = bool(out) and out[-1].type == TokenType.COLON
                    if not follows_colon:
                        raise error("E101", "Invalid identifier", "Identifiers must use ASCII letters, digits, and underscores; Unicode is allowed only for labels.", pos, actual=lex)
                    if not self._valid_name(lex):
                        raise error("E102", "Invalid label", "Unicode labels must be valid NFC-normalized identifiers.", pos, actual=lex)
                    out.append(Token(TokenType.LABEL, lex, None, pos)); continue
                kind = KEYWORDS.get(lex, TokenType.IDENTIFIER)
                literal = True if kind == TokenType.TRUE else False if kind == TokenType.FALSE else None
                out.append(Token(kind, lex, literal, pos)); continue
            raise error("E100", "Unexpected character", f"Character {c!r} is not valid Separan syntax.", pos, actual=c)
