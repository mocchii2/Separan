#include "separan_runtime.h"
#include "separan_lexer.h"
#include "separan_files.h"

#include <ctype.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef enum { V_EMPTY, V_NUMBER, V_BOOL, V_STRING, V_LIST, V_OBJECT, V_VOID, V_BYTES } ValueKind;
typedef struct Value Value;
struct Value { ValueKind kind; double number; int floating; int boolean; char *string; size_t string_length; Value *items; char **keys; size_t count; };
typedef struct Expr Expr;
typedef struct Stmt Stmt;
typedef struct { Stmt **items; size_t count; } Body;

struct Expr {
    int kind; /* 0 literal, 1 variable, 2 unary, 3 binary, 4 call, 5 list, 6 index, 7 member */
    char *text;
    Value literal;
    Expr *left, *right;
    Expr **args;
    size_t argc;
};

struct Stmt {
    int kind; /* 0 assign, 1 print, 2 return, 3 if, 4 while, 5 function, 6 expr, 7 for, 8 const, 9 object, 10 list block */
    char *name;
    Expr *expr;
    Body body, other;
    char **parameters;
    size_t parameter_count;
};

typedef struct { char *name; Value value; int constant; } Binding;
typedef struct Frame { Binding *bindings; size_t count; struct Frame *parent; } Frame;
typedef struct {
    separan_tokens tokens;
    size_t at;
    int error;
    const char *message;
    FILE *errors;
    Body program;
    Frame global;
    FILE *output;
    int returning;
    Value returned;
    size_t steps;
    separan_files files;
    int read_files, write_files, discover_paths;
} Runtime;

static char *copy_text(const char *text) {
    size_t length = strlen(text);
    char *copy = malloc(length + 1);
    if (copy) memcpy(copy, text, length + 1);
    return copy;
}

static Value empty_value(void) { Value v = {0}; return v; }
static Value number_value(double n) { Value v = {0}; v.kind = V_NUMBER; v.number = n; return v; }
static Value floating_value(double n) { Value v = number_value(n); v.floating = 1; return v; }
static void format_number(char *buffer, size_t size, Value value) {
    snprintf(buffer, size, "%.15g", value.number);
    if (value.floating && isfinite(value.number) && floor(value.number) == value.number) {
        size_t length = strlen(buffer);
        if (length + 2 < size && !strchr(buffer, 'e') && !strchr(buffer, 'E')) strcat(buffer, ".0");
    }
}
static Value bool_value(int b) { Value v = {0}; v.kind = V_BOOL; v.boolean = b; return v; }
static Value string_bytes(const char *s, size_t length) {
    Value v = {0}; v.kind = V_STRING; v.string_length = length;
    v.string = malloc(length + 1);
    if (v.string) { memcpy(v.string, s, length); v.string[length] = 0; }
    return v;
}
static Value string_value(const char *s) { return string_bytes(s, strlen(s)); }
static size_t utf8_length(const char *text, size_t length) {
    size_t count = 0;
    for (size_t i = 0; i < length; i++)
        if (((unsigned char)text[i] & 0xC0) != 0x80) count++;
    return count;
}
static int valid_utf8_bytes(const char *text, size_t length) {
    for (size_t i = 0; i < length;) {
        unsigned char c = (unsigned char)text[i];
        if (c < 0x80) { i++; continue; }
        size_t width = c >= 0xF0 && c <= 0xF4 ? 4 : c >= 0xE0 && c <= 0xEF ? 3 :
                       c >= 0xC2 && c <= 0xDF ? 2 : 0;
        if (!width || i + width > length) return 0;
        unsigned value = c & ((1u << (7 - width)) - 1u);
        for (size_t j = 1; j < width; j++) {
            unsigned char part = (unsigned char)text[i + j];
            if ((part & 0xC0) != 0x80) return 0;
            value = (value << 6) | (part & 0x3F);
        }
        if ((width == 2 && value < 0x80) || (width == 3 && value < 0x800) ||
            (width == 4 && value < 0x10000) || value > 0x10FFFF ||
            (value >= 0xD800 && value <= 0xDFFF)) return 0;
        i += width;
    }
    return 1;
}
static int hex_value(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return c - 'A' + 10;
}
static size_t append_utf8(char *out, unsigned value) {
    if (value < 0x80) { out[0] = (char)value; return 1; }
    if (value < 0x800) { out[0] = (char)(0xC0 | (value >> 6)); out[1] = (char)(0x80 | (value & 0x3F)); return 2; }
    if (value < 0x10000) {
        out[0] = (char)(0xE0 | (value >> 12)); out[1] = (char)(0x80 | ((value >> 6) & 0x3F));
        out[2] = (char)(0x80 | (value & 0x3F)); return 3;
    }
    out[0] = (char)(0xF0 | (value >> 18)); out[1] = (char)(0x80 | ((value >> 12) & 0x3F));
    out[2] = (char)(0x80 | ((value >> 6) & 0x3F)); out[3] = (char)(0x80 | (value & 0x3F));
    return 4;
}
static Value clone_value(Value v) {
    if (v.kind == V_STRING || v.kind == V_BYTES) {
        Value copy = string_bytes(v.string, v.string_length); copy.kind = v.kind; return copy;
    }
    if (v.kind == V_LIST || v.kind == V_OBJECT) {
        Value copy = empty_value(); copy.kind = v.kind; copy.count = v.count;
        copy.items = calloc(v.count ? v.count : 1, sizeof(*copy.items));
        if (copy.items) for (size_t i = 0; i < v.count; i++) copy.items[i] = clone_value(v.items[i]);
        if (v.kind == V_OBJECT) {
            copy.keys = calloc(v.count ? v.count : 1, sizeof(*copy.keys));
            if (copy.keys) for (size_t i = 0; i < v.count; i++) copy.keys[i] = copy_text(v.keys[i]);
        }
        return copy;
    }
    return v;
}
static void free_value(Value v) {
    if (v.kind == V_STRING || v.kind == V_BYTES) free(v.string);
    if (v.kind == V_LIST || v.kind == V_OBJECT) {
        for (size_t i = 0; i < v.count; i++) { free_value(v.items[i]); if (v.kind == V_OBJECT) free(v.keys[i]); }
        free(v.items); free(v.keys);
    }
}

static separan_token *peek(Runtime *r) { return &r->tokens.tokens[r->at]; }
static int at(Runtime *r, const char *kind) { return strcmp(peek(r)->type, kind) == 0; }
static int at_label(Runtime *r) { return at(r, "IDENTIFIER") || at(r, "LABEL"); }
static separan_token *take(Runtime *r) { return &r->tokens.tokens[r->at++]; }
static int accept(Runtime *r, const char *kind) { if (!at(r, kind)) return 0; take(r); return 1; }
static const char *fault_code(const char *message) {
    if (!strcmp(message, "undefined variable")) return "E202";
    if (!strcmp(message, "unknown function")) return "E206";
    if (!strcmp(message, "wrong argument count")) return "E207";
    if (!strcmp(message, "constant cannot be reassigned")) return "E211";
    if (!strcmp(message, "list elements must have the same type")) return "E203";
    if (!strcmp(message, "list index out of range or invalid")) return "E302";
    if (!strcmp(message, "JSON parse error")) return "E740";
    if (!strcmp(message, "JSON encode error")) return "E741";
    if (!strcmp(message, "invalid capability path")) return "E721";
    if (!strcmp(message, "file I/O error")) return "E722";
    if (!strcmp(message, "file write error")) return "E723";
    if (!strcmp(message, "destination exists")) return "E725";
    if (!strcmp(message, "capability denied")) return "E720";
    if (!strcmp(message, "invalid hex")) return "E625";
    if (!strcmp(message, "bytes decode error")) return "E621";
    if (!strcmp(message, "invalid bytes index")) return "E622";
    if (!strcmp(message, "invalid bytes range")) return "E623";
    if (!strcmp(message, "bytes size limit")) return "E624";
    if (!strcmp(message, "invalid base64")) return "E626";
    if (!strcmp(message, "VOID value cannot be used")) return "E127";
    if (!strcmp(message, "top-level expression is not allowed")) return "E110";
    if (!strcmp(message, "variable type cannot change") ||
        !strcmp(message, "incompatible operand types") ||
        !strcmp(message, "condition must be boolean")) return "E201";
    return "E100";
}
static void fault(Runtime *r, const char *message) {
    if (!r->error) {
        r->error = 1; r->message = message;
        fprintf(r->errors, "SEPARAN %s: %s at line %zu, column %zu\n", fault_code(message), message,
                peek(r)->line, peek(r)->column);
    }
}
static int expect(Runtime *r, const char *kind) {
    if (accept(r, kind)) return 1;
    fault(r, "unexpected token"); return 0;
}
static void newlines(Runtime *r) { while (accept(r, "NEWLINE")) {} }

static Expr *new_expr(int kind) { Expr *e = calloc(1, sizeof(*e)); if (e) e->kind = kind; return e; }
static Stmt *new_stmt(int kind) { Stmt *s = calloc(1, sizeof(*s)); if (s) s->kind = kind; return s; }
static int add_stmt(Body *body, Stmt *stmt) {
    Stmt **items = realloc(body->items, (body->count + 1) * sizeof(*items));
    if (!items) return 0;
    body->items = items; body->items[body->count++] = stmt; return 1;
}
static int add_arg(Expr *expr, Expr *arg) {
    Expr **args = realloc(expr->args, (expr->argc + 1) * sizeof(*args));
    if (!args) return 0;
    expr->args = args; expr->args[expr->argc++] = arg; return 1;
}
static void free_expr(Expr *e) {
    if (!e) return;
    free(e->text); free_value(e->literal); free_expr(e->left); free_expr(e->right);
    for (size_t i = 0; i < e->argc; i++) free_expr(e->args[i]);
    free(e->args); free(e);
}
static void free_body(Body body) {
    for (size_t i = 0; i < body.count; i++) {
        Stmt *s = body.items[i];
        free(s->name); free_expr(s->expr); free_body(s->body); free_body(s->other);
        for (size_t j = 0; j < s->parameter_count; j++) free(s->parameters[j]);
        free(s->parameters); free(s);
    }
    free(body.items);
}

