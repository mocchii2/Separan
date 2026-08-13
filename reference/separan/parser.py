from dataclasses import dataclass

from .ast_nodes import *
from .errors import error
from .token import Token, TokenType as T


@dataclass
class OpenBlock:
    kind: str
    label: str
    position: object


class Parser:
    CLOSERS = {T.ENDIF: "if", T.ENDWHILE: "while", T.ENDFOR: "for", T.END_FUNCTION: "function", T.END_OBJECT: "object", T.END_LIST: "list", T.ENDTRY: "try", T.END_ERROR: "error", T.END_HTTP_ROUTE: "http_route", T.END_TRANSACTION: "transaction"}
    ASSIGNMENTS = {
        T.EQUAL: None, T.PLUS_EQUAL: "+", T.MINUS_EQUAL: "-", T.STAR_EQUAL: "*",
        T.SLASH_EQUAL: "/", T.FLOOR_DIV_EQUAL: "//", T.PERCENT_EQUAL: "%",
        T.POWER_EQUAL: "**",
    }

    def __init__(self, tokens: list[Token]):
        self.tokens, self.current, self.stack = tokens, 0, []

    def parse(self) -> Program:
        self._newlines(); statements = []; seen_executable = False
        while not self._at(T.EOF):
            if self._peek().type in self.CLOSERS:
                self._unexpected_or_nesting(self._peek())
            stmt = self._statement(top_level=True)
            if isinstance(stmt, ImportStmt) and seen_executable:
                raise error("E702", "Late import", "Imports must appear before other top-level declarations and statements.", stmt.position)
            if not isinstance(stmt, ImportStmt): seen_executable = True
            statements.append(stmt); self._newlines()
        return Program(self._peek().position, statements)

    def _statement(self, top_level=False):
        token = self._peek()
        if token.type == T.IMPORT:
            if not top_level: raise error("E703", "Nested import", "Imports are allowed only at top level.", token.position)
            return self._import()
        if token.type == T.ERROR:
            if not top_level: raise error("E120", "Nested error declaration", "Custom errors may only be declared at top level.", token.position)
            return self._error_declaration()
        if token.type == T.HTTP_ROUTE:
            if not top_level: raise error("E890", "Nested HTTP route", "HTTP routes may only be declared at top level.", token.position)
            return self._http_route()
        if token.type == T.FUNCTION:
            if not top_level:
                raise error("E110", "Invalid nested function", "Functions may only be defined at top level in v0.1.", token.position, actual=token.lexeme)
            return self._function()
        if token.type == T.OBJECT: return self._object()
        if token.type == T.LIST: return self._block_list()
        if token.type == T.TRY:
            if top_level: self._top_error(token)
            return self._try()
        if token.type == T.TRANSACTION:
            if top_level: self._top_error(token)
            return self._transaction()
        if token.type == T.THROW:
            if top_level: self._top_error(token)
            self._advance(); value = self._expression(); self._line_end(); return ThrowStmt(token.position, value)
        if token.type == T.IF:
            if top_level: self._top_error(token)
            return self._if()
        if token.type == T.WHILE:
            if top_level: self._top_error(token)
            return self._while()
        if token.type == T.FOR:
            if top_level: self._top_error(token)
            return self._for()
        if token.type == T.PRINT:
            self._advance(); value = self._expression(); self._line_end(); return PrintStmt(token.position, value)
        if token.type == T.PRINT_ERROR:
            self._advance(); value = self._expression(); self._line_end(); return PrintErrorStmt(token.position, value)
        if token.type == T.RETURN:
            if top_level: self._top_error(token)
            self._advance(); value = None if self._at(T.NEWLINE, T.EOF) else self._expression(); self._line_end(); return ReturnStmt(token.position, value)
        if token.type == T.CONST:
            self._advance()
            name = self._binding(self._consume(T.IDENTIFIER, "Expected constant name after 'const'."))
            self._consume(T.EQUAL, "Expected '=' after constant name.")
            value = self._expression(); self._line_end(); return ConstDeclaration(token.position, name.lexeme, value)
        if token.type == T.IDENTIFIER and self._peek(1).type in self.ASSIGNMENTS:
            name = self._binding(self._advance()); assignment = self._advance(); value = self._expression(); self._line_end()
            operator = self.ASSIGNMENTS[assignment.type]
            if operator is not None: value = BinaryExpr(assignment.position, VariableExpr(name.position, name.lexeme), operator, value)
            return Assignment(name.position, name.lexeme, value)
        if token.type == T.IDENTIFIER and self._peek(1).type == T.DOT and self._peek(2).type == T.IDENTIFIER and self._peek(3).type == T.EQUAL:
            raise error("E214", "Immutable member", f"Cannot assign to read-only member '{token.lexeme}.{self._peek(2).lexeme}'.", token.position, actual=f"{token.lexeme}.{self._peek(2).lexeme}")
        if top_level and token.type == T.IDENTIFIER and token.lexeme in ("http_host", "http_static"):
            expr = self._expression(); self._line_end(); return ExpressionStmt(token.position, expr)
        if top_level:
            self._top_error(token)
        expr = self._expression(); self._line_end(); return ExpressionStmt(token.position, expr)

    def _function(self):
        start = self._advance(); self._consume(T.COLON, "Expected ':' after function.")
        name = self._binding(self._consume(T.IDENTIFIER, "Expected function name."))
        params = []
        if self._match(T.LPAREN):
            if not self._at(T.RPAREN):
                while True:
                    parameter = self._binding(self._consume(T.IDENTIFIER, "Expected parameter name."))
                    if parameter.lexeme in params:
                        raise error("E112", "Duplicate parameter", f"Parameter '{parameter.lexeme}' is already defined.", parameter.position, actual=parameter.lexeme)
                    params.append(parameter.lexeme)
                    if not self._match(T.COMMA): break
            self._consume(T.RPAREN, "Expected ')' after parameters.")
        self._line_end(); self._push("function", name)
        body = self._body_until({T.END_FUNCTION})
        self._close(T.END_FUNCTION, "function")
        return FunctionDecl(start.position, name.lexeme, params, body, name.position)

    def _import(self):
        start = self._advance(); path = self._consume(T.STRING, "Expected quoted .sep path after import.")
        self._consume(T.AS, "Expected 'as' after import path."); alias = self._binding(self._consume(T.IDENTIFIER, "Expected import alias."))
        self._line_end(); return ImportStmt(start.position, path.literal, alias.lexeme)

    def _error_declaration(self):
        start = self._advance(); self._consume(T.COLON, "Expected ':' after error.")
        name = self._consume(T.IDENTIFIER, "Expected custom error name.")
        if not name.lexeme.endswith("_error"): raise error("E121", "Invalid error name", "Custom error names must end with '_error'.", name.position, actual=name.lexeme)
        self._line_end(); self._push("error", name); self._newlines(); self._close(T.END_ERROR, "error")
        return ErrorDecl(start.position, name.lexeme, name.position)

    def _http_route(self):
        start = self._advance(); method = self._consume(T.IDENTIFIER, "Expected HTTP method after http_route.")
        if method.lexeme not in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"): raise error("E891", "Invalid route method", "Route method must be an uppercase supported HTTP method.", method.position, actual=method.lexeme)
        path = self._consume(T.STRING, "Expected route path string.")
        if not path.literal.startswith("/") or "?" in path.literal or "#" in path.literal: raise error("E892", "Invalid route path", "Route path must start with '/' and exclude query/fragment.", path.position, actual=path.literal)
        label = self._opening_label("http_route"); body = self._body_until({T.END_HTTP_ROUTE}); self._close(T.END_HTTP_ROUTE, "http_route")
        return HttpRouteDecl(start.position, method.lexeme, path.literal, label.lexeme, body, label.position)

    def _object(self):
        start = self._advance(); self._consume(T.COLON, "Expected ':' after object.")
        name = self._binding(self._consume(T.IDENTIFIER, "Expected object name.")); self._line_end(); self._push("object", name)
        self._newlines(); entries, names = [], set()
        while not self._at(T.END_OBJECT, T.EOF):
            token = self._peek()
            if token.type in self.CLOSERS: self._unexpected_or_nesting(token)
            if token.type in (T.OBJECT, T.LIST):
                entry = self._object() if token.type == T.OBJECT else self._block_list()
            elif token.type == T.IDENTIFIER and self._peek(1).type == T.EQUAL:
                field = self._advance(); self._advance(); value = self._expression(); self._line_end()
                entry = ObjectField(field.position, field.lexeme, value)
            else:
                raise error("E115", "Invalid object entry", "An object contains field assignments or nested object/list blocks.", token.position, actual=token.lexeme)
            if entry.name in names:
                raise error("E116", "Duplicate object field", f"Field '{entry.name}' is already defined in object :{name.lexeme}.", entry.position, actual=entry.name)
            names.add(entry.name); entries.append(entry); self._newlines()
        if self._at(T.EOF): self._body_until({T.END_OBJECT})
        self._close(T.END_OBJECT, "object")
        return ObjectBlock(start.position, name.lexeme, entries, name.position)

    def _block_list(self):
        start = self._advance(); self._consume(T.COLON, "Expected ':' after list.")
        name = self._binding(self._consume(T.IDENTIFIER, "Expected list name.")); self._line_end(); self._push("list", name)
        self._newlines(); elements = []
        while not self._at(T.END_LIST, T.EOF):
            if self._peek().type in self.CLOSERS: self._unexpected_or_nesting(self._peek())
            elements.append(self._expression()); self._line_end(); self._newlines()
        if self._at(T.EOF): self._body_until({T.END_LIST})
        self._close(T.END_LIST, "list")
        return ListBlock(start.position, name.lexeme, elements, name.position)

    def _try(self):
        start = self._advance(); label = self._opening_label("try")
        body = self._body_until({T.CATCH, T.FINALLY, T.ENDTRY}); catches, seen = [], set(); finally_body = None
        while self._match(T.CATCH):
            catch = self._previous(); category = self._consume(T.IDENTIFIER, "Expected error category after catch.")
            if category.lexeme in seen: raise error("E117", "Duplicate catch", f"Error category '{category.lexeme}' is already caught.", category.position, actual=category.lexeme)
            if "any" in seen: raise error("E118", "Catch after any", "catch any must be the final catch branch.", category.position, actual=category.lexeme)
            seen.add(category.lexeme); self._branch_label(label, "catch")
            catches.append(CatchBranch(catch.position, category.lexeme, self._body_until({T.CATCH, T.FINALLY, T.ENDTRY})))
        if self._match(T.FINALLY):
            self._branch_label(label, "finally"); finally_body = self._body_until({T.ENDTRY})
        self._close(T.ENDTRY, "try")
        if not catches and finally_body is None: raise error("E119", "Empty try handler", "A try block requires at least one catch or finally branch.", start.position)
        return TryStmt(start.position, label.lexeme, body, catches, finally_body, label.position)

    def _transaction(self):
        start = self._advance(); connection = self._expression(); label = self._opening_label("transaction")
        body = self._body_until({T.END_TRANSACTION}); self._close(T.END_TRANSACTION, "transaction")
        return TransactionStmt(start.position, connection, label.lexeme, body, label.position)

    def _if(self):
        start = self._advance(); condition = self._expression(); label = self._opening_label("if")
        branches = [IfBranch(condition, [], start.position)]; else_body = None
        while True:
            branches[-1].body = self._body_until({T.ELSEIF, T.ELSE, T.ENDIF})
            if self._match(T.ELSEIF):
                elseif_token = self._previous()
                cond = self._expression(); self._branch_label(label, "elseif")
                branches.append(IfBranch(cond, [], elseif_token.position)); continue
            if self._match(T.ELSE):
                self._branch_label(label, "else")
                else_body = self._body_until({T.ELSEIF, T.ELSE, T.ENDIF})
                if self._at(T.ELSEIF, T.ELSE):
                    t = self._peek(); raise error("E108", "Invalid if branch", "else must be the final branch and may occur only once.", t.position, actual=t.lexeme)
            break
        self._close(T.ENDIF, "if")
        return IfStmt(start.position, label.lexeme, branches, else_body, label.position)

    def _while(self):
        start = self._advance(); condition = self._expression(); label = self._opening_label("while")
        body = self._body_until({T.ENDWHILE}); self._close(T.ENDWHILE, "while")
        return WhileStmt(start.position, label.lexeme, condition, body, label.position)

    def _for(self):
        start = self._advance(); var = self._binding(self._consume(T.IDENTIFIER, "Expected loop variable."))
        self._consume(T.IN, "Expected 'in' after loop variable."); iterable = self._expression()
        label = self._opening_label("for"); body = self._body_until({T.ENDFOR}); self._close(T.ENDFOR, "for")
        return ForStmt(start.position, label.lexeme, var.lexeme, iterable, body, label.position)

    def _body_until(self, endings):
        self._newlines(); body = []
        while not self._at(*endings, T.EOF):
            if self._peek().type in self.CLOSERS: self._unexpected_or_nesting(self._peek())
            body.append(self._statement()); self._newlines()
        if self._at(T.EOF):
            opened = self.stack[-1]
            raise error("E106", "Unclosed block", f"The {opened.kind} :{opened.label} block reaches the end of file.", opened.position, expected=self._closer_text(opened.kind, opened.label), related=opened.position)
        return body

    def _opening_label(self, kind):
        colon = self._consume(T.COLON, f"Expected :label after {kind} expression.")
        label = self._consume(T.IDENTIFIER, "Expected block label after ':'.")
        self._line_end(); self._push(kind, label); return label

    @staticmethod
    def _binding(token):
        if token.lexeme == "system":
            raise error("E215", "Reserved system name", "Name 'system' is reserved for the read-only execution context.", token.position, actual=token.lexeme)
        return token

    def _push(self, kind, label):
        for opened in self.stack:
            if opened.label == label.lexeme:
                raise error("E109", "Duplicate open label", f":{label.lexeme} is already used by an open block.", label.position, actual=label.lexeme, related=opened.position)
        self.stack.append(OpenBlock(kind, label.lexeme, label.position))

    def _branch_label(self, label, branch):
        self._consume(T.COLON, f"Expected ':' after {branch}.")
        actual = self._consume(T.IDENTIFIER, f"Expected label after {branch}.")
        if actual.lexeme != label.lexeme: self._mismatch(actual, label.lexeme, branch)
        self._line_end()

    def _close(self, token_type, kind):
        closer = self._consume(token_type, f"Expected closing {kind}.")
        self._consume(T.COLON, "Expected ':' in block closer.")
        label = self._consume(T.IDENTIFIER, "Expected closing block label.")
        opened = self.stack[-1]
        if label.lexeme != opened.label:
            lower = next((b for b in reversed(self.stack[:-1]) if b.kind == kind and b.label == label.lexeme), None)
            if lower:
                raise error("E105", "Block nesting error", f"Cannot close {kind} :{label.lexeme} because {opened.kind} :{opened.label} is still open.", closer.position, expected=self._closer_text(opened.kind, opened.label), actual=f"{closer.lexeme}:{label.lexeme}", related=opened.position)
            self._mismatch(label, opened.label, closer.lexeme, opened.position)
        self._line_end(); self.stack.pop()

    def _unexpected_or_nesting(self, closer):
        kind = self.CLOSERS[closer.type]
        label = self._closer_label()
        if self.stack and self.stack[-1].label == label and self.stack[-1].kind != kind:
            opened = self.stack[-1]
            raise error("E105", "Block kind mismatch", f"The label matches the open {opened.kind} block, but '{closer.lexeme}' closes {kind}.", closer.position, expected=self._closer_text(opened.kind, opened.label), actual=f"{closer.lexeme}:{label}", related=opened.position)
        match = next((b for b in reversed(self.stack) if b.kind == kind and b.label == label), None)
        if match:
            opened = self.stack[-1]
            raise error("E105", "Block nesting error", f"Cannot close {kind} :{label} because {opened.kind} :{opened.label} is still open.", closer.position, expected=self._closer_text(opened.kind, opened.label), actual=f"{closer.lexeme}:{label}", related=opened.position)
        raise error("E107", "Unexpected block closer", f"No open {kind} :{label} block exists.", closer.position, actual=f"{closer.lexeme}:{label}")

    def _closer_label(self):
        i = self.current + 1
        if self.tokens[i].type == T.COLON and self.tokens[i+1].type == T.IDENTIFIER: return self.tokens[i+1].lexeme
        return "<missing>"

    def _mismatch(self, token, expected, prefix, related=None):
        raise error("E104", "Block label mismatch", "The closing or branch label must match its opening block.", token.position, expected=f"{prefix}:{expected}", actual=f"{prefix}:{token.lexeme}", related=related or self.stack[-1].position)

    @staticmethod
    def _closer_text(kind, label):
        return f"{'end_function' if kind == 'function' else 'endif' if kind == 'if' else 'end_' + kind if kind in ('object', 'list', 'error', 'http_route', 'transaction') else 'end' + kind}:{label}"

    def _top_error(self, token):
        raise error("E110", "Invalid top-level statement", "Only function definitions, data blocks, const declarations, assignments, and print are allowed at top level.", token.position, actual=token.lexeme)

    def _expression(self): return self._coalesce()
    def _coalesce(self):
        expr = self._or()
        if self._match(T.NULL_COALESCE):
            operator = self._previous(); expr = BinaryExpr(operator.position, expr, operator.lexeme, self._coalesce())
        return expr
    def _or(self): return self._binary(self._and, {T.OR})
    def _and(self): return self._binary(self._equality, {T.AND})
    def _equality(self):
        expr = self._comparison()
        if self._at(T.EQUAL_EQUAL, T.BANG_EQUAL):
            operator = self._advance()
            if isinstance(expr, BinaryExpr) and expr.operator in {">", "<", ">=", "<=", "==", "!=", "in", "not in"}:
                self._chained(operator)
            right = self._comparison()
            if isinstance(right, BinaryExpr) and right.operator in {">", "<", ">=", "<=", "in", "not in"}:
                self._chained(operator)
            expr = BinaryExpr(operator.position, expr, operator.lexeme, right)
        if self._at(T.EQUAL_EQUAL, T.BANG_EQUAL, T.GREATER, T.GREATER_EQUAL, T.LESS, T.LESS_EQUAL):
            self._chained(self._peek())
        return expr
    def _comparison(self):
        expr = self._term()
        if self._at(T.GREATER, T.GREATER_EQUAL, T.LESS, T.LESS_EQUAL, T.IN) or (self._at(T.NOT) and self._peek(1).type == T.IN):
            operator = self._advance()
            lexeme = operator.lexeme
            if operator.type == T.NOT:
                self._advance(); lexeme = "not in"
            expr = BinaryExpr(operator.position, expr, lexeme, self._term())
        if self._at(T.GREATER, T.GREATER_EQUAL, T.LESS, T.LESS_EQUAL, T.IN) or (self._at(T.NOT) and self._peek(1).type == T.IN):
            self._chained(self._peek())
        return expr
    @staticmethod
    def _chained(token):
        raise error("E111", "Chained comparison", "Comparison operators cannot be chained. Use && explicitly.", token.position, actual=token.lexeme)
    def _term(self): return self._binary(self._factor, {T.PLUS, T.MINUS})
    def _factor(self): return self._binary(self._unary, {T.STAR, T.SLASH, T.FLOOR_DIV, T.PERCENT})
    def _binary(self, sub, types, once=False):
        expr = sub()
        while self._peek().type in types:
            op = self._advance(); right = sub(); expr = BinaryExpr(op.position, expr, op.lexeme, right)
            if once: break
        return expr
    def _unary(self):
        if self._match(T.BANG, T.NOT, T.MINUS):
            op = self._previous(); return UnaryExpr(op.position, op.lexeme, self._unary())
        return self._power()
    def _power(self):
        expr = self._postfix()
        if self._match(T.POWER):
            op = self._previous(); expr = BinaryExpr(op.position, expr, op.lexeme, self._unary())
        return expr
    def _postfix(self):
        expr = self._primary()
        while self._at(T.LBRACKET, T.DOT):
            if self._match(T.LBRACKET):
                pos = self._previous().position; index = self._expression(); self._consume(T.RBRACKET, "Expected ']' after index."); expr = IndexExpr(pos, expr, index)
            else:
                pos = self._advance().position; name = self._consume(T.IDENTIFIER, "Expected member name after '.'.")
                if self._match(T.LPAREN):
                    args, named = self._call_arguments(); expr = MemberCallExpr(pos, expr, name.lexeme, args, named)
                else: expr = MemberExpr(pos, expr, name.lexeme)
        return expr

    def _call_arguments(self):
        args, named = [], {}
        if not self._at(T.RPAREN):
            while True:
                if self._at(T.IDENTIFIER) and self._peek(1).type == T.EQUAL:
                    name = self._advance(); self._advance()
                    if name.lexeme in named: raise error("E113", "Duplicate named argument", f"Named argument '{name.lexeme}' is already specified.", name.position, actual=name.lexeme)
                    named[name.lexeme] = self._expression()
                else:
                    if named:
                        token = self._peek(); raise error("E114", "Positional argument after named argument", "Positional arguments must appear before named arguments.", token.position, actual=token.lexeme)
                    args.append(self._expression())
                if not self._match(T.COMMA): break
        self._consume(T.RPAREN, "Expected ')' after arguments."); return args, named
    def _primary(self):
        if self._match(T.NUMBER, T.STRING, T.TRUE, T.FALSE):
            t = self._previous(); return LiteralExpr(t.position, t.literal)
        if self._match(T.NULL):
            t = self._previous(); return LiteralExpr(t.position, None)
        if self._match(T.LBRACKET):
            t = self._previous(); values = []
            if not self._at(T.RBRACKET):
                while True:
                    values.append(self._expression())
                    if not self._match(T.COMMA): break
            self._consume(T.RBRACKET, "Expected ']' after list."); return ListExpr(t.position, values)
        if self._match(T.IDENTIFIER):
            t = self._previous()
            if self._match(T.LPAREN):
                args, named = self._call_arguments(); return CallExpr(t.position, t.lexeme, args, named)
            return VariableExpr(t.position, t.lexeme)
        if self._match(T.LPAREN):
            opening = self._previous()
            expr = self._expression(); self._consume(T.RPAREN, "Expected ')' after expression."); return GroupExpr(opening.position, expr)
        t = self._peek(); raise error("E100", "Expected expression", "A value or expression is required here.", t.position, actual=t.lexeme)

    def _line_end(self):
        if not self._at(T.NEWLINE, T.EOF):
            t = self._peek(); raise error("E100", "Unexpected token", "Statements must end at the end of the line.", t.position, actual=t.lexeme)
        self._match(T.NEWLINE)
    def _newlines(self):
        while self._match(T.NEWLINE): pass
    def _consume(self, kind, message):
        if self._at(kind): return self._advance()
        t = self._peek(); raise error("E100", "Syntax error", message, t.position, actual=t.lexeme)
    def _match(self, *types):
        if self._at(*types): self._advance(); return True
        return False
    def _at(self, *types): return self._peek().type in types
    def _peek(self, offset=0): return self.tokens[min(self.current + offset, len(self.tokens)-1)]
    def _advance(self):
        token = self._peek(); self.current += 1; return token
    def _previous(self): return self.tokens[self.current-1]
