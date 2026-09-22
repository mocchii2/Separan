#ifndef SEPARAN_LEXER_H
#define SEPARAN_LEXER_H

#include <stddef.h>

typedef struct {
    const char *type;
    char *lexeme;
    size_t line;
    size_t column;
} separan_token;

typedef struct {
    separan_token *tokens;
    size_t count;
    char error_code[8];
    size_t error_line;
    size_t error_column;
} separan_tokens;

/* Returns zero on success. The caller owns the result and must free it. */
int separan_lex(const char *source, separan_tokens *result);
void separan_tokens_free(separan_tokens *result);

#endif