static int precedence(const char *kind) {
    if (!strcmp(kind, "OR")) return 1;
    if (!strcmp(kind, "AND")) return 2;
    if (!strcmp(kind, "EQUAL_EQUAL") || !strcmp(kind, "BANG_EQUAL")) return 3;
    if (!strcmp(kind, "LESS") || !strcmp(kind, "LESS_EQUAL") ||
        !strcmp(kind, "GREATER") || !strcmp(kind, "GREATER_EQUAL")) return 4;
    if (!strcmp(kind, "PLUS") || !strcmp(kind, "MINUS")) return 5;
    if (!strcmp(kind, "STAR") || !strcmp(kind, "SLASH") || !strcmp(kind, "PERCENT") ||
        !strcmp(kind, "FLOOR_DIV")) return 6;
    if (!strcmp(kind, "POWER")) return 7;
    return 0;
}

static Expr *parse_expr(Runtime *r, int minimum);
static Expr *parse_atom(Runtime *r) {
    separan_token *token = peek(r);
    if (accept(r, "NUMBER")) {
        Expr *e = new_expr(0); if (!e) return NULL;
        char *normalized = malloc(strlen(token->lexeme) + 1);
        if (!normalized) { free(e); return NULL; }
        size_t j = 0;
        for (size_t i = 0; token->lexeme[i]; i++) if (token->lexeme[i] != '_') normalized[j++] = token->lexeme[i];
        normalized[j] = 0;
        if (normalized[0] == '0' && (normalized[1] == 'b' || normalized[1] == 'B')) {
            double value = 0;
            for (size_t i = 2; normalized[i]; i++) value = value * 2 + (normalized[i] - '0');
            e->literal = number_value(value);
        } else if (normalized[0] == '0' && (normalized[1] == 'o' || normalized[1] == 'O')) {
            e->literal = number_value((double)strtoull(normalized + 2, NULL, 8));
        } else if (normalized[0] == '0' && (normalized[1] == 'x' || normalized[1] == 'X')) {
            e->literal = number_value((double)strtoull(normalized + 2, NULL, 16));
        } else e->literal = strchr(normalized, '.') ? floating_value(strtod(normalized, NULL)) :
                             number_value(strtod(normalized, NULL));
        free(normalized); return e;
    }
    if (accept(r, "STRING")) {
        Expr *e = new_expr(0); if (!e) return NULL;
        const char *start = token->lexeme + (token->lexeme[0] == 'r' ? 2 : 1);
        size_t length = strlen(start) - 1;
        char *decoded = malloc(length + 1); if (!decoded) { free(e); return NULL; }
        size_t j = 0;
        for (size_t i = 0; i < length; i++) {
            if (token->lexeme[0] != 'r' && start[i] == '\\' && i + 1 < length) {
                i++;
                if (start[i] == 'u' || start[i] == 'U') {
                    size_t digits = start[i] == 'u' ? 4 : 8;
                    unsigned value = 0;
                    for (size_t k = 1; k <= digits; k++) value = (value << 4) | (unsigned)hex_value(start[i + k]);
                    j += append_utf8(decoded + j, value); i += digits;
                } else decoded[j++] = start[i] == 'n' ? '\n' : start[i] == 't' ? '\t' :
                    start[i] == 'r' ? '\r' : start[i] == '0' ? '\0' : start[i];
            } else decoded[j++] = start[i];
        }
        decoded[j] = 0; e->literal.kind = V_STRING; e->literal.string = decoded;
        e->literal.string_length = j; return e;
    }
    if (accept(r, "TRUE") || accept(r, "FALSE")) {
        Expr *e = new_expr(0); if (e) e->literal = bool_value(strcmp(token->type, "TRUE") == 0); return e;
    }
    if (accept(r, "EMPTY")) return new_expr(0);
    if (accept(r, "LBRACKET")) {
        Expr *e = new_expr(5); if (!e) return NULL;
        if (!at(r, "RBRACKET")) do {
            if (!add_arg(e, parse_expr(r, 1))) { fault(r, "out of memory"); break; }
        } while (accept(r, "COMMA"));
        expect(r, "RBRACKET"); return e;
    }
    if (accept(r, "LPAREN")) {
        Expr *e = parse_expr(r, 1); expect(r, "RPAREN"); return e;
    }
    if (accept(r, "MINUS") || accept(r, "NOT") || accept(r, "BANG")) {
        Expr *e = new_expr(2); if (!e) return NULL;
        e->text = copy_text(token->type); e->right = parse_expr(r, 8); return e;
    }
    if (accept(r, "IDENTIFIER")) {
        Expr *e = new_expr(1); if (!e) return NULL;
        e->text = copy_text(token->lexeme);
        if (accept(r, "LPAREN")) {
            e->kind = 4;
            if (!at(r, "RPAREN")) do { if (!add_arg(e, parse_expr(r, 1))) break; } while (accept(r, "COMMA"));
            expect(r, "RPAREN");
        }
        return e;
    }
    fault(r, "expected expression"); return NULL;
}

static Expr *parse_primary(Runtime *r) {
    Expr *left = parse_atom(r);
    while (!r->error && (at(r, "LBRACKET") || at(r, "DOT"))) {
        if (accept(r, "LBRACKET")) {
            Expr *index = new_expr(6);
            if (!index) { fault(r, "out of memory"); break; }
            index->left = left;
            index->right = parse_expr(r, 1);
            expect(r, "RBRACKET");
            left = index;
        } else {
            take(r);
            Expr *member = new_expr(7);
            if (!member) { fault(r, "out of memory"); break; }
            member->left = left;
            if (at(r, "IDENTIFIER")) member->text = copy_text(take(r)->lexeme);
            else fault(r, "expected member name");
            left = member;
        }
    }
    return left;
}

static Expr *parse_expr(Runtime *r, int minimum) {
    Expr *left = parse_primary(r);
    while (!r->error) {
        int level = precedence(peek(r)->type);
        if (level < minimum) break;
        separan_token *op = take(r);
        Expr *node = new_expr(3); if (!node) return left;
        node->text = copy_text(op->type); node->left = left;
        node->right = parse_expr(r, level + (strcmp(op->type, "POWER") == 0 ? 0 : 1));
        left = node;
    }
    return left;
}

