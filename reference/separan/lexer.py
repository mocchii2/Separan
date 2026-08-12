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
            if stripped.startswith("::"):
                label = stripped[2:].strip()
                pos = SourcePosition(self.filename, line_no, column_offset + 1, text)
                if not self._valid_name(label):
                    raise error("E102", "Invalid comment label", "A multiline comment needs a valid label.", pos, actual=label)
                if comment_label is None:
                    comment_label, comment_open = label, pos
                elif label == comment_label:
                    comment_label, comment_open = None, None
                else:
                    raise error("E104", "Comment label mismatch", "Nested comments are not supported and the closing label must match.", pos, expected=f"::{comment_label}", actual=f"::{label}", related=comment_open)
                tokens.append(Token(TokenType.NEWLINE, "\n", None, pos))
                continue
            if comment_label is not None or (stripped.startswith(":") and not stripped.startswith("::")):
                pos = SourcePosition(self.filename, line_no, 1, text)
                tokens.append(Token(TokenType.NEWLINE, "\n", None, pos))
                continue
            self._scan_line(text, line_no, tokens)
            tokens.append(Token(TokenType.NEWLINE, "\n", None, SourcePosition(self.filename, line_no, len(text) + 1, text)))
        if comment_label is not None:
            raise error("E106", "Unclosed comment", f"Multiline comment :{comment_label} was not closed.", comment_open, expected=f"::{comment_label}")
        eof_line = len(lines) + 1
        tokens.append(Token(TokenType.EOF, "", None, SourcePosition(self.filename, eof_line, 1, "")))
        return tokens

    @staticmethod
    def _valid_name(value):
        return bool(value) and (value[0].isalpha() and value[0].isascii() or value[0] == "_") and all((c.isalnum() and c.isascii()) or c == "_" for c in value)

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
            if c in single:
                out.append(Token(single[c], c, None, pos)); i += 1; continue
            pairs = {"==": TokenType.EQUAL_EQUAL, "!=": TokenType.BANG_EQUAL,
                     ">=": TokenType.GREATER_EQUAL, "<=": TokenType.LESS_EQUAL,
                     "&&": TokenType.AND, "||": TokenType.OR}
            pair = text[i:i+2]
            if pair in pairs:
                out.append(Token(pairs[pair], pair, None, pos)); i += 2; continue
            singles = {"=": TokenType.EQUAL, "!": TokenType.BANG, ">": TokenType.GREATER, "<": TokenType.LESS}
            if c in singles:
                out.append(Token(singles[c], c, None, pos)); i += 1; continue
            if c == '"':
                start = i; i += 1; chars = []
                escapes = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
                while i < len(text) and text[i] != '"':
                    if text[i] == "\\":
                        i += 1
                        if i >= len(text) or text[i] not in escapes:
                            raise error("E101", "Invalid string escape", 'Supported escapes are \\n, \\r, \\t, \\" and \\\\.', SourcePosition(self.filename, line_no, i + 1, text))
                        chars.append(escapes[text[i]])
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
            if c.isalpha() or c == "_":
                start = i
                while i < len(text) and (text[i].isalnum() or text[i] == "_"): i += 1
                lex = text[start:i]
                if not all(ch.isascii() for ch in lex):
                    raise error("E101", "Invalid identifier", "v0.1 identifiers must use ASCII letters, digits, and underscores.", pos, actual=lex)
                kind = KEYWORDS.get(lex, TokenType.IDENTIFIER)
                literal = True if kind == TokenType.TRUE else False if kind == TokenType.FALSE else None
                out.append(Token(kind, lex, literal, pos)); continue
            raise error("E100", "Unexpected character", f"Character {c!r} is not valid Separan syntax.", pos, actual=c)
