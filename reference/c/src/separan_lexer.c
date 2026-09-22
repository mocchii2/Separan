#include "separan_lexer.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

typedef struct { const char *spelling; const char *type; } Entry;

static const Entry keywords[] = {
    {"function", "FUNCTION"}, {"sep", "FUNCTION"}, {"end_function", "END_FUNCTION"},
    {"end_sep", "END_FUNCTION"}, {"if", "IF"}, {"elseif", "ELSEIF"},
    {"else", "ELSE"}, {"endif", "ENDIF"}, {"while", "WHILE"},
    {"endwhile", "ENDWHILE"}, {"for", "FOR"}, {"in", "IN"},
    {"endfor", "ENDFOR"}, {"print", "PRINT"}, {"print_error", "PRINT_ERROR"},
    {"return", "RETURN"}, {"const", "CONST"}, {"not", "NOT"}, {"is", "IS"},
    {"object", "OBJECT"}, {"end_object", "END_OBJECT"}, {"list", "LIST"},
    {"end_list", "END_LIST"}, {"import", "IMPORT"}, {"as", "AS"},
    {"try", "TRY"}, {"catch", "CATCH"}, {"finally", "FINALLY"},
    {"endtry", "ENDTRY"}, {"throw", "THROW"}, {"error", "ERROR"},
    {"end_error", "END_ERROR"}, {"http_route", "HTTP_ROUTE"},
    {"end_http_route", "END_HTTP_ROUTE"}, {"transaction", "TRANSACTION"},
    {"end_transaction", "END_TRANSACTION"}, {"true", "TRUE"}, {"false", "FALSE"},
    {"EMPTY", "EMPTY"}, {"EMPTYS", "EMPTYS"}, {"front", "FRONT"}, {"back", "BACK"}
};

static const Entry operators[] = {
    {"//=", "FLOOR_DIV_EQUAL"}, {"**=", "POWER_EQUAL"},
    {"==", "EQUAL_EQUAL"}, {"!=", "BANG_EQUAL"}, {">=", "GREATER_EQUAL"},
    {"<=", "LESS_EQUAL"}, {"&&", "AND"}, {"||", "OR"}, {"**", "POWER"},
    {"//", "FLOOR_DIV"}, {"??", "EMPTY_COALESCE"}, {"+=", "PLUS_EQUAL"},
    {"-=", "MINUS_EQUAL"}, {"*=", "STAR_EQUAL"}, {"/=", "SLASH_EQUAL"},
    {"%=", "PERCENT_EQUAL"}, {"+", "PLUS"}, {"-", "MINUS"},
    {"*", "STAR"}, {"/", "SLASH"}, {"%", "PERCENT"}, {"=", "EQUAL"},
    {"!", "BANG"}, {">", "GREATER"}, {"<", "LESS"}, {"(", "LPAREN"},
    {")", "RPAREN"}, {"[", "LBRACKET"}, {"]", "RBRACKET"},
    {",", "COMMA"}, {":", "COLON"}, {".", "DOT"}
};

static int append(separan_tokens *result, const char *type, const char *start,
                  size_t length, size_t line, size_t column) {
    separan_token *next = realloc(result->tokens, (result->count + 1) * sizeof(*next));
    if (!next) return 0;
    result->tokens = next;
    separan_token *token = &next[result->count];
    token->lexeme = malloc(length + 1);
    if (!token->lexeme) return 0;
    memcpy(token->lexeme, start, length);
    token->lexeme[length] = '\0';
    token->type = type;
    token->line = line;
    token->column = column;
    result->count++;
    return 1;
}

static int fail(separan_tokens *result, const char *code, size_t line, size_t column) {
    memcpy(result->error_code, code, strlen(code) + 1);
    result->error_line = line;
    result->error_column = column;
    return 1;
}

static int name_start(unsigned char c) { return isalpha(c) || c == '_'; }
static int name_part(unsigned char c) { return isalnum(c) || c == '_'; }
static int utf8_next(const char *text, size_t length, size_t at, size_t *width, unsigned *codepoint) {
    unsigned char lead = (unsigned char)text[at];
    if (lead < 0x80) { *width = 1; *codepoint = lead; return 1; }
    size_t count = lead >= 0xF0 && lead <= 0xF4 ? 4 :
                   lead >= 0xE0 && lead <= 0xEF ? 3 :
                   lead >= 0xC2 && lead <= 0xDF ? 2 : 0;
    if (!count || at + count > length) return 0;
    unsigned value = lead & ((1u << (7 - count)) - 1u);
    for (size_t i = 1; i < count; i++) {
        unsigned char part = (unsigned char)text[at + i];
        if ((part & 0xC0) != 0x80) return 0;
        value = (value << 6) | (part & 0x3F);
    }
    if ((count == 2 && value < 0x80) || (count == 3 && value < 0x800) ||
        (count == 4 && value < 0x10000) || value > 0x10FFFF ||
        (value >= 0xD800 && value <= 0xDFFF)) return 0;
    *width = count; *codepoint = value; return 1;
}
static size_t unicode_column(const char *line, size_t byte_offset) {
    size_t column = 1;
    for (size_t i = 0; i < byte_offset; i++)
        if (((unsigned char)line[i] & 0xC0) != 0x80) column++;
    return column;
}