static Body parse_body(Runtime *r, const char *stop_a, const char *stop_b);
static Stmt *parse_stmt(Runtime *r) {
    separan_token *head = peek(r);
    if (accept(r, "FUNCTION")) {
        Stmt *s = new_stmt(5);
        expect(r, "COLON");
        if (at(r, "IDENTIFIER")) s->name = copy_text(take(r)->lexeme); else fault(r, "expected function name");
        if (accept(r, "LPAREN")) {
            if (!at(r, "RPAREN")) do {
                if (!at(r, "IDENTIFIER")) { fault(r, "expected parameter"); break; }
                char **next = realloc(s->parameters, (s->parameter_count + 1) * sizeof(*next));
                if (!next) { fault(r, "out of memory"); break; }
                s->parameters = next; s->parameters[s->parameter_count++] = copy_text(take(r)->lexeme);
            } while (accept(r, "COMMA"));
            expect(r, "RPAREN");
        }
        expect(r, "NEWLINE");
        while (accept(r, "TAG")) expect(r, "NEWLINE");
        s->body = parse_body(r, "END_FUNCTION", NULL);
        expect(r, "END_FUNCTION"); expect(r, "COLON");
        if (at(r, "IDENTIFIER") && s->name && strcmp(take(r)->lexeme, s->name) != 0) fault(r, "function label mismatch");
        else if (!r->error && !at(r, "NEWLINE") && !at(r, "EOF")) fault(r, "expected function label");
        return s;
    }
    if (accept(r, "FOR")) {
        Stmt *s = new_stmt(7);
        if (at(r, "IDENTIFIER")) {
            s->parameters = calloc(1, sizeof(*s->parameters));
            if (!s->parameters) { fault(r, "out of memory"); return s; }
            s->parameters[0] = copy_text(take(r)->lexeme); s->parameter_count = 1;
        } else fault(r, "expected loop variable");
        expect(r, "IN"); s->expr = parse_expr(r, 1); expect(r, "COLON");
        if (at_label(r)) s->name = copy_text(take(r)->lexeme); else fault(r, "expected label");
        expect(r, "NEWLINE"); s->body = parse_body(r, "ENDFOR", NULL);
        expect(r, "ENDFOR"); expect(r, "COLON");
        if (at_label(r) && s->name && strcmp(take(r)->lexeme, s->name) != 0) fault(r, "block label mismatch");
        return s;
    }
    if (accept(r, "IF") || accept(r, "WHILE")) {
        int is_if = strcmp(head->type, "IF") == 0;
        Stmt *s = new_stmt(is_if ? 3 : 4);
        s->expr = parse_expr(r, 1); expect(r, "COLON");
        if (at_label(r)) s->name = copy_text(take(r)->lexeme); else fault(r, "expected label");
        expect(r, "NEWLINE");
        s->body = parse_body(r, is_if ? "ELSE" : "ENDWHILE", is_if ? "ENDIF" : NULL);
        Stmt *branch = s;
        while (is_if && accept(r, "ELSEIF")) {
            Stmt *next = new_stmt(3);
            if (!next || !add_stmt(&branch->other, next)) { fault(r, "out of memory"); break; }
            next->name = copy_text(s->name);
            next->expr = parse_expr(r, 1); expect(r, "COLON");
            if (at_label(r) && s->name && strcmp(take(r)->lexeme, s->name) != 0)
                fault(r, "branch label mismatch");
            expect(r, "NEWLINE");
            next->body = parse_body(r, "ELSE", "ENDIF");
            branch = next;
        }
        if (is_if && accept(r, "ELSE")) {
            expect(r, "COLON");
            if (at_label(r) && s->name && strcmp(take(r)->lexeme, s->name) != 0) fault(r, "branch label mismatch");
            expect(r, "NEWLINE"); branch->other = parse_body(r, "ENDIF", NULL);
        }
        expect(r, is_if ? "ENDIF" : "ENDWHILE"); expect(r, "COLON");
        if (at_label(r) && s->name && strcmp(take(r)->lexeme, s->name) != 0) fault(r, "block label mismatch");
        return s;
    }
    if (accept(r, "PRINT") || accept(r, "RETURN")) {
        Stmt *s = new_stmt(strcmp(head->type, "PRINT") == 0 ? 1 : 2);
        if (!at(r, "NEWLINE") && !at(r, "EOF")) s->expr = parse_expr(r, 1);
        return s;
    }
    if (accept(r, "CONST")) {
        Stmt *s = new_stmt(8);
        if (at(r, "IDENTIFIER")) s->name = copy_text(take(r)->lexeme);
        else fault(r, "expected constant name");
        expect(r, "EQUAL"); s->expr = parse_expr(r, 1); return s;
    }
    if (accept(r, "OBJECT")) {
        Stmt *s = new_stmt(9);
        expect(r, "COLON");
        if (at(r, "IDENTIFIER")) s->name = copy_text(take(r)->lexeme);
        else fault(r, "expected object name");
        expect(r, "NEWLINE");
        s->body = parse_body(r, "END_OBJECT", NULL);
        expect(r, "END_OBJECT"); expect(r, "COLON");
        if (at(r, "IDENTIFIER") && s->name && strcmp(take(r)->lexeme, s->name) != 0)
            fault(r, "object label mismatch");
        return s;
    }
    if (accept(r, "LIST")) {
        Stmt *s = new_stmt(10);
        expect(r, "COLON");
        if (at(r, "IDENTIFIER")) s->name = copy_text(take(r)->lexeme);
        else fault(r, "expected list name");
        expect(r, "NEWLINE");
        s->body = parse_body(r, "END_LIST", NULL);
        expect(r, "END_LIST"); expect(r, "COLON");
        if (at(r, "IDENTIFIER") && s->name && strcmp(take(r)->lexeme, s->name) != 0)
            fault(r, "list label mismatch");
        return s;
    }
    if (at(r, "IDENTIFIER") && r->at + 1 < r->tokens.count &&
        strcmp(r->tokens.tokens[r->at + 1].type, "EQUAL") == 0) {
        Stmt *s = new_stmt(0); s->name = copy_text(take(r)->lexeme);
        take(r); s->expr = parse_expr(r, 1); return s;
    }
    Stmt *s = new_stmt(6); s->expr = parse_expr(r, 1); return s;
}

static Body parse_body(Runtime *r, const char *stop_a, const char *stop_b) {
    Body body = {0}; newlines(r);
    while (!r->error && !at(r, "EOF") && !(stop_a && at(r, stop_a)) && !(stop_b && at(r, stop_b)) &&
           !(stop_a && strcmp(stop_a, "ELSE") == 0 && at(r, "ELSEIF"))) {
        size_t old = r->at;
        Stmt *stmt = parse_stmt(r);
        if (!stmt || !add_stmt(&body, stmt)) { fault(r, "out of memory"); break; }
        if (!stop_a && !stop_b && stmt->kind == 6) fault(r, "top-level expression is not allowed");
        if (!at(r, "EOF") && !at(r, "NEWLINE")) fault(r, "expected end of line");
        newlines(r);
        if (old == r->at) { fault(r, "parser did not advance"); break; }
    }
    return body;
}

