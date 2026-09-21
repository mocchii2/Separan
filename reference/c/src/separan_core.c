#include "separan_core.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SEPARAN_MAX_BLOCKS 1024

typedef enum {
    BLOCK_NONE = 0,
    BLOCK_SEP,
    BLOCK_FUNCTION,
    BLOCK_IF,
    BLOCK_WHILE,
    BLOCK_FOR,
    BLOCK_OBJECT,
    BLOCK_LIST,
    BLOCK_TRY,
    BLOCK_ERROR,
    BLOCK_HTTP_ROUTE,
    BLOCK_TRANSACTION
} BlockKind;

typedef struct {
    BlockKind kind;
    char *label;
    int line_number;
} OpenBlock;

typedef struct {
    OpenBlock entries[SEPARAN_MAX_BLOCKS];
    size_t count;
} BlockStack;

static const char *block_kind_name(BlockKind kind) {
    switch (kind) {
        case BLOCK_SEP: return "SEP";
        case BLOCK_FUNCTION: return "function";
        case BLOCK_IF: return "if";
        case BLOCK_WHILE: return "while";
        case BLOCK_FOR: return "for";
        case BLOCK_OBJECT: return "object";
        case BLOCK_LIST: return "list";
        case BLOCK_TRY: return "try";
        case BLOCK_ERROR: return "error";
        case BLOCK_HTTP_ROUTE: return "http_route";
        case BLOCK_TRANSACTION: return "transaction";
        default: return "block";
    }
}

static const char *closer_for_kind(BlockKind kind) {
    switch (kind) {
        case BLOCK_SEP: return "END_SEP";
        case BLOCK_FUNCTION: return "end_function";
        case BLOCK_IF: return "endif";
        case BLOCK_WHILE: return "endwhile";
        case BLOCK_FOR: return "endfor";
        case BLOCK_OBJECT: return "end_object";
        case BLOCK_LIST: return "end_list";
        case BLOCK_TRY: return "endtry";
        case BLOCK_ERROR: return "end_error";
        case BLOCK_HTTP_ROUTE: return "end_http_route";
        case BLOCK_TRANSACTION: return "end_transaction";
        default: return "end";
    }
}

static char *duplicate_string(const char *text) {
    if (text == NULL) {
        return NULL;
    }
    size_t length = strlen(text);
    char *copy = (char *)malloc(length + 1U);
    if (copy == NULL) {
        return NULL;
    }
    memcpy(copy, text, length + 1U);
    return copy;
}