static const char *keyword_type(const char *start, size_t length) {
    for (size_t i = 0; i < sizeof(keywords) / sizeof(*keywords); i++) {
        const char *word = keywords[i].spelling;
        if (strlen(word) != length) continue;
        if ((strcmp(word, "EMPTY") == 0 || strcmp(word, "EMPTYS") == 0) &&
            memcmp(start, word, length) != 0) continue;
        size_t j = 0;
        for (; j < length; j++) {
            if (tolower((unsigned char)start[j]) != tolower((unsigned char)word[j])) break;
        }
        if (j == length) return keywords[i].type;
    }
    return "IDENTIFIER";
}

static int digits_valid(const char *start, size_t length, const char *allowed) {
    if (!length || start[0] == '_' || start[length - 1] == '_') return 0;
    for (size_t i = 0; i < length; i++) {
        if (start[i] == '_') {
            if (i && start[i - 1] == '_') return 0;
        } else if (!strchr(allowed, start[i])) return 0;
    }
    return 1;
}

void separan_tokens_free(separan_tokens *result) {
    if (!result) return;
    for (size_t i = 0; i < result->count; i++) free(result->tokens[i].lexeme);
    free(result->tokens);
    memset(result, 0, sizeof(*result));
}

int separan_lex(const char *source, separan_tokens *result) {
    if (!result) return 1;
    memset(result, 0, sizeof(*result));
    if (!source) return fail(result, "E000", 0, 0);
    const char *cursor = source;
    size_t line = 1;
    int in_comment = 0;
    char *comment_label = NULL;
    while (*cursor) {
        const char *start = cursor;
        while (*cursor && *cursor != '\n' && *cursor != '\r') cursor++;
        size_t length = (size_t)(cursor - start);
        size_t offset = 0;
        size_t newline_column = in_comment ? 1 : length + 1;
        while (offset < length && (start[offset] == ' ' || start[offset] == '\t')) offset++;
        if (offset + 2 <= length && start[offset] == '#' && start[offset + 1] == '#') {
            size_t end = length;
            while (end > offset + 2 && (start[end - 1] == ' ' || start[end - 1] == '\t')) end--;
            size_t label_length = end - offset - 2;
            int delimiter = 1;
            for (size_t j = offset + 2; j < end;) {
                unsigned char part = (unsigned char)start[j];
                if (part < 0x80) { if (!name_part(part)) delimiter = 0; j++; }
                else {
                    size_t width; unsigned codepoint;
                    if (!utf8_next(start, end, j, &width, &codepoint) ||
                        (codepoint >= 0x300 && codepoint <= 0x36F)) { delimiter = 0; break; }
                    j += width;
                }
            }
            if (label_length && (unsigned char)start[offset + 2] < 0x80 &&
                !name_start((unsigned char)start[offset + 2])) delimiter = 0;
            if (delimiter) {
                newline_column = unicode_column(start, offset);
                if (!in_comment) {
                    comment_label = malloc(label_length + 1);
                    if (!comment_label) goto memory_error;
                    memcpy(comment_label, start + offset + 2, label_length);
                    comment_label[label_length] = '\0';
                    in_comment = 1;
                } else if (strlen(comment_label) == label_length &&
                           memcmp(comment_label, start + offset + 2, label_length) == 0) {
                    free(comment_label); comment_label = NULL; in_comment = 0;
                } else {
                    free(comment_label);
                    return fail(result, "E104", line, offset + 1);
                }
            }
        }
        if (!in_comment && !(offset + 2 <= length && start[offset] == '#' && start[offset + 1] == '#')) {
            size_t i = 0;
            while (i < length) {
                unsigned char c = (unsigned char)start[i];
                if (c == ' ' || c == '\t') { i++; continue; }
                if (c == '#') break;
                size_t first = i;
                const char *type = NULL;
                if (c == '@') {
                    i++;
                    if (i >= length || !name_start((unsigned char)start[i])) {
                        free(comment_label); return fail(result, "E216", line, first + 1);
                    }
                    while (i < length && (name_part((unsigned char)start[i]) || start[i] == ':')) i++;
                    type = "TAG";
                    first++;
                } else if (c == '"' || (c == 'r' && i + 1 < length && start[i + 1] == '"')) {
                    int raw = c == 'r';
                    i += raw ? 2 : 1;
                    while (i < length && start[i] != '"') {
                        if (!raw && start[i] == '\\') {
                            i++;
                            if (i >= length) { free(comment_label); return fail(result, "E219", line, i); }
                            if (!strchr("nrt0\"\\uU", start[i])) {
                                free(comment_label); return fail(result, "E219", line, i);
                            }
                            if (start[i] == 'u' || start[i] == 'U') {
                                size_t digits = start[i] == 'u' ? 4 : 8;
                                if (i + digits >= length) { free(comment_label); return fail(result, "E220", line, i); }
                                unsigned codepoint = 0;
                                for (size_t j = 1; j <= digits; j++) if (!isxdigit((unsigned char)start[i + j])) {
                                    free(comment_label); return fail(result, "E220", line, i);
                                }
                                for (size_t j = 1; j <= digits; j++) {
                                    char part = start[i + j];
                                    codepoint = (codepoint << 4) | (unsigned)(part >= '0' && part <= '9' ? part - '0' :
                                        part >= 'a' && part <= 'f' ? part - 'a' + 10 : part - 'A' + 10);
                                }
                                if (codepoint > 0x10FFFF || (codepoint >= 0xD800 && codepoint <= 0xDFFF)) {
                                    free(comment_label); return fail(result, "E220", line, i);
                                }
                                i += digits;
                            }
                        }
                        i++;
                    }
                    if (i >= length) { free(comment_label); return fail(result, "E103", line, first + 1); }
                    i++; type = "STRING";
                } else if (isdigit(c)) {
                    const char *allowed = "0123456789";
                    size_t digits_start = i;
                    if (c == '0' && i + 1 < length) {
                        unsigned char marker = (unsigned char)tolower((unsigned char)start[i + 1]);
                        if (marker == 'b' || marker == 'o' || marker == 'x') {
                            allowed = marker == 'b' ? "01" : marker == 'o' ? "01234567" : "0123456789abcdefABCDEF";
                            i += 2; digits_start = i;
                            while (i < length && (isalnum((unsigned char)start[i]) || start[i] == '_' || start[i] == '.')) i++;
                        }
                    }
                    if (digits_start == first) {
                        while (i < length && (isdigit((unsigned char)start[i]) || start[i] == '_')) i++;
                        if (!digits_valid(start + first, i - first, allowed)) {
                            free(comment_label); return fail(result, "E101", line, first + 1);
                        }
                        if (i < length && start[i] == '.') {
                            i++; size_t fraction = i;
                            while (i < length && (isdigit((unsigned char)start[i]) || start[i] == '_')) i++;
                            if (!digits_valid(start + fraction, i - fraction, allowed)) {
                                free(comment_label); return fail(result, "E101", line, first + 1);
                            }
                        }
                    } else if (!digits_valid(start + digits_start, i - digits_start, allowed)) {
                        free(comment_label); return fail(result, "E101", line, first + 1);
                    }
                    type = "NUMBER";
                } else if (name_start(c) || c >= 0x80) {
                    int non_ascii = 0;
                    while (i < length) {
                        unsigned char part = (unsigned char)start[i];
                        if (part < 0x80) { if (!name_part(part)) break; i++; }
                        else {
                            size_t width; unsigned codepoint;
                            if (!utf8_next(start, length, i, &width, &codepoint)) {
                                free(comment_label); return fail(result, "E101", line, unicode_column(start, i));
                            }
                            if (codepoint >= 0x300 && codepoint <= 0x36F) {
                                free(comment_label); return fail(result, "E102", line, unicode_column(start, first));
                            }
                            non_ascii = 1; i += width;
                        }
                    }
                    int after_colon = result->count &&
                        !strcmp(result->tokens[result->count - 1].type, "COLON");
                    if (non_ascii && !after_colon) {
                        free(comment_label); return fail(result, "E101", line, unicode_column(start, first));
                    }
                    type = non_ascii ? "LABEL" : keyword_type(start + first, i - first);
                    if ((i - first == 4 && memcmp(start + first, "null", 4) == 0) ||
                        (i - first == 4 && memcmp(start + first, "NULL", 4) == 0)) {
                        free(comment_label); return fail(result, "E135", line, first + 1);
                    }
                } else {
                    for (size_t j = 0; j < sizeof(operators) / sizeof(*operators); j++) {
                        size_t width = strlen(operators[j].spelling);
                        if (i + width <= length && memcmp(start + i, operators[j].spelling, width) == 0) {
                            type = operators[j].type; i += width; break;
                        }
                    }
                    if (!type) { free(comment_label); return fail(result, "E100", line, first + 1); }
                }
                if (!append(result, type, start + first, i - first, line,
                            unicode_column(start, first))) goto memory_error;
            }
        }
        if (!append(result, "NEWLINE", "\n", 1, line,
                    newline_column == length + 1 ? unicode_column(start, length) : newline_column)) goto memory_error;
        if (*cursor == '\r') cursor++;
        if (*cursor == '\n') cursor++;
        line++;
    }
    if (in_comment) { free(comment_label); return fail(result, "E106", line - 1, 1); }
    if (!append(result, "EOF", "", 0, line, 1)) goto memory_error;
    return 0;
memory_error:
    free(comment_label);
    return fail(result, "E000", line, 1);
}