static Binding *lookup_local(Frame *frame, const char *name) {
    for (size_t i = 0; i < frame->count; i++)
        if (strcmp(frame->bindings[i].name, name) == 0) return &frame->bindings[i];
    return NULL;
}
static Binding *lookup(Frame *frame, const char *name) {
    for (Frame *current = frame; current; current = current->parent) {
        Binding *binding = lookup_local(current, name);
        if (binding) return binding;
    }
    return NULL;
}
static int bind(Frame *frame, const char *name, Value value, int constant) {
    Binding *found = lookup_local(frame, name);
    if (found) {
        if (found->constant || constant) return 0;
        free_value(found->value); found->value = clone_value(value); return 1;
    }
    Binding *next = realloc(frame->bindings, (frame->count + 1) * sizeof(*next));
    if (!next) return 0;
    frame->bindings = next; next[frame->count].name = copy_text(name);
    next[frame->count].value = clone_value(value); next[frame->count].constant = constant;
    frame->count++; return 1;
}
static void free_frame(Frame *frame) {
    for (size_t i = 0; i < frame->count; i++) { free(frame->bindings[i].name); free_value(frame->bindings[i].value); }
    free(frame->bindings);
}
static Stmt *find_function(Runtime *r, const char *name) {
    for (size_t i = 0; i < r->program.count; i++) {
        Stmt *s = r->program.items[i];
        if (s->kind == 5 && s->name && strcmp(s->name, name) == 0) return s;
    }
    return NULL;
}
static Value evaluate(Runtime *r, Frame *frame, Expr *e);
static void execute_body(Runtime *r, Frame *frame, Body body);
static int same_value(Value a, Value b) {
    if (a.kind != b.kind) return 0;
    if (a.kind == V_NUMBER) return a.number == b.number;
    if (a.kind == V_BOOL) return a.boolean == b.boolean;
    if (a.kind == V_STRING || a.kind == V_BYTES) return a.string_length == b.string_length &&
        memcmp(a.string, b.string, a.string_length) == 0;
    if (a.kind == V_LIST || a.kind == V_OBJECT) {
        if (a.count != b.count) return 0;
        for (size_t i = 0; i < a.count; i++) {
            if (a.kind == V_OBJECT && strcmp(a.keys[i], b.keys[i])) return 0;
            if (!same_value(a.items[i], b.items[i])) return 0;
        }
    }
    return 1;
}
static int builtin_name(const char *name) {
    const char *names[] = {"len", "length", "is_empty", "size", "first", "last",
                           "list_append", "append", "contains", "abs", "sum",
                           "type", "trim", "upper", "lower", "starts_with", "ends_with",
                           "number", "string", "boolean", "index_of", "last_index_of",
                           "reverse", "slice", "prepend", "ceil", "floor", "sqrt",
                           "sin", "cos", "tan", "round", "json_encode", "json_decode",
                           "read_text", "read_bytes", "write_text", "write_bytes", "append_text", "file_exists", "file_size",
                           "directory_exists", "create_directory", "delete_directory", "delete_file",
                           "read_lines", "list_directory", "file_name", "file_extension",
                           "parent_directory", "absolute_path", "copy_file", "move_file",
                           "bytes_from_string", "string_from_bytes", "bytes_get", "slice_bytes",
                           "bytes_concat", "hex_encode", "hex_decode", "bytes_from_hex",
                           "bytes_to_hexadecimal", "hexadecimal_to_bytes", "base64_encode",
                           "base64_decode", "bytes_to_base64", "base64_to_bytes"};
    for (size_t i = 0; i < sizeof(names) / sizeof(*names); i++)
        if (!strcmp(name, names[i])) return 1;
    return 0;
}
typedef struct { char *data; size_t length, capacity; } TextBuffer;
static int buffer_append(TextBuffer *buffer, const char *text, size_t length) {
    if (length > SIZE_MAX - buffer->length - 1) return 0;
    size_t needed = buffer->length + length + 1;
    if (needed > buffer->capacity) {
        size_t capacity = buffer->capacity ? buffer->capacity : 64;
        while (capacity < needed) {
            if (capacity > SIZE_MAX / 2) { capacity = needed; break; }
            capacity *= 2;
        }
        char *data = realloc(buffer->data, capacity);
        if (!data) return 0;
        buffer->data = data; buffer->capacity = capacity;
    }
    memcpy(buffer->data + buffer->length, text, length);
    buffer->length += length; buffer->data[buffer->length] = 0;
    return 1;
}
static int buffer_char(TextBuffer *buffer, char c) { return buffer_append(buffer, &c, 1); }
static int json_string(TextBuffer *buffer, const char *text, size_t length) {
    if (!buffer_char(buffer, '"')) return 0;
    for (size_t i = 0; i < length; i++) {
        unsigned char c = (unsigned char)text[i];
        const char *escape = c == '"' ? "\\\"" : c == '\\' ? "\\\\" :
                             c == '\n' ? "\\n" : c == '\r' ? "\\r" : c == '\t' ? "\\t" : NULL;
        if (escape) { if (!buffer_append(buffer, escape, 2)) return 0; }
        else if (c < 0x20) {
            char code[7]; snprintf(code, sizeof(code), "\\u%04x", c);
            if (!buffer_append(buffer, code, 6)) return 0;
        } else if (!buffer_char(buffer, (char)c)) return 0;
    }
    return buffer_char(buffer, '"');
}
static int json_value(TextBuffer *buffer, Value value, unsigned depth) {
    if (depth > 128) return 0;
    if (value.kind == V_EMPTY) return buffer_append(buffer, "null", 4);
    if (value.kind == V_BOOL) return buffer_append(buffer, value.boolean ? "true" : "false", value.boolean ? 4 : 5);
    if (value.kind == V_NUMBER) {
        if (!isfinite(value.number)) return 0;
        char number[64]; format_number(number, sizeof(number), value);
        return buffer_append(buffer, number, strlen(number));
    }
    if (value.kind == V_STRING) return json_string(buffer, value.string, value.string_length);
    if (value.kind == V_LIST) {
        if (!buffer_char(buffer, '[')) return 0;
        for (size_t i = 0; i < value.count; i++) {
            if (i && !buffer_char(buffer, ',')) return 0;
            if (!json_value(buffer, value.items[i], depth + 1)) return 0;
        }
        return buffer_char(buffer, ']');
    }
    if (value.kind == V_OBJECT) {
        if (!buffer_char(buffer, '{')) return 0;
        unsigned char *used = calloc(value.count ? value.count : 1, 1);
        if (!used) return 0;
        for (size_t i = 0; i < value.count; i++) {
            size_t selected = value.count;
            for (size_t j = 0; j < value.count; j++)
                if (!used[j] && (selected == value.count || strcmp(value.keys[j], value.keys[selected]) < 0))
                    selected = j;
            used[selected] = 1;
            if (i && !buffer_char(buffer, ',')) { free(used); return 0; }
            if (!json_string(buffer, value.keys[selected], strlen(value.keys[selected])) ||
                !buffer_char(buffer, ':') || !json_value(buffer, value.items[selected], depth + 1)) {
                free(used); return 0;
            }
        }
        free(used); return buffer_char(buffer, '}');
    }
    return 0;
}
typedef struct { const char *text; size_t length, at; int error; } JsonCursor;
static void json_space(JsonCursor *cursor) {
    while (cursor->at < cursor->length &&
           (cursor->text[cursor->at] == ' ' || cursor->text[cursor->at] == '\n' ||
            cursor->text[cursor->at] == '\r' || cursor->text[cursor->at] == '\t')) cursor->at++;
}
static int json_hex4(JsonCursor *cursor, unsigned *value) {
    if (cursor->at + 4 > cursor->length) return 0;
    *value = 0;
    for (size_t i = 0; i < 4; i++) {
        char c = cursor->text[cursor->at++];
        if (!isxdigit((unsigned char)c)) return 0;
        *value = (*value << 4) | (unsigned)hex_value(c);
    }
    return 1;
}
static Value json_parse_string(JsonCursor *cursor) {
    Value result = empty_value();
    TextBuffer buffer = {0};
    if (cursor->at >= cursor->length || cursor->text[cursor->at++] != '"') goto invalid;
    while (cursor->at < cursor->length) {
        unsigned char c = (unsigned char)cursor->text[cursor->at++];
        if (c == '"') {
            result = string_bytes(buffer.data ? buffer.data : "", buffer.length);
            free(buffer.data); return result;
        }
        if (c < 0x20) goto invalid;
        if (c == '\\') {
            if (cursor->at >= cursor->length) goto invalid;
            c = (unsigned char)cursor->text[cursor->at++];
            if (c == 'u') {
                unsigned value;
                if (!json_hex4(cursor, &value)) goto invalid;
                if (value >= 0xD800 && value <= 0xDBFF) {
                    if (cursor->at + 2 > cursor->length || cursor->text[cursor->at++] != '\\' ||
                        cursor->text[cursor->at++] != 'u') goto invalid;
                    unsigned low;
                    if (!json_hex4(cursor, &low) || low < 0xDC00 || low > 0xDFFF) goto invalid;
                    value = 0x10000 + ((value - 0xD800) << 10) + (low - 0xDC00);
                } else if (value >= 0xDC00 && value <= 0xDFFF) goto invalid;
                char utf8[4]; size_t width = append_utf8(utf8, value);
                if (!buffer_append(&buffer, utf8, width)) goto invalid;
                continue;
            }
            if (c == 'n') c = '\n'; else if (c == 'r') c = '\r';
            else if (c == 't') c = '\t'; else if (c == 'b') c = '\b';
            else if (c == 'f') c = '\f';
            else if (c != '"' && c != '\\' && c != '/') goto invalid;
        }
        if (!buffer_char(&buffer, (char)c)) goto invalid;
    }
invalid:
    free(buffer.data); cursor->error = 1; return empty_value();
}
static Value json_parse_value(JsonCursor *cursor, unsigned depth) {
    Value result = empty_value();
    json_space(cursor);
    if (cursor->at >= cursor->length || depth > 128) { cursor->error = 1; return result; }
    char c = cursor->text[cursor->at];
    if (c == '"') return json_parse_string(cursor);
    if (c == 't' && cursor->at + 4 <= cursor->length && !memcmp(cursor->text + cursor->at, "true", 4)) {
        cursor->at += 4; return bool_value(1);
    }
    if (c == 'f' && cursor->at + 5 <= cursor->length && !memcmp(cursor->text + cursor->at, "false", 5)) {
        cursor->at += 5; return bool_value(0);
    }
    if (c == 'n' && cursor->at + 4 <= cursor->length && !memcmp(cursor->text + cursor->at, "null", 4)) {
        cursor->at += 4; return result;
    }
    if (c == '[' || c == '{') {
        int object = c == '{';
        result.kind = object ? V_OBJECT : V_LIST; cursor->at++; json_space(cursor);
        if (cursor->at < cursor->length && cursor->text[cursor->at] == (object ? '}' : ']')) {
            cursor->at++; return result;
        }
        while (!cursor->error && cursor->at < cursor->length) {
            char *key = NULL;
            if (object) {
                Value parsed = json_parse_string(cursor);
                if (cursor->error) break;
                key = parsed.string;
                json_space(cursor);
                if (cursor->at >= cursor->length || cursor->text[cursor->at++] != ':') {
                    free(key); cursor->error = 1; break;
                }
                for (size_t i = 0; i < result.count; i++) if (!strcmp(result.keys[i], key)) cursor->error = 1;
                if (cursor->error) { free(key); break; }
            }
            Value item = json_parse_value(cursor, depth + 1);
            if (cursor->error || (!object && result.count && item.kind != result.items[0].kind)) {
                free(key); free_value(item); cursor->error = 1; break;
            }
            Value *items = realloc(result.items, (result.count + 1) * sizeof(*items));
            if (!items) { free(key); free_value(item); cursor->error = 1; break; }
            result.items = items;
            if (object) {
                char **keys = realloc(result.keys, (result.count + 1) * sizeof(*keys));
                if (!keys) { free(key); free_value(item); cursor->error = 1; break; }
                result.keys = keys; result.keys[result.count] = key;
            }
            result.items[result.count++] = item;
            json_space(cursor);
            if (cursor->at >= cursor->length) { cursor->error = 1; break; }
            c = cursor->text[cursor->at++];
            if (c == (object ? '}' : ']')) return result;
            if (c != ',') { cursor->error = 1; break; }
            json_space(cursor);
        }
        free_value(result); return empty_value();
    }
    size_t start = cursor->at;
    if (c == '-') cursor->at++;
    size_t digits = 0;
    while (cursor->at < cursor->length && isdigit((unsigned char)cursor->text[cursor->at])) {
        cursor->at++; digits++;
    }
    if (!digits) { cursor->error = 1; return result; }
    int floating = 0;
    if (cursor->at < cursor->length && cursor->text[cursor->at] == '.') {
        floating = 1; cursor->at++; size_t fraction = 0;
        while (cursor->at < cursor->length && isdigit((unsigned char)cursor->text[cursor->at])) {
            cursor->at++; fraction++;
        }
        if (!fraction) { cursor->error = 1; return result; }
    }
    if (cursor->at < cursor->length && (cursor->text[cursor->at] == 'e' || cursor->text[cursor->at] == 'E')) {
        floating = 1; cursor->at++;
        if (cursor->at < cursor->length && (cursor->text[cursor->at] == '+' || cursor->text[cursor->at] == '-')) cursor->at++;
        size_t exponent = 0;
        while (cursor->at < cursor->length && isdigit((unsigned char)cursor->text[cursor->at])) {
            cursor->at++; exponent++;
        }
        if (!exponent) { cursor->error = 1; return result; }
    }
    char *number = malloc(cursor->at - start + 1);
    if (!number) { cursor->error = 1; return result; }
    memcpy(number, cursor->text + start, cursor->at - start);
    number[cursor->at - start] = 0;
    result = floating ? floating_value(strtod(number, NULL)) : number_value(strtod(number, NULL));
    free(number);
    if (!isfinite(result.number)) cursor->error = 1;
    return result;
}
static Value builtin_call(Runtime *r, Frame *frame, Expr *e) {
    Value args[3] = {{0}, {0}, {0}};
    Value result = empty_value();
    const char *name = e->text;
    int three = !strcmp(name, "slice") || !strcmp(name, "slice_bytes");
    int two = !strcmp(name, "list_append") || !strcmp(name, "append") || !strcmp(name, "prepend") ||
              !strcmp(name, "contains") || !strcmp(name, "starts_with") || !strcmp(name, "ends_with") ||
              !strcmp(name, "index_of") || !strcmp(name, "last_index_of") ||
              !strcmp(name, "write_text") || !strcmp(name, "write_bytes") || !strcmp(name, "append_text") ||
              !strcmp(name, "copy_file") || !strcmp(name, "move_file") ||
              !strcmp(name, "bytes_get") || !strcmp(name, "bytes_concat");
    if (e->argc != (size_t)(three ? 3 : two ? 2 : 1)) { fault(r, "wrong argument count"); return result; }
    for (size_t i = 0; i < e->argc && !r->error; i++) args[i] = evaluate(r, frame, e->args[i]);
    if (r->error) goto done;
    if (!strcmp(name, "len") || !strcmp(name, "length") || !strcmp(name, "is_empty")) {
        size_t length;
        if (args[0].kind == V_LIST) length = args[0].count;
        else if (args[0].kind == V_STRING) length = utf8_length(args[0].string, args[0].string_length);
        else { fault(r, "length requires string or list"); goto done; }
        result = !strcmp(name, "is_empty") ? bool_value(length == 0) : number_value((double)length);
    } else if (!strcmp(name, "size") || !strcmp(name, "first") || !strcmp(name, "last")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        if (!strcmp(name, "size")) result = number_value((double)args[0].count);
        else if (!args[0].count) fault(r, "empty list access");
        else result = clone_value(args[0].items[!strcmp(name, "first") ? 0 : args[0].count - 1]);
    } else if (!strcmp(name, "contains")) {
        if (args[0].kind == V_STRING && args[1].kind == V_STRING) {
            int found = args[1].string_length == 0;
            for (size_t i = 0; !found && i + args[1].string_length <= args[0].string_length; i++)
                found = memcmp(args[0].string + i, args[1].string, args[1].string_length) == 0;
            result = bool_value(found);
        }
        else if (args[0].kind == V_LIST) {
            if (args[0].count && args[0].items[0].kind != args[1].kind) { fault(r, "incompatible search value"); goto done; }
            int found = 0;
            for (size_t i = 0; i < args[0].count; i++) if (same_value(args[0].items[i], args[1])) found = 1;
            result = bool_value(found);
        } else fault(r, "string or list required");
    } else if (!strcmp(name, "index_of") || !strcmp(name, "last_index_of")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        if (args[0].count && args[0].items[0].kind != args[1].kind) { fault(r, "incompatible search value"); goto done; }
        for (size_t i = 0; i < args[0].count; i++) {
            size_t index = !strcmp(name, "index_of") ? i : args[0].count - i - 1;
            if (same_value(args[0].items[index], args[1])) { result = number_value((double)index); break; }
        }
    } else if (!strcmp(name, "reverse")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        result.kind = V_LIST; result.count = args[0].count;
        result.items = calloc(result.count ? result.count : 1, sizeof(*result.items));
        if (!result.items) { fault(r, "out of memory"); result = empty_value(); goto done; }
        for (size_t i = 0; i < result.count; i++)
            result.items[i] = clone_value(args[0].items[result.count - 1 - i]);
    } else if (!strcmp(name, "slice")) {
        if (args[0].kind != V_LIST || args[1].kind != V_NUMBER || args[2].kind != V_NUMBER ||
            args[1].number < 0 || args[2].number < args[1].number ||
            args[2].number > (double)args[0].count ||
            floor(args[1].number) != args[1].number || floor(args[2].number) != args[2].number) {
            fault(r, "invalid list slice"); goto done;
        }
        size_t start = (size_t)args[1].number;
        result.kind = V_LIST; result.count = (size_t)args[2].number - start;
        result.items = calloc(result.count ? result.count : 1, sizeof(*result.items));
        if (!result.items) { fault(r, "out of memory"); result = empty_value(); goto done; }
        for (size_t i = 0; i < result.count; i++) result.items[i] = clone_value(args[0].items[start + i]);
    } else if (!strcmp(name, "list_append") || !strcmp(name, "append") || !strcmp(name, "prepend")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        if (args[0].count && args[0].items[0].kind != args[1].kind) { fault(r, "incompatible list value"); goto done; }
        result.kind = V_LIST; result.count = args[0].count + 1;
        result.items = calloc(result.count, sizeof(*result.items));
        if (!result.items) { fault(r, "out of memory"); result = empty_value(); goto done; }
        int prepend = !strcmp(name, "prepend");
        for (size_t i = 0; i < args[0].count; i++) result.items[i + prepend] = clone_value(args[0].items[i]);
        result.items[prepend ? 0 : args[0].count] = clone_value(args[1]);
    } else if (!strcmp(name, "abs")) {
        if (args[0].kind != V_NUMBER) fault(r, "number required");
        else { result = number_value(fabs(args[0].number)); result.floating = args[0].floating; }
    } else if (!strcmp(name, "ceil") || !strcmp(name, "floor") || !strcmp(name, "sqrt") ||
               !strcmp(name, "sin") || !strcmp(name, "cos") || !strcmp(name, "tan") ||
               !strcmp(name, "round")) {
        if (args[0].kind != V_NUMBER || !isfinite(args[0].number)) { fault(r, "finite number required"); goto done; }
        double n = args[0].number;
        if (!strcmp(name, "ceil")) result = number_value(ceil(n));
        else if (!strcmp(name, "floor")) result = number_value(floor(n));
        else if (!strcmp(name, "sqrt")) {
            if (n < 0) fault(r, "math domain error"); else result = floating_value(sqrt(n));
        } else if (!strcmp(name, "sin")) result = floating_value(sin(n));
        else if (!strcmp(name, "cos")) result = floating_value(cos(n));
        else if (!strcmp(name, "tan")) result = floating_value(tan(n));
        else result = number_value(n >= 0 ? floor(n + 0.5) : ceil(n - 0.5));
    } else if (!strcmp(name, "sum")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        double total = 0;
        int floating = 0;
        for (size_t i = 0; i < args[0].count; i++) {
            if (args[0].items[i].kind != V_NUMBER) { fault(r, "number list required"); break; }
            total += args[0].items[i].number;
            floating |= args[0].items[i].floating;
        }
        if (!r->error) { result = number_value(total); result.floating = floating; }
    } else if (!strcmp(name, "type")) {
        const char *types[] = {"EMPTY", "number", "boolean", "string", "list", "object", "VOID", "bytes"};
        result = string_value(types[args[0].kind]);
    } else if (!strcmp(name, "json_encode")) {
        TextBuffer buffer = {0};
        if (!json_value(&buffer, args[0], 0)) fault(r, "JSON encode error");
        else result = string_bytes(buffer.data, buffer.length);
        free(buffer.data);
    } else if (!strcmp(name, "json_decode")) {
        if (args[0].kind != V_STRING) { fault(r, "JSON text must be a string"); goto done; }
        JsonCursor cursor = {args[0].string, args[0].string_length, 0, 0};
        result = json_parse_value(&cursor, 0); json_space(&cursor);
        if (cursor.error || cursor.at != cursor.length) {
            free_value(result); result = empty_value(); fault(r, "JSON parse error");
        }
    } else if (!strcmp(name, "bytes_from_string") || !strcmp(name, "string_from_bytes")) {
        if (!strcmp(name, "bytes_from_string")) {
            if (args[0].kind != V_STRING) fault(r, "string required");
            else { result = clone_value(args[0]); result.kind = V_BYTES; }
        } else {
            if (args[0].kind != V_BYTES) fault(r, "bytes required");
            else if (!valid_utf8_bytes(args[0].string, args[0].string_length)) fault(r, "bytes decode error");
            else { result = clone_value(args[0]); result.kind = V_STRING; }
        }
    } else if (!strcmp(name, "hex_encode") || !strcmp(name, "bytes_to_hexadecimal")) {
        if (args[0].kind != V_BYTES) { fault(r, "bytes required"); goto done; }
        if (args[0].string_length > SIZE_MAX / 2) { fault(r, "bytes size limit"); goto done; }
        size_t length = args[0].string_length * 2;
        char *hex = malloc(length + 1);
        if (!hex) { fault(r, "out of memory"); goto done; }
        const char *digits = "0123456789ABCDEF";
        for (size_t i = 0; i < args[0].string_length; i++) {
            unsigned char byte = (unsigned char)args[0].string[i];
            hex[2 * i] = digits[byte >> 4]; hex[2 * i + 1] = digits[byte & 15];
        }
        hex[length] = 0; result = string_bytes(hex, length); free(hex);
    } else if (!strcmp(name, "hex_decode") || !strcmp(name, "bytes_from_hex") ||
               !strcmp(name, "hexadecimal_to_bytes")) {
        if (args[0].kind != V_STRING) { fault(r, "hex string required"); goto done; }
        if (args[0].string_length % 2) { fault(r, "invalid hex"); goto done; }
        size_t length = args[0].string_length / 2;
        char *bytes = malloc(length + 1);
        if (!bytes) { fault(r, "out of memory"); goto done; }
        for (size_t i = 0; i < length; i++) {
            char high = args[0].string[2 * i], low = args[0].string[2 * i + 1];
            if (!isxdigit((unsigned char)high) || !isxdigit((unsigned char)low)) {
                fault(r, "invalid hex"); break;
            }
            bytes[i] = (char)((hex_value(high) << 4) | hex_value(low));
        }
        if (!r->error) { result = string_bytes(bytes, length); result.kind = V_BYTES; }
        free(bytes);
    } else if (!strcmp(name, "bytes_get")) {
        if (args[0].kind != V_BYTES || args[1].kind != V_NUMBER || args[1].floating ||
            args[1].number < 0 || floor(args[1].number) != args[1].number ||
            args[1].number >= (double)args[0].string_length) fault(r, "invalid bytes index");
        else result = number_value((unsigned char)args[0].string[(size_t)args[1].number]);
    } else if (!strcmp(name, "slice_bytes")) {
        if (args[0].kind != V_BYTES || args[1].kind != V_NUMBER || args[2].kind != V_NUMBER ||
            args[1].floating || args[2].floating || args[1].number < 0 ||
            args[2].number < args[1].number || args[2].number > (double)args[0].string_length ||
            floor(args[1].number) != args[1].number || floor(args[2].number) != args[2].number)
            fault(r, "invalid bytes range");
        else {
            size_t start = (size_t)args[1].number, end = (size_t)args[2].number;
            result = string_bytes(args[0].string + start, end - start); result.kind = V_BYTES;
        }
    } else if (!strcmp(name, "bytes_concat")) {
        if (args[0].kind != V_BYTES || args[1].kind != V_BYTES) { fault(r, "bytes required"); goto done; }
        if (args[1].string_length > 67108864 ||
            args[0].string_length > 67108864 - args[1].string_length) {
            fault(r, "bytes size limit"); goto done;
        }
        result.kind = V_BYTES; result.string_length = args[0].string_length + args[1].string_length;
        result.string = malloc(result.string_length + 1);
        if (!result.string) { fault(r, "out of memory"); goto done; }
        memcpy(result.string, args[0].string, args[0].string_length);
        memcpy(result.string + args[0].string_length, args[1].string, args[1].string_length);
        result.string[result.string_length] = 0;
    } else if (!strcmp(name, "base64_encode") || !strcmp(name, "bytes_to_base64")) {
        if (args[0].kind != V_BYTES) { fault(r, "bytes required"); goto done; }
        size_t length = args[0].string_length;
        if (length > (SIZE_MAX / 4) * 3) { fault(r, "bytes size limit"); goto done; }
        size_t encoded_length = ((length + 2) / 3) * 4;
        char *encoded = malloc(encoded_length + 1);
        if (!encoded) { fault(r, "out of memory"); goto done; }
        const char *alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        size_t j = 0;
        for (size_t i = 0; i < length; i += 3) {
            unsigned a = (unsigned char)args[0].string[i];
            unsigned b = i + 1 < length ? (unsigned char)args[0].string[i + 1] : 0;
            unsigned c = i + 2 < length ? (unsigned char)args[0].string[i + 2] : 0;
            encoded[j++] = alphabet[a >> 2];
            encoded[j++] = alphabet[((a & 3) << 4) | (b >> 4)];
            encoded[j++] = i + 1 < length ? alphabet[((b & 15) << 2) | (c >> 6)] : '=';
            encoded[j++] = i + 2 < length ? alphabet[c & 63] : '=';
        }
        encoded[j] = 0; result = string_bytes(encoded, j); free(encoded);
    } else if (!strcmp(name, "base64_decode") || !strcmp(name, "base64_to_bytes")) {
        if (args[0].kind != V_STRING) { fault(r, "base64 string required"); goto done; }
        size_t length = args[0].string_length;
        if (length % 4) { fault(r, "invalid base64"); goto done; }
        char *decoded = malloc(length / 4 * 3 + 1);
        if (!decoded) { fault(r, "out of memory"); goto done; }
        size_t written = 0;
        const char *alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        for (size_t i = 0; i < length; i += 4) {
            unsigned bits[4] = {0};
            int padding = 0;
            for (size_t k = 0; k < 4; k++) {
                char c = args[0].string[i + k];
                if (c == '=') {
                    if (k < 2 || i + 4 != length) { fault(r, "invalid base64"); break; }
                    padding++;
                } else {
                    if (padding) { fault(r, "invalid base64"); break; }
                    const char *found = c ? strchr(alphabet, c) : NULL;
                    if (!found) { fault(r, "invalid base64"); break; }
                    bits[k] = (unsigned)(found - alphabet);
                }
            }
            if (r->error) break;
            decoded[written++] = (char)((bits[0] << 2) | (bits[1] >> 4));
            if (padding < 2) decoded[written++] = (char)((bits[1] << 4) | (bits[2] >> 2));
            if (padding == 0) decoded[written++] = (char)((bits[2] << 6) | bits[3]);
        }
        if (!r->error) { result = string_bytes(decoded, written); result.kind = V_BYTES; }
        free(decoded);
    } else if (!strcmp(name, "copy_file") || !strcmp(name, "move_file")) {
        if (!r->read_files || !r->write_files) { fault(r, "capability denied"); goto done; }
        if (args[0].kind != V_STRING || args[1].kind != V_STRING) {
            fault(r, "file paths must be strings"); goto done;
        }
        if (strlen(args[0].string) != args[0].string_length ||
            strlen(args[1].string) != args[1].string_length) {
            fault(r, "invalid capability path"); goto done;
        }
        int status = !strcmp(name, "copy_file") ?
            separan_files_copy_file(&r->files, args[0].string, args[1].string) :
            separan_files_move_file(&r->files, args[0].string, args[1].string);
        if (!status) result.kind = V_VOID;
        else fault(r, status == 1 ? "invalid capability path" :
                      status == 3 ? "destination exists" : "file write error");
    } else if (!strcmp(name, "read_text") || !strcmp(name, "read_bytes") || !strcmp(name, "read_lines") ||
               !strcmp(name, "list_directory") || !strcmp(name, "write_text") || !strcmp(name, "append_text") ||
               !strcmp(name, "write_bytes") || !strcmp(name, "file_exists") || !strcmp(name, "file_size") ||
               !strcmp(name, "directory_exists") || !strcmp(name, "create_directory") ||
               !strcmp(name, "delete_directory") || !strcmp(name, "delete_file") ||
               !strcmp(name, "file_name") || !strcmp(name, "file_extension") ||
               !strcmp(name, "parent_directory") || !strcmp(name, "absolute_path")) {
        int needs_read = !strcmp(name, "read_text") || !strcmp(name, "read_bytes") ||
                         !strcmp(name, "read_lines") || !strcmp(name, "file_size");
        int needs_write = !strcmp(name, "write_text") || !strcmp(name, "write_bytes") ||
                          !strcmp(name, "append_text") || !strcmp(name, "create_directory") ||
                          !strcmp(name, "delete_directory") || !strcmp(name, "delete_file");
        if ((needs_read && !r->read_files) || (needs_write && !r->write_files) ||
            (!needs_read && !needs_write && !r->discover_paths)) {
            fault(r, "capability denied"); goto done;
        }
        if (args[0].kind != V_STRING) { fault(r, "file path must be a string"); goto done; }
        if (strlen(args[0].string) != args[0].string_length) { fault(r, "invalid capability path"); goto done; }
        int status = 0;
        if (!strcmp(name, "read_text") || !strcmp(name, "read_bytes") || !strcmp(name, "read_lines")) {
            char *data = NULL; size_t length = 0;
            status = !strcmp(name, "read_bytes") ?
                separan_files_read_bytes(&r->files, args[0].string, &data, &length) :
                separan_files_read_text(&r->files, args[0].string, &data, &length);
            if (!status) {
                if (!strcmp(name, "read_text") || !strcmp(name, "read_bytes")) {
                    result = string_bytes(data, length);
                    if (!strcmp(name, "read_bytes")) result.kind = V_BYTES;
                }
                else {
                    result.kind = V_LIST;
                    for (size_t start = 0; start < length;) {
                        size_t end = start;
                        while (end < length && data[end] != '\n') end++;
                        Value *next = realloc(result.items, (result.count + 1) * sizeof(*next));
                        if (!next) { fault(r, "out of memory"); break; }
                        result.items = next; next[result.count++] = string_bytes(data + start, end - start);
                        start = end < length ? end + 1 : end;
                    }
                }
                free(data);
            }
        } else if (!strcmp(name, "list_directory")) {
            char **names = NULL; size_t count = 0;
            status = separan_files_list_directory(&r->files, args[0].string, &names, &count);
            if (!status) {
                result.kind = V_LIST;
                result.items = calloc(count ? count : 1, sizeof(*result.items));
                if (!result.items) fault(r, "out of memory");
                else {
                    result.count = count;
                    for (size_t i = 0; i < count; i++) result.items[i] = string_value(names[i]);
                }
                separan_files_list_free(names, count);
            }
        } else if (!strcmp(name, "write_text") || !strcmp(name, "write_bytes") || !strcmp(name, "append_text")) {
            if (args[1].kind != (!strcmp(name, "write_bytes") ? V_BYTES : V_STRING)) {
                fault(r, "file value has wrong type"); goto done;
            }
            status = !strcmp(name, "write_bytes") ?
                separan_files_write_bytes(&r->files, args[0].string, args[1].string, args[1].string_length) :
                !strcmp(name, "write_text") ?
                separan_files_write_text(&r->files, args[0].string, args[1].string, args[1].string_length) :
                separan_files_append_text(&r->files, args[0].string, args[1].string, args[1].string_length);
            if (!status) result.kind = V_VOID;
        } else if (!strcmp(name, "file_exists")) {
            int exists = 0;
            status = separan_files_exists(&r->files, args[0].string, &exists);
            if (!status) result = bool_value(exists);
        } else if (!strcmp(name, "directory_exists")) {
            int exists = 0;
            status = separan_files_directory_exists(&r->files, args[0].string, &exists);
            if (!status) result = bool_value(exists);
        } else if (!strcmp(name, "create_directory")) {
            status = separan_files_create_directory(&r->files, args[0].string);
            if (!status) result.kind = V_VOID;
        } else if (!strcmp(name, "delete_directory")) {
            status = separan_files_delete_directory(&r->files, args[0].string);
            if (!status) result.kind = V_VOID;
        } else if (!strcmp(name, "delete_file")) {
            status = separan_files_delete_file(&r->files, args[0].string);
            if (!status) result.kind = V_VOID;
        } else if (!strcmp(name, "file_name") || !strcmp(name, "file_extension") ||
                   !strcmp(name, "parent_directory") || !strcmp(name, "absolute_path")) {
            char *absolute = NULL;
            status = separan_files_path(&r->files, args[0].string, &absolute);
            if (!status) {
                if (!strcmp(name, "absolute_path")) {
#ifdef _WIN32
                    char *canonical = _fullpath(NULL, absolute, 0);
                    result = string_value(canonical ? canonical : absolute);
                    free(canonical);
#else
                    result = string_value(absolute);
#endif
                } else {
                    size_t length = args[0].string_length;
                    while (length && (args[0].string[length - 1] == '/' || args[0].string[length - 1] == '\\')) length--;
                    size_t start = length;
                    while (start && args[0].string[start - 1] != '/' && args[0].string[start - 1] != '\\') start--;
                    if (!strcmp(name, "parent_directory")) {
                        size_t parent = start ? start - 1 : 0;
                        while (parent && (args[0].string[parent - 1] == '/' || args[0].string[parent - 1] == '\\')) parent--;
                        result = parent ? string_bytes(args[0].string, parent) : string_value(".");
                        for (size_t i = 0; i < result.string_length; i++)
                            if (result.string[i] == '\\') result.string[i] = '/';
                    } else if (!strcmp(name, "file_name")) result = string_bytes(args[0].string + start, length - start);
                    else {
                        size_t dot = length;
                        while (dot > start && args[0].string[dot - 1] != '.') dot--;
                        result = (dot == start + 1 || dot == length || dot == start) ?
                            string_value("") : string_bytes(args[0].string + dot, length - dot);
                    }
                }
                free(absolute);
            }
        } else {
            size_t size = 0;
            status = separan_files_size(&r->files, args[0].string, &size);
            if (!status) result = number_value((double)size);
        }
        if (status == 1) fault(r, "invalid capability path");
        else if (status) fault(r, !strcmp(name, "write_text") || !strcmp(name, "write_bytes") || !strcmp(name, "append_text") ||
                               !strcmp(name, "create_directory") || !strcmp(name, "delete_directory") ||
                               !strcmp(name, "delete_file") ? "file write error" : "file I/O error");
    } else if (!strcmp(name, "trim") || !strcmp(name, "upper") || !strcmp(name, "lower")) {
        if (args[0].kind != V_STRING) { fault(r, "string required"); goto done; }
        const char *start = args[0].string;
        size_t length = args[0].string_length;
        if (!strcmp(name, "trim")) {
            while (length && isspace((unsigned char)*start)) { start++; length--; }
            while (length && isspace((unsigned char)start[length - 1])) length--;
        }
        char *converted = malloc(length + 1);
        if (!converted) { fault(r, "out of memory"); goto done; }
        for (size_t i = 0; i < length; i++) converted[i] =
            !strcmp(name, "upper") ? (char)toupper((unsigned char)start[i]) :
            !strcmp(name, "lower") ? (char)tolower((unsigned char)start[i]) : start[i];
        converted[length] = 0; result.kind = V_STRING; result.string = converted;
        result.string_length = length;
    } else if (!strcmp(name, "starts_with") || !strcmp(name, "ends_with")) {
        if (args[0].kind != V_STRING || args[1].kind != V_STRING) { fault(r, "strings required"); goto done; }
        size_t length = args[0].string_length, part = args[1].string_length;
        result = bool_value(part <= length &&
            (!strcmp(name, "starts_with") ? memcmp(args[0].string, args[1].string, part) == 0 :
             memcmp(args[0].string + length - part, args[1].string, part) == 0));
    } else if (!strcmp(name, "string")) {
        if (args[0].kind == V_STRING) result = clone_value(args[0]);
        else if (args[0].kind == V_BOOL) result = string_value(args[0].boolean ? "true" : "false");
        else if (args[0].kind == V_NUMBER) {
            char text[64]; format_number(text, sizeof(text), args[0]); result = string_value(text);
        } else fault(r, "cannot convert to string");
    } else if (!strcmp(name, "number")) {
        if (args[0].kind == V_NUMBER) result = args[0];
        else if (args[0].kind == V_STRING) {
            const char *text = args[0].string;
            if (strlen(text) != args[0].string_length) { fault(r, "invalid decimal string"); goto done; }
            size_t i = (*text == '-') ? 1 : 0, digits = 0;
            while (isdigit((unsigned char)text[i])) { i++; digits++; }
            if (text[i] == '.') {
                i++; size_t fractional = 0;
                while (isdigit((unsigned char)text[i])) { i++; fractional++; }
                if (!fractional) digits = 0;
            }
            if (!digits || text[i]) fault(r, "invalid decimal string");
            else result = strchr(text, '.') ? floating_value(strtod(text, NULL)) : number_value(strtod(text, NULL));
        } else fault(r, "cannot convert to number");
    } else if (!strcmp(name, "boolean")) {
        if (args[0].kind == V_BOOL) result = args[0];
        else if (args[0].kind == V_STRING && args[0].string_length == 4 && !memcmp(args[0].string, "true", 4)) result = bool_value(1);
        else if (args[0].kind == V_STRING && args[0].string_length == 5 && !memcmp(args[0].string, "false", 5)) result = bool_value(0);
        else fault(r, "cannot convert to boolean");
    }
done:
    for (size_t i = 0; i < e->argc; i++) free_value(args[i]);
    return result;
}
static Value call(Runtime *r, Frame *frame, Expr *e) {
    if (builtin_name(e->text)) return builtin_call(r, frame, e);
    Stmt *function = find_function(r, e->text);
    if (!function) { fault(r, "unknown function"); return empty_value(); }
    if (function->parameter_count != e->argc) { fault(r, "wrong argument count"); return empty_value(); }
    Frame local = {0}; local.parent = &r->global;
    for (size_t i = 0; i < e->argc && !r->error; i++) {
        Value arg = evaluate(r, frame, e->args[i]);
        bind(&local, function->parameters[i], arg, 0); free_value(arg);
    }
    execute_body(r, &local, function->body);
    Value result = r->returning ? r->returned : empty_value();
    r->returning = 0; r->returned = empty_value(); free_frame(&local); return result;
}
static Value evaluate(Runtime *r, Frame *frame, Expr *e) {
    if (!e || r->error) return empty_value();
    if (e->kind == 0) return clone_value(e->literal);
    if (e->kind == 1) {
        Binding *b = lookup(frame, e->text);
        if (!b) { fault(r, "undefined variable"); return empty_value(); }
        return clone_value(b->value);
    }
    if (e->kind == 5) {
        Value list = empty_value(); list.kind = V_LIST; list.count = e->argc;
        list.items = calloc(e->argc ? e->argc : 1, sizeof(*list.items));
        if (!list.items) { fault(r, "out of memory"); return empty_value(); }
        for (size_t i = 0; i < e->argc && !r->error; i++) {
            list.items[i] = evaluate(r, frame, e->args[i]);
            if (i && list.items[i].kind != list.items[0].kind) fault(r, "list elements must have the same type");
        }
        if (r->error) { free_value(list); return empty_value(); }
        return list;
    }
    if (e->kind == 6) {
        Value target = evaluate(r, frame, e->left);
        Value index = evaluate(r, frame, e->right);
        Value result = empty_value();
        if (target.kind != V_LIST || index.kind != V_NUMBER || index.number < 0 ||
            floor(index.number) != index.number || index.number >= (double)target.count)
            fault(r, "list index out of range or invalid");
        else result = clone_value(target.items[(size_t)index.number]);
        free_value(target); free_value(index); return result;
    }
    if (e->kind == 7) {
        Value object = evaluate(r, frame, e->left);
        Value result = empty_value();
        if (object.kind != V_OBJECT) fault(r, "member access requires object");
        else {
            size_t i = 0;
            for (; i < object.count; i++) if (strcmp(object.keys[i], e->text) == 0) break;
            if (i == object.count) fault(r, "missing object member");
            else result = clone_value(object.items[i]);
        }
        free_value(object); return result;
    }
    if (e->kind == 4) return call(r, frame, e);
    if (e->kind == 2) {
        Value right = evaluate(r, frame, e->right);
        Value result = empty_value();
        if (!strcmp(e->text, "MINUS") && right.kind == V_NUMBER) {
            result = number_value(-right.number); result.floating = right.floating;
        }
        else if ((!strcmp(e->text, "NOT") || !strcmp(e->text, "BANG")) && right.kind == V_BOOL) result = bool_value(!right.boolean);
        else fault(r, "invalid unary operand");
        free_value(right); return result;
    }
    Value left = evaluate(r, frame, e->left);
    if (r->error) { free_value(left); return empty_value(); }
    if (!strcmp(e->text, "AND") && left.kind == V_BOOL && !left.boolean) {
        free_value(left); return bool_value(0);
    }
    if (!strcmp(e->text, "OR") && left.kind == V_BOOL && left.boolean) {
        free_value(left); return bool_value(1);
    }
    Value right = evaluate(r, frame, e->right);
    if (r->error) { free_value(left); free_value(right); return empty_value(); }
    Value result = empty_value();
    const char *op = e->text;
    if (!strcmp(op, "PLUS") && left.kind == V_STRING && right.kind == V_STRING) {
        result.kind = V_STRING; result.string_length = left.string_length + right.string_length;
        result.string = malloc(result.string_length + 1);
        if (result.string) {
            memcpy(result.string, left.string, left.string_length);
            memcpy(result.string + left.string_length, right.string, right.string_length);
            result.string[result.string_length] = 0;
        }
    } else if (left.kind == V_NUMBER && right.kind == V_NUMBER) {
        double a = left.number, b = right.number;
        if (!strcmp(op, "PLUS")) result = number_value(a + b);
        else if (!strcmp(op, "MINUS")) result = number_value(a - b);
        else if (!strcmp(op, "STAR")) result = number_value(a * b);
        else if (!strcmp(op, "SLASH") && b != 0) result = floating_value(a / b);
        else if (!strcmp(op, "FLOOR_DIV") && b != 0) {
            result = number_value(floor(a / b)); result.floating = left.floating || right.floating;
        }
        else if (!strcmp(op, "PERCENT") && b != 0) {
            result = number_value(a - floor(a / b) * b); result.floating = left.floating || right.floating;
        }
        else if (!strcmp(op, "POWER")) result = (left.floating || right.floating || b < 0) ?
            floating_value(pow(a, b)) : number_value(pow(a, b));
        else if (!strcmp(op, "LESS")) result = bool_value(a < b);
        else if (!strcmp(op, "LESS_EQUAL")) result = bool_value(a <= b);
        else if (!strcmp(op, "GREATER")) result = bool_value(a > b);
        else if (!strcmp(op, "GREATER_EQUAL")) result = bool_value(a >= b);
        else if (!strcmp(op, "EQUAL_EQUAL")) result = bool_value(a == b);
        else if (!strcmp(op, "BANG_EQUAL")) result = bool_value(a != b);
        else fault(r, "invalid numeric operation");
        if (result.kind == V_NUMBER && (!strcmp(op, "PLUS") || !strcmp(op, "MINUS") || !strcmp(op, "STAR")))
            result.floating = left.floating || right.floating;
    } else if (left.kind == V_BOOL && right.kind == V_BOOL) {
        if (!strcmp(op, "AND")) result = bool_value(left.boolean && right.boolean);
        else if (!strcmp(op, "OR")) result = bool_value(left.boolean || right.boolean);
        else if (!strcmp(op, "EQUAL_EQUAL")) result = bool_value(left.boolean == right.boolean);
        else if (!strcmp(op, "BANG_EQUAL")) result = bool_value(left.boolean != right.boolean);
        else fault(r, "invalid boolean operation");
    } else if (left.kind == V_STRING && right.kind == V_STRING) {
        int equal = same_value(left, right);
        if (!strcmp(op, "EQUAL_EQUAL")) result = bool_value(equal);
        else if (!strcmp(op, "BANG_EQUAL")) result = bool_value(!equal);
        else fault(r, "invalid string operation");
    } else fault(r, "incompatible operand types");
    free_value(left); free_value(right); return result;
}

