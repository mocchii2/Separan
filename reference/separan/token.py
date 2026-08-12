from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    IDENTIFIER = auto()
    NUMBER = auto()
    STRING = auto()
    TRUE = auto()
    FALSE = auto()
    NULL = auto()
    FUNCTION = auto()
    END_FUNCTION = auto()
    IF = auto()
    ELSEIF = auto()
    ELSE = auto()
    ENDIF = auto()
    WHILE = auto()
    ENDWHILE = auto()
    FOR = auto()
    IN = auto()
    ENDFOR = auto()
    PRINT = auto()
    PRINT_ERROR = auto()
    RETURN = auto()
    CONST = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQUAL = auto()
    EQUAL_EQUAL = auto()
    BANG = auto()
    BANG_EQUAL = auto()
    GREATER = auto()
    GREATER_EQUAL = auto()
    LESS = auto()
    LESS_EQUAL = auto()
    AND = auto()
    OR = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    COLON = auto()
    DOT = auto()
    OBJECT = auto()
    END_OBJECT = auto()
    LIST = auto()
    END_LIST = auto()
    IMPORT = auto()
    AS = auto()
    TRY = auto()
    CATCH = auto()
    FINALLY = auto()
    ENDTRY = auto()
    THROW = auto()
    ERROR = auto()
    END_ERROR = auto()
    HTTP_ROUTE = auto()
    END_HTTP_ROUTE = auto()
    TRANSACTION = auto()
    END_TRANSACTION = auto()
    NEWLINE = auto()
    EOF = auto()


@dataclass(frozen=True)
class SourcePosition:
    file: str
    line: int
    column: int
    source_line: str


@dataclass(frozen=True)
class Token:
    type: TokenType
    lexeme: str
    literal: object
    position: SourcePosition
