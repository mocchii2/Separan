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
    if (separan_lex("function:main\nend_function:main\n", &result) != 0) return 4;
    if (strcmp(result.tokens[0].type, "IDENTIFIER") != 0 ||
        strcmp(result.tokens[4].type, "IDENTIFIER") != 0) return 5;
    separan_tokens_free(&result);

    const char *unicode =
        "SEP:main\n"
        "@通知:処理\n"
        "if true :日本語\n"
        "endif:日本語\n"
        "##説明\n"
        "ignored\n"
        "##説明\n"
        "END_SEP:main\n";
    if (separan_lex(unicode, &result) != 0) return 6;
    if (strcmp(result.tokens[4].type, "TAG") != 0 ||
        strcmp(result.tokens[4].lexeme, "通知:処理") != 0) return 7;
    separan_tokens_free(&result);

    if (separan_lex("SEP:main\nif true :cafe\xCC\x81\n", &result) == 0 ||
        strcmp(result.error_code, "E102") != 0) return 8;
    separan_tokens_free(&result);
    if (separan_lex("SEP:main\n@通知:cafe\xCC\x81\n", &result) == 0 ||
        strcmp(result.error_code, "E216") != 0) return 9;
    separan_tokens_free(&result);
    /* U+0338 is a valid identifier continuation and is already NFC here. */
    if (separan_lex("SEP:main\n@a\xCC\xB8\nEND_SEP:main\n", &result) != 0) return 10;
    separan_tokens_free(&result);
    if (separan_lex("SEP:\xF0\x9F\x98\x80\n", &result) == 0 ||
        strcmp(result.error_code, "E100") != 0) return 11;
    separan_tokens_free(&result);
    puts("lexer_api: ok");
    return 0;
}