static void print_value(FILE *out, Value v) {
    if (v.kind == V_NUMBER) { char text[64]; format_number(text, sizeof(text), v); fputs(text, out); }
    else if (v.kind == V_STRING && v.string) fwrite(v.string, 1, v.string_length, out);
    else if (v.kind == V_BOOL) fputs(v.boolean ? "true" : "false", out);
    else if (v.kind == V_BYTES) {
        fputs("0x", out);
        for (size_t i = 0; i < v.string_length; i++) fprintf(out, "%02x", (unsigned char)v.string[i]);
    }
    else if (v.kind == V_LIST) {
        fputc('[', out);
        for (size_t i = 0; i < v.count; i++) {
            if (i) fputs(", ", out);
            print_value(out, v.items[i]);
        }
        fputc(']', out);
    }
    else if (v.kind == V_OBJECT) {
        fputs("object:", out);
        for (size_t i = 0; i < v.count; i++) {
            if (i) fputs(", ", out);
            fputs(v.keys[i], out); fputc('=', out); print_value(out, v.items[i]);
        }
    }
    else fputs("EMPTY", out);
}
static void execute_body(Runtime *r, Frame *frame, Body body) {
    for (size_t i = 0; i < body.count && !r->error && !r->returning; i++) {
        if (++r->steps > 1000000) { fault(r, "execution limit exceeded"); break; }
        Stmt *s = body.items[i];
        if (s->kind == 5) continue;
        if (s->kind == 10) {
            Value list = empty_value(); list.kind = V_LIST; list.count = s->body.count;
            list.items = calloc(list.count ? list.count : 1, sizeof(*list.items));
            if (!list.items) { fault(r, "out of memory"); continue; }
            for (size_t j = 0; j < list.count && !r->error; j++) {
                Stmt *element = s->body.items[j];
                if (element->kind != 6) { fault(r, "list block requires values"); break; }
                list.items[j] = evaluate(r, frame, element->expr);
                if (j && list.items[j].kind != list.items[0].kind)
                    fault(r, "list elements must have the same type");
            }
            if (!r->error && !bind(frame, s->name, list, 0)) fault(r, "cannot declare list");
            free_value(list); continue;
        }
        if (s->kind == 9) {
            Frame fields = {0}; fields.parent = frame;
            execute_body(r, &fields, s->body);
            if (!r->error) {
                Value object = empty_value(); object.kind = V_OBJECT; object.count = fields.count;
                object.items = calloc(object.count ? object.count : 1, sizeof(*object.items));
                object.keys = calloc(object.count ? object.count : 1, sizeof(*object.keys));
                if (!object.items || !object.keys) fault(r, "out of memory");
                else {
                    for (size_t j = 0; j < object.count; j++) {
                        object.keys[j] = copy_text(fields.bindings[j].name);
                        object.items[j] = clone_value(fields.bindings[j].value);
                    }
                    if (!bind(frame, s->name, object, 0)) fault(r, "cannot declare object");
                }
                free_value(object);
            }
            free_frame(&fields); continue;
        }
        if (s->kind == 7) {
            Value values = evaluate(r, frame, s->expr);
            if (values.kind != V_LIST) fault(r, "for requires a list");
            else for (size_t j = 0; j < values.count && !r->error && !r->returning; j++) {
                if (!bind(frame, s->parameters[0], values.items[j], 0)) { fault(r, "cannot assign loop variable"); break; }
                execute_body(r, frame, s->body);
            }
            free_value(values); continue;
        }
        if (s->kind == 3 || s->kind == 4) {
            do {
                Value condition = evaluate(r, frame, s->expr);
                if (condition.kind != V_BOOL) { fault(r, "condition must be boolean"); free_value(condition); break; }
                int true_branch = condition.boolean; free_value(condition);
                if (true_branch) execute_body(r, frame, s->body);
                else if (s->kind == 3) execute_body(r, frame, s->other);
                if (!true_branch || s->kind == 3 || r->returning || r->error) break;
            } while (1);
            continue;
        }
        Value value = s->expr ? evaluate(r, frame, s->expr) : empty_value();
        if (r->error) { free_value(value); break; }
        if (value.kind == V_VOID && s->kind != 6) {
            fault(r, "VOID value cannot be used"); free_value(value); break;
        }
        if (s->kind == 0 || s->kind == 8) {
            Binding *existing = lookup_local(frame, s->name);
            if (existing && existing->constant) fault(r, "constant cannot be reassigned");
            else if (existing && existing->value.kind != value.kind) fault(r, "variable type cannot change");
            else if (!bind(frame, s->name, value, s->kind == 8)) fault(r, "cannot declare or assign variable");
        } else if (s->kind == 1) { print_value(r->output, value); fputc('\n', r->output); }
        else if (s->kind == 2) { r->returning = 1; r->returned = clone_value(value); }
        free_value(value);
    }
}