static char *trim_in_place(char *text) {
    while (*text != '\0' && (*text == ' ' || *text == '\t')) {
        text++;
    }
    if (*text == '\0') {
        return text;
    }

    char *end = text + strlen(text) - 1;
    while (end > text && (*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n')) {
        *end = '\0';
        end--;
    }
    return text;
}

static int starts_with_keyword(const char *text, const char *keyword) {
    size_t len = strlen(keyword);
    if (strncmp(text, keyword, len) != 0) {
        return 0;
    }
    return 1;
}

static char *label_after_prefix(const char *text, const char *prefix) {
    size_t prefix_len = strlen(prefix);
    const char *cursor = text + prefix_len;
    while (*cursor == ' ' || *cursor == '\t') {
        cursor++;
    }
    if (*cursor == ':') {
        cursor++;
    }
    while (*cursor == ' ' || *cursor == '\t') {
        cursor++;
    }
    if (*cursor == '\0') {
        return NULL;
    }

    const char *end = cursor;
    while (*end != '\0' && *end != ' ' && *end != '\t' && *end != '\n' && *end != '\r') {
        end++;
    }
    size_t len = (size_t)(end - cursor);
    char *copy = (char *)malloc(len + 1U);
    if (copy == NULL) {
        return NULL;
    }
    memcpy(copy, cursor, len);
    copy[len] = '\0';
    return copy;
}

static char *last_label_from_line(const char *text) {
    const char *colon = strrchr(text, ':');
    if (colon == NULL || colon[1] == '\0') {
        return NULL;
    }
    const char *cursor = colon + 1;
    while (*cursor == ' ' || *cursor == '\t') {
        cursor++;
    }
    if (*cursor == '\0') {
        return NULL;
    }
    const char *end = cursor;
    while (*end != '\0' && *end != ' ' && *end != '\t' && *end != '\n' && *end != '\r') {
        end++;
    }
    size_t len = (size_t)(end - cursor);
    char *copy = (char *)malloc(len + 1U);
    if (copy == NULL) {
        return NULL;
    }
    memcpy(copy, cursor, len);
    copy[len] = '\0';
    return copy;
}

static int is_valid_label_text(const char *text) {
    if (text == NULL || *text == '\0') {
        return 0;
    }
    for (const unsigned char *cursor = (const unsigned char *)text; *cursor != '\0'; cursor++) {
        if (*cursor == '_' || *cursor == ':' || isalnum(*cursor)) {
            continue;
        }
        if (*cursor >= 0x80) {
            continue;
        }
        return 0;
    }
    return 1;
}

static separan_result g_last_result = {0};

static void reset_result(separan_result *result) {
    if (result == NULL) {
        return;
    }
    result->ok = 1;
    result->error_count = 0U;
    for (size_t index = 0; index < SEPARAN_MAX_ERRORS; index++) {
        result->errors[index].line_number = 0;
        result->errors[index].code[0] = '\0';
        result->errors[index].title[0] = '\0';
        result->errors[index].expected[0] = '\0';
        result->errors[index].actual[0] = '\0';
    }
}

static void record_error(const char *code, const char *title, int line_number, const char *expected, const char *actual) {
    if (code == NULL || title == NULL) {
        return;
    }

    if (g_last_result.error_count < SEPARAN_MAX_ERRORS) {
        separan_error *entry = &g_last_result.errors[g_last_result.error_count++];
        entry->line_number = line_number;
        snprintf(entry->code, sizeof(entry->code), "%s", code);
        snprintf(entry->title, sizeof(entry->title), "%s", title);
        if (expected != NULL) {
            snprintf(entry->expected, sizeof(entry->expected), "%s", expected);
        }
        if (actual != NULL) {
            snprintf(entry->actual, sizeof(entry->actual), "%s", actual);
        }
    }

    g_last_result.ok = 0;

    fprintf(stderr, "SEPARAN %s: %s\n\n", code, title);
    fprintf(stderr, " --> line:%d\n", line_number);
    if (expected != NULL && actual != NULL) {
        fprintf(stderr, "  expected: %s\n", expected);
        fprintf(stderr, "  actual:   %s\n", actual);
    }
}

static void print_error(const char *code, const char *title, int line_number, const char *expected, const char *actual) {
    record_error(code, title, line_number, expected, actual);
}

static void push_block(BlockStack *stack, BlockKind kind, const char *label, int line_number) {
    if (stack->count >= SEPARAN_MAX_BLOCKS) {
        print_error("E106", "Unclosed block", line_number, "a valid block closer", label ? label : "<unknown>");
        exit(1);
    }

    for (size_t index = 0; index < stack->count; index++) {
        if (strcmp(stack->entries[index].label, label) == 0) {
            print_error("E109", "Duplicate open label", line_number, block_kind_name(stack->entries[index].kind), label);
            exit(1);
        }
    }

    OpenBlock *slot = &stack->entries[stack->count++];
    slot->kind = kind;
    slot->label = duplicate_string(label);
    slot->line_number = line_number;
}

static int pop_block(BlockStack *stack, BlockKind kind, const char *label, int line_number) {
    if (stack->count == 0) {
        print_error("E107", "Unexpected block closer", line_number, closer_for_kind(kind), label);
        return 1;
    }

    OpenBlock *top = &stack->entries[stack->count - 1];
    if (strcmp(top->label, label) != 0) {
        print_error("E104", "Block label mismatch", line_number, top->label, label);
        return 1;
    }
    if (top->kind != kind) {
        print_error("E105", "Block kind mismatch", line_number, block_kind_name(top->kind), label);
        return 1;
    }

    free(top->label);
    stack->count--;
    return 0;
}

static int handle_branch(BlockStack *stack, const char *line, int line_number, const char *branch_name) {
    if (stack->count == 0) {
        print_error("E107", "Unexpected block closer", line_number, branch_name, line);
        return 1;
    }

    OpenBlock *top = &stack->entries[stack->count - 1];
    if (top->kind != BLOCK_IF) {
        print_error("E107", "Unexpected block closer", line_number, closer_for_kind(top->kind), line);
        return 1;
    }

    char *label = NULL;
    if (starts_with_keyword(line, "else:")) {
        label = label_after_prefix(line, "else");
    } else if (starts_with_keyword(line, "elseif")) {
        label = label_after_prefix(line, "elseif");
    } else {
        return 0;
    }

    if (label == NULL || strcmp(top->label, label) != 0) {
        print_error("E104", "Block label mismatch", line_number, top->label, label ? label : "<missing>");
        free(label);
        return 1;
    }
    free(label);
    return 0;
}

static int handle_open_block(BlockStack *stack, BlockKind kind, const char *line, int line_number) {
    char *label = last_label_from_line(line);
    if (label == NULL || !is_valid_label_text(label)) {
        free(label);
        print_error("E104", "Block label mismatch", line_number, "a valid label", line);
        return 1;
    }

    push_block(stack, kind, label, line_number);
    free(label);
    return 0;
}

static int handle_close_block(BlockStack *stack, BlockKind kind, const char *line, int line_number) {
    char *label = last_label_from_line(line);
    if (label == NULL || !is_valid_label_text(label)) {
        free(label);
        print_error("E104", "Block label mismatch", line_number, "a valid label", line);
        return 1;
    }

    int result = pop_block(stack, kind, label, line_number);
    free(label);
    return result;
}

static char *strip_leading_comment(char *text) {
    int in_string = 0;
    int escaped = 0;
    for (char *cursor = text; *cursor != '\0'; cursor++) {
        if (in_string) {
            if (escaped) {
                escaped = 0;
            } else if (*cursor == '\\') {
                escaped = 1;
            } else if (*cursor == '"') {
                in_string = 0;
            }
            continue;
        }

        if (*cursor == '"') {
            in_string = 1;
        } else if (*cursor == '#') {
            *cursor = '\0';
            return text;
        }
    }
    return text;
}

static int handle_multiline_comment(BlockStack *stack, char *trimmed, int line_number, int *in_multiline_comment, char **comment_label) {
    (void)stack;
    if (starts_with_keyword(trimmed, "##")) {
        char *after = trimmed + 2;
        while (*after == ' ' || *after == '\t') {
            after++;
        }
        if (*after == '\0') {
            if (*in_multiline_comment) {
                free(*comment_label);
                *comment_label = NULL;
                *in_multiline_comment = 0;
            } else {
                *comment_label = duplicate_string("");
                *in_multiline_comment = 1;
            }
            return 1;
        }

        char *cursor = after;
        while (*cursor != '\0' && *cursor != ' ' && *cursor != '\t' && *cursor != '\n' && *cursor != '\r') {
            cursor++;
        }
        if (*cursor != '\0') {
            *cursor = '\0';
        }

        if (*in_multiline_comment) {
            if (strcmp(after, *comment_label) == 0) {
                free(*comment_label);
                *comment_label = NULL;
                *in_multiline_comment = 0;
            } else {
                print_error("E104", "Multiline comment label mismatch", line_number, *comment_label, after);
                return 1;
            }
        } else {
            *comment_label = duplicate_string(after);
            *in_multiline_comment = 1;
        }
        return 1;
    }

    if (*in_multiline_comment) {
        return 1;
    }
    return 0;
}

static int parse_line(BlockStack *stack, char *trimmed, int line_number, int *in_multiline_comment, char **comment_label) {
    if (handle_multiline_comment(stack, trimmed, line_number, in_multiline_comment, comment_label)) {
        return 0;
    }

    if (*trimmed == '\0') {
        return 0;
    }

    if (starts_with_keyword(trimmed, "SEP:")) {
        return handle_open_block(stack, BLOCK_SEP, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "function:")) {
        return handle_open_block(stack, BLOCK_FUNCTION, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "END_SEP:")) {
        return handle_close_block(stack, BLOCK_SEP, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "end_function:")) {
        return handle_close_block(stack, BLOCK_FUNCTION, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "if") && strchr(trimmed, ':') != NULL) {
        return handle_open_block(stack, BLOCK_IF, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "elseif")) {
        return handle_branch(stack, trimmed, line_number, "elseif");
    }
    if (starts_with_keyword(trimmed, "else:")) {
        return handle_branch(stack, trimmed, line_number, "else");
    }
    if (starts_with_keyword(trimmed, "endif:")) {
        return handle_close_block(stack, BLOCK_IF, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "while") && strchr(trimmed, ':') != NULL) {
        return handle_open_block(stack, BLOCK_WHILE, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "endwhile:")) {
        return handle_close_block(stack, BLOCK_WHILE, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "for") && strchr(trimmed, ':') != NULL) {
        return handle_open_block(stack, BLOCK_FOR, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "endfor:")) {
        return handle_close_block(stack, BLOCK_FOR, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "object") && strchr(trimmed, ':') != NULL) {
        return handle_open_block(stack, BLOCK_OBJECT, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "end_object:")) {
        return handle_close_block(stack, BLOCK_OBJECT, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "list") && strchr(trimmed, ':') != NULL) {
        return handle_open_block(stack, BLOCK_LIST, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "end_list:")) {
        return handle_close_block(stack, BLOCK_LIST, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "try") && strchr(trimmed, ':') != NULL) {
        return handle_open_block(stack, BLOCK_TRY, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "endtry:")) {
        return handle_close_block(stack, BLOCK_TRY, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "error") && strchr(trimmed, ':') != NULL) {
        return handle_open_block(stack, BLOCK_ERROR, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "end_error:")) {
        return handle_close_block(stack, BLOCK_ERROR, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "http_route") && strchr(trimmed, ':') != NULL) {
        return handle_open_block(stack, BLOCK_HTTP_ROUTE, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "end_http_route:")) {
        return handle_close_block(stack, BLOCK_HTTP_ROUTE, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "transaction") && strchr(trimmed, ':') != NULL) {
        return handle_open_block(stack, BLOCK_TRANSACTION, trimmed, line_number);
    }
    if (starts_with_keyword(trimmed, "end_transaction:")) {
        return handle_close_block(stack, BLOCK_TRANSACTION, trimmed, line_number);
    }

    if (trimmed[0] == '@') {
        return 0;
    }

    return 0;
}

void separan_reset_result(separan_result *result) {
    if (result == NULL) {
        return;
    }
    reset_result(result);
}

void separan_result_free(separan_result *result) {
    if (result == NULL) {
        return;
    }
    reset_result(result);
}

separan_result separan_validate_source(const char *source) {
    reset_result(&g_last_result);
    int status = separan_analyze_source(source);
    g_last_result.ok = (status == 0);
    return g_last_result;
}

separan_result separan_validate_path(const char *path) {
    reset_result(&g_last_result);
    int status = separan_analyze_path(path);
    g_last_result.ok = (status == 0);
    return g_last_result;
}

int separan_analyze_source(const char *source) {
    reset_result(&g_last_result);
    if (source == NULL) {
        record_error("E000", "Null source", 0, "a valid source string", "NULL");
        return 1;
    }

    BlockStack stack = {0};
    int in_multiline_comment = 0;
    char *comment_label = NULL;
    int line_number = 0;
    const char *cursor = source;

    while (*cursor != '\0') {
        const char *line_start = cursor;
        while (*cursor != '\0' && *cursor != '\n' && *cursor != '\r') {
            cursor++;
        }

        size_t len = (size_t)(cursor - line_start);
        char *line = (char *)malloc(len + 1U);
        if (line == NULL) {
            return 1;
        }
        memcpy(line, line_start, len);
        line[len] = '\0';

        line_number++;
        char *trimmed = trim_in_place(line);
        trimmed = strip_leading_comment(trimmed);
        trimmed = trim_in_place(trimmed);

        if (!in_multiline_comment && *trimmed != '\0') {
            int result = parse_line(&stack, trimmed, line_number, &in_multiline_comment, &comment_label);
            if (result != 0) {
                free(line);
                free(comment_label);
                for (size_t index = 0; index < stack.count; index++) {
                    free(stack.entries[index].label);
                }
                return result;
            }
        }

        free(line);
        while (*cursor == '\n' || *cursor == '\r') {
            cursor++;
        }
    }

    if (in_multiline_comment) {
        print_error("E106", "Unclosed comment", line_number, comment_label ? comment_label : "<missing>", "<end of file>");
        free(comment_label);
        for (size_t index = 0; index < stack.count; index++) {
            free(stack.entries[index].label);
        }
        return 1;
    }

    if (stack.count != 0) {
        OpenBlock *last = &stack.entries[stack.count - 1];
        print_error("E106", "Unclosed block", last->line_number, closer_for_kind(last->kind), last->label);
        for (size_t index = 0; index < stack.count; index++) {
            free(stack.entries[index].label);
        }
        return 1;
    }

    for (size_t index = 0; index < stack.count; index++) {
        free(stack.entries[index].label);
    }
    return 0;
}

int separan_analyze_path(const char *path) {
    if (path == NULL) {
        record_error("E000", "Null file path", 0, "a valid file path", "NULL");
        return 1;
    }

    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        fprintf(stderr, "Unable to open input file: %s\n", path);
        record_error("E000", "Unable to open input file", 0, path, "file not found");
        return 1;
    }

    if (fseek(file, 0L, SEEK_END) != 0) {
        fclose(file);
        record_error("E000", "Seek failed", 0, "a readable file", path);
        return 1;
    }

    long size = ftell(file);
    if (size < 0) {
        fclose(file);
        record_error("E000", "File length unavailable", 0, "a readable file", path);
        return 1;
    }

    if (fseek(file, 0L, SEEK_SET) != 0) {
        fclose(file);
        record_error("E000", "Rewind failed", 0, "a readable file", path);
        return 1;
    }

    char *buffer = (char *)malloc((size_t)size + 1U);
    if (buffer == NULL) {
        fclose(file);
        record_error("E000", "Memory allocation failed", 0, "enough memory", path);
        return 1;
    }

    size_t read_count = fread(buffer, 1U, (size_t)size, file);
    buffer[read_count] = '\0';
    fclose(file);

    int result = separan_analyze_source(buffer);
    free(buffer);
    return result;
}

