#include "separan_lexer.h"

#include <stdio.h>
#include <string.h>

int main(void) {
    separan_tokens result;
    const char *source = "SEP:main\nvalue = 0x2a + 1_000\nprint r\"ok\"\nEND_SEP:main\n";
    if (separan_lex(source, &result) != 0) return 1;
    const char *expected[] = {
        "FUNCTION", "COLON", "IDENTIFIER", "NEWLINE", "IDENTIFIER", "EQUAL",
        "NUMBER", "PLUS", "NUMBER", "NEWLINE", "PRINT", "STRING", "NEWLINE",
        "END_FUNCTION", "COLON", "IDENTIFIER", "NEWLINE", "EOF"
    };
    if (result.count != sizeof(expected) / sizeof(*expected)) return 2;
    for (size_t i = 0; i < result.count; i++) {
        if (strcmp(result.tokens[i].type, expected[i]) != 0) return 3;
    }
    separan_tokens_free(&result);
    puts("lexer_api: ok");
    return 0;
}