static int separan_run_source_at(const char *source, const separan_runtime_options *options,
                                 FILE *output, FILE *errors) {
    Runtime r = {0}; r.output = output ? output : stdout; r.errors = errors ? errors : stderr;
    r.read_files = options->read_files;
    r.write_files = options->write_files;
    r.discover_paths = options->discover_paths;
    if (separan_files_init(&r.files, options->root ? options->root : ".")) {
        fprintf(r.errors, "SEPARAN E721: invalid capability root\n"); return 1;
    }
    if (separan_lex(source, &r.tokens)) {
        fprintf(r.errors, "Separan C: %s at line %zu, column %zu\n",
                r.tokens.error_code, r.tokens.error_line, r.tokens.error_column);
        separan_tokens_free(&r.tokens); separan_files_free(&r.files); return 1;
    }
    r.program = parse_body(&r, NULL, NULL);
    if (!r.error) {
        execute_body(&r, &r.global, r.program);
        if (!r.error) {
            Stmt *main_function = find_function(&r, "main");
            if (main_function) {
                Expr call_main = {0}; call_main.kind = 4; call_main.text = "main";
                Value value = call(&r, &r.global, &call_main); free_value(value);
            }
        }
    }
    free_value(r.returned); free_frame(&r.global); free_body(r.program);
    separan_tokens_free(&r.tokens); separan_files_free(&r.files);
    return r.error ? 1 : 0;
}

int separan_run_source(const char *source, FILE *output, FILE *errors) {
    separan_runtime_options options = {".", 1, 1, 1};
    return separan_run_source_at(source, &options, output, errors);
}

int separan_run_source_with_options(const char *source, const separan_runtime_options *options,
                                    FILE *output, FILE *errors) {
    if (!options) return 1;
    return separan_run_source_at(source, options, output, errors);
}

int separan_run_path(const char *path, FILE *output, FILE *errors) {
    FILE *file = fopen(path, "rb");
    if (!file) { fprintf(errors ? errors : stderr, "Cannot open %s\n", path); return 1; }
    if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return 1; }
    long size = ftell(file);
    if (size < 0 || fseek(file, 0, SEEK_SET) != 0) { fclose(file); return 1; }
    char *source = malloc((size_t)size + 1);
    if (!source) { fclose(file); return 1; }
    size_t count = fread(source, 1, (size_t)size, file); fclose(file);
    source[count] = 0;
    const char *last_slash = strrchr(path, '/');
    const char *last_backslash = strrchr(path, '\\');
    const char *last = last_slash;
    if (last_backslash && (!last || last_backslash > last)) last = last_backslash;
    char *root = NULL;
    if (last) {
        size_t length = (size_t)(last - path);
        if (length == 0 || (length == 2 && path[1] == ':')) length++;
        root = malloc(length + 1);
        if (root) { memcpy(root, path, length); root[length] = 0; }
    }
    separan_runtime_options options = {root && *root ? root : ".", 1, 1, 1};
    int status = separan_run_source_at(source, &options, output, errors);
    free(root);
    free(source); return status;
}
