#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "separan_runtime.h"
#include "separan_lexer.h"
#include "separan_files.h"

#ifdef _WIN32
#define _CRT_RAND_S
#endif
#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define SEPARAN_MAX_BIG_INTEGER_DIGITS 4096

typedef enum { V_EMPTY, V_NUMBER, V_BOOL, V_STRING, V_LIST, V_OBJECT, V_VOID, V_BYTES, V_DURATION,
               V_TIMEZONE, V_LOCAL_DATETIME, V_DATETIME, V_DB, V_EXEC_RESULT, V_ERROR, V_NAMESPACE, V_POSITION, V_REGEX } ValueKind;
typedef struct {
    size_t references;
    int closed;
    void *native;
    separan_database_adapter adapter;
} DatabaseResource;
typedef struct Value Value;
typedef struct ModuleResource ModuleResource;
typedef struct ModuleCache ModuleCache;
typedef struct ParseOpenFrame ParseOpenFrame;
static void module_retain(ModuleResource *module);
static void module_release(ModuleResource *module);
static int module_exported(ModuleResource *module,const char *name,int callable);
struct ParseOpenFrame { const char *label; const char *closer; size_t line,column; ParseOpenFrame *parent; };
static const char *closer_spelling(const char *type);
struct Value { ValueKind kind; double number; int64_t integer; char *big_integer; int temporal[7]; int offset_minutes; int floating; int exact_integer; int boolean; char *string; size_t string_length; Value *items; char **keys; size_t count; void *external; char *retained_type; };
static Value string_value(const char *s);
typedef struct Expr Expr;
typedef struct Stmt Stmt;
typedef struct { Stmt **items; size_t count; } Body;

struct Expr {
    int kind; /* 0 literal, 1 variable, 2 unary, 3 binary, 4 call, 5 list, 6 index, 7 member, 8 member call, 9 state test */
    size_t line, column;
    char *text;
    Value literal;
    Expr *left, *right;
    Expr **args;
    char **arg_names;
    size_t argc;
};

struct Stmt {
    int kind; /* ... 17 transaction, 18 index assignment, 19 typed declaration, 20 HTTP route */
    size_t line, column;
    size_t end_line;
    size_t name_line,name_column;
    size_t path_line,path_column;
    char *name, *declared_type, *method, *path;
    Expr *expr, *target;
    Body body, other, final;
    char **parameters, **parameter_types, **inferred_parameter_types;
    size_t parameter_count;
    char **tags;
    size_t tag_count;
    int constant;
};

typedef struct { char *name; char *declared_type; Value value; int constant; } Binding;
typedef struct Frame { Binding *bindings; size_t count; struct Frame *parent; } Frame;
typedef struct Runtime {
    separan_tokens tokens;
    size_t at;
    int error;
    const char *message;
    char error_code[8];
    char error_category[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
    char error_description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
    char error_expected[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
    char error_actual[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
    size_t error_related_line,error_related_column;
    size_t error_line,error_column;
    int handler_depth;
    int parse_depth;
    size_t parse_open_line,parse_open_column;
    const char *parse_open_label;
    ParseOpenFrame *parse_open_frame;
    int executing;
    size_t fault_line, fault_column;
    FILE *errors;
    Body program;
    Frame global;
    FILE *output;
    int returning;
    Value returned;
    int throwing;
    Value thrown;
    char thrown_code[8];
    size_t thrown_line,thrown_column;
    size_t steps;
    uint64_t random_state;
    separan_files files;
    int read_files, write_files, discover_paths, import_modules, read_environment, write_environment;
    const char *script_path;
    const char *const *command_arguments;
    size_t command_argument_count;
    const separan_database_adapter *database;
    const separan_process_adapter *process;
    const separan_host_adapter *host;
    Value http_request, http_params, http_response, http_cookies;
    int http_active, http_returned;
    struct Runtime *import_parent;
    ModuleCache **module_cache;
} Runtime;
struct ModuleResource { size_t references; Runtime runtime; char *path; };
struct ModuleCache { char *path; ModuleResource *module; ModuleCache *next; };
struct separan_runtime { Runtime runtime; ModuleCache *module_cache; };

static char *copy_text(const char *text) {
    size_t length = strlen(text);
    char *copy = malloc(length + 1);
    if (copy) memcpy(copy, text, length + 1);
    return copy;
}

static Value empty_value(void) { Value v = {0}; return v; }
static Value emptys_marker(void) { Value v=empty_value();v.retained_type=copy_text("__EMPTYS__");return v; }
static Value number_value(double n) { Value v = {0}; v.kind = V_NUMBER; v.number = n; return v; }
static Value integer_value(int64_t n) { Value v=number_value((double)n);v.integer=n;v.exact_integer=1;return v; }
static Value integer_text_value(const char *text) {
    errno=0;char *end=NULL;long long small=strtoll(text,&end,10);
    if(!errno&&end&&!*end)return integer_value((int64_t)small);
    int negative=*text=='-';const char *digits=text+negative;while(digits[0]=='0'&&digits[1])digits++;
    size_t n=strlen(digits);int sign=negative&&strcmp(digits,"0");char *canonical=malloc(n+(size_t)sign+1);
    if(!canonical)return empty_value();size_t at=0;if(sign)canonical[at++]='-';memcpy(canonical+at,digits,n+1);
    Value v=number_value(strtod(canonical,NULL));v.exact_integer=1;v.big_integer=canonical;return v;
}
static Value floating_value(double n) { Value v = number_value(n); v.floating = 1; return v; }
static Value duration_value(int64_t milliseconds) { Value v = {0}; v.kind = V_DURATION; v.integer = milliseconds; return v; }
static void format_number(char *buffer, size_t size, Value value) {
    if(value.big_integer){snprintf(buffer,size,"%s",value.big_integer);return;}
    if(value.exact_integer){snprintf(buffer,size,"%lld",(long long)value.integer);return;}
    if (isfinite(value.number) && floor(value.number) == value.number && fabs(value.number) < 1e16) {
        snprintf(buffer, size, "%.0f", value.number);
        if (value.floating && strlen(buffer) + 2 < size) strcat(buffer, ".0");
        return;
    }
    char candidate[64] = {0};
    for (int precision = 1; precision <= 17; precision++) {
        snprintf(candidate, sizeof(candidate), "%.*g", precision, value.number);
        if (strtod(candidate, NULL) == value.number) break;
    }
    snprintf(buffer, size, "%s", candidate);
}
static void format_duration_value(char *buffer, size_t size, int64_t milliseconds) {
    if (!milliseconds) { snprintf(buffer, size, "0ms"); return; }
    uint64_t remaining = milliseconds < 0 ? (uint64_t)(-(milliseconds + 1)) + 1 : (uint64_t)milliseconds;
    size_t at = 0;
    if (milliseconds < 0 && at + 1 < size) buffer[at++] = '-';
    const uint64_t factors[] = {86400000, 3600000, 60000, 1000, 1};
    const char *units[] = {"d", "h", "m", "s", "ms"};
    for (size_t i = 0; i < 5; i++) {
        uint64_t amount = remaining / factors[i]; remaining %= factors[i];
        if (amount) at += (size_t)snprintf(buffer + at, at < size ? size - at : 0, "%llu%s",
                                           (unsigned long long)amount, units[i]);
    }
}
static int calendar_days(int year, int month) {
    static const int days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    if (month == 2 && (year % 4 == 0 && (year % 100 != 0 || year % 400 == 0))) return 29;
    return month >= 1 && month <= 12 ? days[month - 1] : 0;
}
static int decimal_part(const char *text, size_t at, size_t count, int *value) {
    int result = 0;
    for (size_t i = 0; i < count; i++) {
        if (!isdigit((unsigned char)text[at + i])) return 0;
        result = result * 10 + text[at + i] - '0';
    }
    *value = result; return 1;
}
static int parse_calendar(const char *text, size_t length, int values[7], char canonical[32]) {
    if (length < 19 || length > 23 || text[4] != '-' || text[7] != '-' || text[10] != 'T' ||
        text[13] != ':' || text[16] != ':') return 0;
    memset(values, 0, 7 * sizeof(*values));
    if (!decimal_part(text,0,4,&values[0]) || !decimal_part(text,5,2,&values[1]) ||
        !decimal_part(text,8,2,&values[2]) || !decimal_part(text,11,2,&values[3]) ||
        !decimal_part(text,14,2,&values[4]) || !decimal_part(text,17,2,&values[5]) ||
        !values[0] || values[2] < 1 || values[2] > calendar_days(values[0], values[1]) ||
        values[3] > 23 || values[4] > 59 || values[5] > 59) return 0;
    if (length > 19) {
        size_t digits = length - 20;
        if (text[19] != '.' || digits < 1 || digits > 3 || !decimal_part(text,20,digits,&values[6])) return 0;
        if (digits == 1) values[6] *= 100; else if (digits == 2) values[6] *= 10;
    }
    if (values[6]) snprintf(canonical,32,"%04d-%02d-%02dT%02d:%02d:%02d.%03d",
                            values[0],values[1],values[2],values[3],values[4],values[5],values[6]);
    else snprintf(canonical,32,"%04d-%02d-%02dT%02d:%02d:%02d",
                  values[0],values[1],values[2],values[3],values[4],values[5]);
    return 1;
}
static int64_t days_from_civil(int year, unsigned month, unsigned day) {
    year -= month <= 2;
    int era = (year >= 0 ? year : year - 399) / 400;
    unsigned yoe = (unsigned)(year - era * 400);
    unsigned doy = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1;
    unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return (int64_t)era * 146097 + (int64_t)doe - 719468;
}
static void civil_from_days(int64_t days, int *year, int *month, int *day) {
    days += 719468;
    int64_t era = (days >= 0 ? days : days - 146096) / 146097;
    unsigned doe = (unsigned)(days - era * 146097);
    unsigned yoe = (doe - doe/1460 + doe/36524 - doe/146096) / 365;
    int y = (int)yoe + (int)era * 400;
    unsigned doy = doe - (365*yoe + yoe/4 - yoe/100);
    unsigned mp = (5*doy + 2)/153;
    *day = (int)(doy - (153*mp+2)/5 + 1); *month = (int)(mp + (mp < 10 ? 3 : -9));
    *year = y + (*month <= 2);
}
static int timezone_offset_text(const char *text, size_t length, int *offset) {
    if (length == 1 && text[0] == 'Z') { *offset = 0; return 1; }
    if (length == 3 && !memcmp(text,"UTC",3)) { *offset = 0; return 1; }
    if (length != 6 || (text[0] != '+' && text[0] != '-') || text[3] != ':') return 0;
    int hours, minutes;
    if (!decimal_part(text,1,2,&hours) || !decimal_part(text,4,2,&minutes) || minutes > 59 || hours > 14 ||
        (hours == 14 && minutes) || !memcmp(text,"-00:00",6)) return 0;
    *offset = (hours * 60 + minutes) * (text[0] == '-' ? -1 : 1); return 1;
}
static int64_t calendar_to_epoch(const int values[7], int offset_minutes) {
    return days_from_civil(values[0],(unsigned)values[1],(unsigned)values[2]) * INT64_C(86400000) +
        values[3]*INT64_C(3600000) + values[4]*INT64_C(60000) + values[5]*INT64_C(1000) + values[6] -
        offset_minutes*INT64_C(60000);
}
static Value datetime_epoch_value(int64_t epoch, int offset_minutes) {
    int64_t local = epoch + offset_minutes * INT64_C(60000);
    int64_t days = local / INT64_C(86400000), remainder = local % INT64_C(86400000);
    if (remainder < 0) { remainder += INT64_C(86400000); days--; }
    int values[7]; civil_from_days(days,&values[0],&values[1],&values[2]);
    values[3]=(int)(remainder/3600000); remainder%=3600000;
    values[4]=(int)(remainder/60000); remainder%=60000;
    values[5]=(int)(remainder/1000); values[6]=(int)(remainder%1000);
    char body[32], text[40];
    if (values[6]) snprintf(body,sizeof(body),"%04d-%02d-%02dT%02d:%02d:%02d.%03d",
                            values[0],values[1],values[2],values[3],values[4],values[5],values[6]);
    else snprintf(body,sizeof(body),"%04d-%02d-%02dT%02d:%02d:%02d",
                  values[0],values[1],values[2],values[3],values[4],values[5]);
    if (!offset_minutes) snprintf(text,sizeof(text),"%sZ",body);
    else snprintf(text,sizeof(text),"%s%c%02d:%02d",body,offset_minutes<0?'-':'+',abs(offset_minutes)/60,abs(offset_minutes)%60);
    Value value = string_value(text); value.kind=V_DATETIME; value.integer=epoch; value.offset_minutes=offset_minutes;
    memcpy(value.temporal,values,sizeof(values)); return value;
}
static Value bool_value(int b) { Value v = {0}; v.kind = V_BOOL; v.boolean = b; return v; }
static Value string_bytes(const char *s, size_t length) {
    Value v = {0}; v.kind = V_STRING; v.string_length = length;
    v.string = malloc(length + 1);
    if (v.string) { memcpy(v.string, s, length); v.string[length] = 0; }
    return v;
}
static Value string_value(const char *s) { return string_bytes(s, strlen(s)); }
static int owns_string(ValueKind kind) {
    return kind == V_STRING || kind == V_BYTES || kind == V_TIMEZONE || kind == V_LOCAL_DATETIME || kind == V_DATETIME;
}
static size_t utf8_length(const char *text, size_t length) {
    size_t count = 0;
    for (size_t i = 0; i < length; i++)
        if (((unsigned char)text[i] & 0xC0) != 0x80) count++;
    return count;
}
static size_t utf8_offset(const char *text, size_t length, size_t character) {
    size_t offset = 0, at = 0;
    while (offset < length && at < character) {
        offset++;
        while (offset < length && ((unsigned char)text[offset] & 0xC0) == 0x80) offset++;
        at++;
    }
    return offset;
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
    if(v.kind==V_EMPTY&&v.retained_type){Value copy=empty_value();copy.retained_type=copy_text(v.retained_type);return copy;}
    if (v.kind == V_DB && v.external) { ((DatabaseResource *)v.external)->references++; return v; }
    if(v.kind==V_NAMESPACE&&v.external){module_retain(v.external);return v;}
    if (owns_string(v.kind)) {
        Value copy = string_bytes(v.string, v.string_length); copy.kind = v.kind; copy.integer = v.integer;
        copy.offset_minutes = v.offset_minutes; memcpy(copy.temporal, v.temporal, sizeof(copy.temporal));
        if(v.retained_type)copy.retained_type=copy_text(v.retained_type);return copy;
    }
    if (v.kind == V_LIST || v.kind == V_OBJECT || v.kind == V_EXEC_RESULT || v.kind == V_ERROR || v.kind == V_REGEX) {
        Value copy = empty_value(); copy.kind = v.kind; copy.count = v.count;
        copy.items = calloc(v.count ? v.count : 1, sizeof(*copy.items));
        if (copy.items) for (size_t i = 0; i < v.count; i++) copy.items[i] = clone_value(v.items[i]);
        if (v.kind == V_OBJECT || v.kind == V_EXEC_RESULT || v.kind == V_ERROR || v.kind == V_REGEX) {
            copy.keys = calloc(v.count ? v.count : 1, sizeof(*copy.keys));
            if (copy.keys) for (size_t i = 0; i < v.count; i++) copy.keys[i] = copy_text(v.keys[i]);
        }
        if(v.retained_type)copy.retained_type=copy_text(v.retained_type);return copy;
    }
    if(v.kind==V_NUMBER&&v.big_integer){Value copy=v;copy.big_integer=copy_text(v.big_integer);if(v.retained_type)copy.retained_type=copy_text(v.retained_type);return copy;}
    if(v.retained_type){Value copy=v;copy.retained_type=copy_text(v.retained_type);return copy;}return v;
}
static void free_value(Value v) {
    free(v.retained_type);
    free(v.big_integer);
    if (v.kind == V_DB && v.external) {
        DatabaseResource *resource = v.external;
        if (--resource->references == 0) {
            if (!resource->closed && resource->adapter.close) resource->adapter.close(resource->adapter.context, resource->native);
            free(resource);
        }
    }
    if(v.kind==V_NAMESPACE&&v.external)module_release(v.external);
    if (owns_string(v.kind)) free(v.string);
    if (v.kind == V_LIST || v.kind == V_OBJECT || v.kind == V_EXEC_RESULT || v.kind == V_ERROR || v.kind == V_REGEX) {
        for (size_t i = 0; i < v.count; i++) { free_value(v.items[i]); if (v.kind == V_OBJECT || v.kind == V_EXEC_RESULT || v.kind == V_ERROR || v.kind == V_REGEX) free(v.keys[i]); }
        free(v.items); free(v.keys);
    }
}

static separan_token *peek(Runtime *r) { return &r->tokens.tokens[r->at]; }
static int at(Runtime *r, const char *kind) { return strcmp(peek(r)->type, kind) == 0; }
static int at_label(Runtime *r) { return at(r, "IDENTIFIER") || at(r, "LABEL"); }
static separan_token *take(Runtime *r) { return &r->tokens.tokens[r->at++]; }
static int accept(Runtime *r, const char *kind) { if (!at(r, kind)) return 0; take(r); return 1; }
static void fault_at(Runtime *r,const char *message,size_t line,size_t column);
static void fault_syntax(Runtime *r,const char *message,const char *description);
static void check_closing_label(Runtime *r,const char *expected,const char *message,
                                size_t opener_line,size_t opener_column) {
    if(r->error)return;
    if(!at_label(r)){
        const char *description="Expected closing block label.";
        if(!strcmp(message,"branch label mismatch")){
            const char *branch="branch";
            for(size_t index=r->at;index>0;index--){
                separan_token *token=&r->tokens.tokens[index-1];
                if(token->line!=peek(r)->line)break;
                if(!strcmp(token->type,"ELSEIF")){branch="elseif";break;}
                if(!strcmp(token->type,"ELSE")){branch="else";break;}
                if(!strcmp(token->type,"CATCH")){branch="catch";break;}
                if(!strcmp(token->type,"FINALLY")){branch="finally";break;}
            }
            char text[96];snprintf(text,sizeof(text),"Expected label after %s.",branch);
            fault_syntax(r,"expected closing block label",text);
        }else fault_syntax(r,"expected closing block label",description);
        return;
    }
    separan_token *label=take(r);
    if(strcmp(label->lexeme,expected)){
        size_t first_index=r->at-2;
        while(first_index&&r->tokens.tokens[first_index-1].line==label->line)first_index--;
        separan_token *closer=&r->tokens.tokens[first_index];
        for(ParseOpenFrame *ancestor=r->parse_open_frame;ancestor;ancestor=ancestor->parent){
            if(ancestor->label&&ancestor->closer&&!strcmp(ancestor->label,label->lexeme)&&
               !strcmp(ancestor->closer,closer->type)){
                const char *prefix=closer_spelling(closer->type);
                snprintf(r->error_expected,sizeof(r->error_expected),"%s:%s",prefix,expected);
                snprintf(r->error_actual,sizeof(r->error_actual),"%s:%s",closer->lexeme,label->lexeme);
                r->error_related_line=opener_line;r->error_related_column=opener_column;
                fault_at(r,"block nesting error",closer->line,closer->column);
                return;
            }
        }
        if(strstr(message,"label mismatch")){
            const char *prefix=closer->lexeme;
            if(!strcmp(message,"branch label mismatch")){
                if(!strcmp(closer->type,"ELSEIF"))prefix="elseif";
                else if(!strcmp(closer->type,"ELSE"))prefix="else";
                else if(!strcmp(closer->type,"CATCH"))prefix="catch";
                else if(!strcmp(closer->type,"FINALLY"))prefix="finally";
            }
            snprintf(r->error_expected,sizeof(r->error_expected),"%s:%s",prefix,expected);
            snprintf(r->error_actual,sizeof(r->error_actual),"%s:%s",prefix,label->lexeme);
            r->error_related_line=opener_line;
            r->error_related_column=opener_column;
        }
        fault_at(r,message,label->line,label->column);
    }
}
static const char *fault_code(const char *message) {
    if (!strcmp(message, "process permission error")) return "E800";
    if (!strcmp(message, "invalid command")) return "E801";
    if (!strcmp(message, "command not found or denied")) return "E802";
    if (!strcmp(message, "invalid process cwd")) return "E803";
    if (!strcmp(message, "command spawn error")) return "E804";
    if (!strcmp(message, "process limit error")) return "E805";
    if (!strcmp(message, "command error")) return "E808";
    if (!strcmp(message, "command timeout error")) return "E809";
    if (!strcmp(message, "database driver error")) return "E900";
    if (!strcmp(message, "database connection error")) return "E901";
    if (!strcmp(message, "database authentication error")) return "E902";
    if (!strcmp(message, "database query error")) return "E903";
    if (!strcmp(message, "database constraint error")) return "E904";
    if (!strcmp(message, "database timeout error")) return "E905";
    if (!strcmp(message, "database transaction error")) return "E907";
    if (!strcmp(message,"nested HTTP route")) return "E890";
    if (!strcmp(message,"invalid route method")) return "E891";
    if (!strcmp(message,"invalid route path")) return "E892";
    if (!strcmp(message,"no HTTP request context")) return "E893";
    if (!strcmp(message,"HTTP request decode error")) return "E894";
    if (!strcmp(message,"invalid HTTP response")) return "E895";
    if (!strcmp(message,"duplicate HTTP route")) return "E896";
    if (!strcmp(message,"duplicate function")) return "E204";
    if (!strcmp(message,"invalid main function")) return "E205";
    if (!strcmp(message,"reserved function name")) return "E209";
    if (!strcmp(message,"duplicate error name")) return "E122";
    if (!strcmp(message,"error name conflicts with function")) return "E122";
    if (!strcmp(message,"invalid error name")) return "E121";
    if (!strcmp(message,"nested error declaration")) return "E120";
    if (!strcmp(message,"duplicate parameter")) return "E112";
    if (!strcmp(message,"duplicate named argument")) return "E113";
    if (!strcmp(message,"positional argument after named argument")) return "E114";
    if (!strcmp(message,"invalid object entry")) return "E115";
    if (!strcmp(message,"duplicate object field")) return "E116";
    if (!strcmp(message,"block label mismatch")||!strcmp(message,"branch label mismatch")||
        !strcmp(message,"function label mismatch")||!strcmp(message,"object label mismatch")||
        !strcmp(message,"list label mismatch")||!strcmp(message,"error label mismatch")) return "E104";
    if (!strcmp(message, "undefined variable")) return "E202";
    if (!strcmp(message, "unknown function")) return "E206";
    if (!strcmp(message, "wrong argument count")) return "E207";
    if (!strcmp(message, "unknown named argument")) return "E207";
    if (!strcmp(message, "constant cannot be reassigned")) return "E211";
    if (!strcmp(message, "duplicate typed declaration")) return "E210";
    if (!strcmp(message, "initializer required")) return "E124";
    if (!strcmp(message, "invalid declared type")) return "E123";
    if (!strcmp(message, "untyped EMPTY")) return "E129";
    if (!strcmp(message, "EMPTY constant")) return "E130";
    if (!strcmp(message, "EMPTY value cannot be used")) return "E131";
    if (!strcmp(message, "list element type required")) return "E134";
    if (!strcmp(message, "position selector outside list operation")) return "E136";
    if (!strcmp(message,"list shape integer required")) return "E201";
    if (!strcmp(message,"invalid list shape range")) return "E603";
    if (!strcmp(message,"list shape target required")) return "E605";
    if (!strcmp(message, "EMPTYS requires container")) return "E133";
    if (!strcmp(message, "list elements must have the same type")) return "E203";
    if (!strcmp(message, "list index out of range or invalid")) return "E302";
    if (!strcmp(message,"list index type invalid")) return "E201";
    if (!strcmp(message,"missing object member")) return "E212";
    if (!strcmp(message,"unknown regex member method")) return "E213";
    if (!strcmp(message,"regex group out of range")) return "E834";
    if (!strcmp(message,"member access requires object")||!strcmp(message,"for requires a list")||
    !strcmp(message,"invalid unary operand")||!strcmp(message,"integer operands required")||
    !strcmp(message,"index target requires list")) return "E201";
    if (!strcmp(message,"number required")||!strcmp(message,"number list required")||
        !strcmp(message,"non-empty number list required")||!strcmp(message,"string required")||
        !strcmp(message,"list required")||!strcmp(message,"bytes required")||
        !strcmp(message,"string or bytes required")||!strcmp(message,"integer required")||
        !strcmp(message,"finite number required")||!strcmp(message,"timezone required")||
        !strcmp(message,"datetime required")||!strcmp(message,"local datetime and timezone required")||
        !strcmp(message,"datetime and timezone required")||!strcmp(message,"datetime and pattern required")||
        !strcmp(message,"string list and separator required")||!strcmp(message,"string and non-negative indexes required")||
        !strcmp(message,"string template required")||!strcmp(message,"glob pattern must be a string")||
        !strcmp(message,"string and non-negative index required")||!strcmp(message,"string and non-negative byte limit required")||
        !strcmp(message,"string arguments required")||!strcmp(message,"strings required")||
        !strcmp(message,"string or list required")||!strcmp(message,"length requires string, list, or bytes")||
        !strcmp(message,"format string template required")||!strcmp(message,"file path must be a string")||
        !strcmp(message,"file paths must be strings")||!strcmp(message,"JSON text must be a string")||
        !strcmp(message,"timezone text required")||!strcmp(message,"datetime text required")||
        !strcmp(message,"valid environment name required")||!strcmp(message,"string option required")||
        !strcmp(message,"hex string required")||!strcmp(message,"base64 string required")||
        !strcmp(message,"cannot convert to number")||!strcmp(message,"string or list required")||
        !strcmp(message,"integer calendar fields required")||!strcmp(message,"duration required")||
        !strcmp(message,"integer seed required")||!strcmp(message,"number range required")||
        !strcmp(message,"non-empty list required")||!strcmp(message,"object list and field required")||
        !strcmp(message,"function reference required")||!strcmp(message,"object and string key required")||
        !strcmp(message,"string and integer required")||!strcmp(message,"encoding must be a string")||
        !strcmp(message,"object required")||!strcmp(message,"integer and base 2..36 required")||
        !strcmp(message,"string and base 2..36 required")||!strcmp(message,"database connection required")||
        !strcmp(message,"file value has wrong type")||!strcmp(message,"bytes index type invalid")||
        !strcmp(message,"integer required")) return "E201";
    if (!strcmp(message,"invalid decimal string")||!strcmp(message,"cannot convert to boolean")||
        !strcmp(message,"invalid base integer")) return "E304";
    if (!strcmp(message,"empty delimiter")||!strcmp(message,"empty search string")) return "E305";
    if (!strcmp(message,"invalid local datetime")) return "E404";
    if (!strcmp(message,"invalid duration text")) return "E407";
    if (!strcmp(message,"invalid secure random length")) return "E504";
    if (!strcmp(message,"numeric domain error")||!strcmp(message,"math domain error")||!strcmp(message,"math range error")||!strcmp(message,"exact power size limit")) return "E308";
     if (!strcmp(message,"datetime precision or range error")) return "E401";
     if (!strcmp(message,"duration precision or range error")||!strcmp(message,"duration overflow")) return "E407";
    if (!strcmp(message,"invalid random integer range")||!strcmp(message,"invalid secure random range")) return "E501";
    if (!strcmp(message,"chained comparison")) return "E111";
    if (!strcmp(message,"expected EMPTY or EMPTYS")) return "E128";
    if (!strcmp(message,"EMPTY equality is invalid")) return "E128";
    if (!strcmp(message,"tag outside function")) return "E216";
    if (!strcmp(message,"tag after statement")) return "E217";
    if (!strcmp(message,"invalid or duplicate function tag")) return "E218";
    if (!strcmp(message,"reserved system binding")) return "E215";
    if (!strcmp(message,"immutable system member")) return "E214";
    if (!strcmp(message,"parameter type cannot change")) return "E208";
    if (!strcmp(message,"incomplete structural token")) return "E122";
    if (!strcmp(message,"invalid branch order")) return "E108";
    if (!strcmp(message,"unexpected closer")) return "E107";
    if (!strcmp(message,"unclosed block")) return "E106";
    if (!strcmp(message,"block kind mismatch")) return "E105";
    if (!strcmp(message,"block nesting error")) return "E105";
    if (!strcmp(message,"duplicate open label")) return "E109";
    if (!strcmp(message, "JSON parse error")) return "E740";
    if (!strcmp(message, "JSON encode error")) return "E741";
    if (!strcmp(message, "invalid capability path")) return "E721";
    if (!strcmp(message, "file I/O error")) return "E722";
    if (!strcmp(message, "file write error")) return "E723";
    if (!strcmp(message, "destination exists")) return "E725";
    if (!strcmp(message, "capability denied")||!strcmp(message,"host adapter returned invalid result")) return "E720";
    if (!strcmp(message, "unsupported encoding")) return "E620";
    if (!strcmp(message, "bytes encode error")||!strcmp(message, "bytes decode error")) return "E621";
    if (!strcmp(message, "invalid hex")) return "E625";
    if (!strcmp(message,"division by zero")) return "E301";
    if (!strcmp(message, "invalid bytes index")) return "E622";
    if (!strcmp(message, "invalid bytes range")) return "E623";
    if (!strcmp(message, "bytes size limit")) return "E624";
    if (!strcmp(message, "invalid base64")) return "E626";
    if (!strcmp(message, "VOID value cannot be used")) return "E127";
    if (!strcmp(message, "top-level expression is not allowed")) return "E110";
    if (!strcmp(message,"duplicate catch")) return "E117";
    if (!strcmp(message,"catch after any")) return "E118";
    if (!strcmp(message,"empty try handler")) return "E119";
    if (!strcmp(message,"throw requires error value")||!strcmp(message,"error message must be string")) return "E201";
    if (!strcmp(message,"invalid import path")) return "E704";
    if (!strcmp(message,"circular import")) return "E701";
    if (!strcmp(message,"import order")) return "E702";
    if (!strcmp(message,"nested import")) return "E703";
    if (!strcmp(message,"import read error")||!strcmp(message,"import parse error")||!strcmp(message,"import execution error")) return "E705";
    if (!strcmp(message,"private or missing export")||!strcmp(message,"function value is not supported here")) return "E706";
    if (!strcmp(message, "variable type cannot change") ||
        !strcmp(message, "object field type cannot change") ||
        !strcmp(message, "incompatible operand types") ||
        !strcmp(message, "condition must be boolean")) return "E201";
    return "E100";
}
static void fault(Runtime *r, const char *message) {
    if (!r->error) {
        r->error = 1; r->message = message;
        snprintf(r->error_code,sizeof(r->error_code),"%s",fault_code(message));
        size_t line=r->executing&&r->fault_line?r->fault_line:peek(r)->line;
        size_t column=r->executing&&r->fault_line?r->fault_column:peek(r)->column;
        r->error_line=line;r->error_column=column;
        if(!strcmp(r->error_code,"E100"))
            snprintf(r->error_actual,sizeof(r->error_actual),"%s",peek(r)->lexeme);
        if(!strcmp(message,"chained comparison")){
            snprintf(r->error_category,sizeof(r->error_category),"Chained comparison");
            snprintf(r->error_description,sizeof(r->error_description),"Comparison operators cannot be chained. Use && explicitly.");
            snprintf(r->error_actual,sizeof(r->error_actual),"%s",peek(r)->lexeme);
        }
        if(!strcmp(message,"expected expression")){
            snprintf(r->error_category,sizeof(r->error_category),"Expected expression");
            snprintf(r->error_description,sizeof(r->error_description),"A value or expression is required here.");
        }else if(!strcmp(message,"expected end of line")){
            snprintf(r->error_category,sizeof(r->error_category),"Unexpected token");
            snprintf(r->error_description,sizeof(r->error_description),"Statements must end at the end of the line.");
        }
        if(!r->error_category[0]){
            const char *category=NULL,*description=NULL;
            if(!strcmp(message,"EMPTY value cannot be used")){category="EMPTY value use";description="EMPTY cannot be used as a concrete value.";}
            else if(!strcmp(message,"EMPTYS requires container")){category="EMPTYS container required";description="EMPTYS can only clear a container-valued value.";}
            else if(!strcmp(message,"list element type required")){category="List element type required";description="A concrete list element type is required here.";}
            else if(!strcmp(message,"position selector outside list operation")){category="Position selector context";description="Position selectors are valid only as a list shape position.";}
            else if(!strcmp(message,"VOID value cannot be used")){category="VOID value use";description="VOID does not represent a value.";}
            else if(!strcmp(message,"invalid import path")){category="Invalid import path";description="Import paths must be relative .sep paths without '..'.";}
            else if(!strcmp(message,"import read error")||!strcmp(message,"import parse error")||!strcmp(message,"import execution error")){category="Import error";description="The imported module could not be loaded or executed.";}
            else if(!strcmp(message,"circular import")){category="Circular import";description="The imported module is already active in the import chain.";}
            else if(!strcmp(message,"no HTTP request context")){category="HTTP request context";description="This operation requires an active HTTP request context.";}
            else if(!strcmp(message,"HTTP request decode error")){category="HTTP request decode error";description="The HTTP request could not be decoded.";}
            else if(!strcmp(message,"invalid HTTP response")){category="Invalid HTTP response";description="The HTTP response value is invalid.";}
            if(category){snprintf(r->error_category,sizeof(r->error_category),"%s",category);snprintf(r->error_description,sizeof(r->error_description),"%s",description);}
        }
            if(!r->handler_depth)fprintf(r->errors, "SEPARAN %s: %s at line %zu, column %zu\n", r->error_code, message,line,column);
    }
}
static void fault_at(Runtime *r,const char *message,size_t line,size_t column) {
    size_t old_line=r->fault_line,old_column=r->fault_column;int old_executing=r->executing;
    r->fault_line=line;r->fault_column=column;r->executing=1;fault(r,message);
    r->fault_line=old_line;r->fault_column=old_column;r->executing=old_executing;
}
static void fault_detail_at(Runtime *r,const char *message,const char *category,const char *description,
                            const char *actual,size_t line,size_t column) {
    if(r->error)return;
    snprintf(r->error_category,sizeof(r->error_category),"%s",category);
    snprintf(r->error_description,sizeof(r->error_description),"%s",description);
    snprintf(r->error_actual,sizeof(r->error_actual),"%s",actual);
        fault_at(r,message,line,column);
}
static void external_fault(Runtime *r,const char *code,const char *message) {
    if(r->error)return;
    const char *safe_code=code&&code[0]=='E'&&isdigit((unsigned char)code[1])&&
        isdigit((unsigned char)code[2])&&isdigit((unsigned char)code[3])&&!code[4]?code:"E720";
    r->error=1;r->message="host operation failed";snprintf(r->error_code,sizeof(r->error_code),"%s",safe_code);
    size_t line=r->executing&&r->fault_line?r->fault_line:peek(r)->line;
    size_t column=r->executing&&r->fault_line?r->fault_column:peek(r)->column;
    r->error_line=line;r->error_column=column;
    if(!r->handler_depth)fprintf(r->errors,"SEPARAN %s: %s at line %zu, column %zu\n",safe_code,
                                 message&&*message?message:"host operation failed",line,column);
}
static int expect_syntax(Runtime *r,const char *kind,const char *description) {
    if(r->error)return 0;
    if(accept(r,kind))return 1;
    snprintf(r->error_category,sizeof(r->error_category),"Syntax error");
    snprintf(r->error_description,sizeof(r->error_description),"%s",description);
    fault(r,"unexpected token");return 0;
}
static int expect_detail(Runtime *r,const char *kind,const char *category,const char *description) {
    if(r->error)return 0;
    if(accept(r,kind))return 1;
    snprintf(r->error_category,sizeof(r->error_category),"%s",category);
    snprintf(r->error_description,sizeof(r->error_description),"%s",description);
    fault(r,"unexpected token");return 0;
}
static int expect_line_end(Runtime *r) {
    return expect_detail(r,"NEWLINE","Unexpected token","Statements must end at the end of the line.");
}
static int expect_open_label_colon(Runtime *r,const char *kind) {
    char description[128];
    snprintf(description,sizeof(description),"Expected :label after %s expression.",kind);
    return expect_syntax(r,"COLON",description);
}
static int expect_block_closer(Runtime *r,const char *token,const char *kind) {
    char description[96];
    snprintf(description,sizeof(description),"Expected closing %s.",kind);
    return expect_syntax(r,token,description);
}
static int expect_block_closer_colon(Runtime *r) {
    return expect_syntax(r,"COLON","Expected ':' in block closer.");
}
static void fault_syntax(Runtime *r,const char *message,const char *description) {
    if(r->error)return;
    snprintf(r->error_category,sizeof(r->error_category),"Syntax error");
    snprintf(r->error_description,sizeof(r->error_description),"%s",description);
    fault(r,message);
}
static void newlines(Runtime *r) { while (accept(r, "NEWLINE")) {} }

static Expr *new_expr(int kind) { Expr *e = calloc(1, sizeof(*e)); if (e) e->kind = kind; return e; }
static Stmt *new_stmt(int kind) { Stmt *s = calloc(1, sizeof(*s)); if (s) s->kind = kind; return s; }
static int add_stmt(Body *body, Stmt *stmt) {
    Stmt **items = realloc(body->items, (body->count + 1) * sizeof(*items));
    if (!items) return 0;
    body->items = items; body->items[body->count++] = stmt; return 1;
}
static int add_named_arg(Expr *expr, Expr *arg, const char *name) {
    Expr **args = realloc(expr->args, (expr->argc + 1) * sizeof(*args));
    if (!args) return 0;
    expr->args = args;
    char **names = realloc(expr->arg_names, (expr->argc + 1) * sizeof(*names));
    if (!names) return 0;
    expr->arg_names = names; expr->args[expr->argc] = arg;
    expr->arg_names[expr->argc] = name ? copy_text(name) : NULL;
    if (name && !expr->arg_names[expr->argc]) return 0;
    expr->argc++; return 1;
}
static int add_arg(Expr *expr, Expr *arg) { return add_named_arg(expr, arg, NULL); }
static void free_expr(Expr *e) {
    if (!e) return;
    free(e->text); free_value(e->literal); free_expr(e->left); free_expr(e->right);
    for (size_t i = 0; i < e->argc; i++) { free_expr(e->args[i]); free(e->arg_names[i]); }
    free(e->args); free(e->arg_names); free(e);
}
static void free_body(Body body) {
    for (size_t i = 0; i < body.count; i++) {
        Stmt *s = body.items[i];
        free(s->name); free(s->declared_type); free(s->method); free(s->path); free_expr(s->expr); free_expr(s->target); free_body(s->body); free_body(s->other); free_body(s->final);
        for (size_t j = 0; j < s->parameter_count; j++) {free(s->parameters[j]);free(s->parameter_types?s->parameter_types[j]:NULL);}
        for(size_t j=0;j<s->parameter_count;j++)free(s->inferred_parameter_types?s->inferred_parameter_types[j]:NULL);
        for(size_t j=0;j<s->tag_count;j++)free(s->tags[j]);
        free(s->tags);free(s->parameters);free(s->parameter_types);free(s->inferred_parameter_types); free(s);
    }
    free(body.items);
}

static int precedence(const char *kind) {
    if(!strcmp(kind,"EMPTY_COALESCE"))return 1;
    if (!strcmp(kind, "OR")) return 2;
    if (!strcmp(kind, "AND")) return 3;
    if (!strcmp(kind, "EQUAL_EQUAL") || !strcmp(kind, "BANG_EQUAL")) return 4;
    if(!strcmp(kind,"IN"))return 5;
    if (!strcmp(kind, "LESS") || !strcmp(kind, "LESS_EQUAL") ||
        !strcmp(kind, "GREATER") || !strcmp(kind, "GREATER_EQUAL")) return 5;
    if (!strcmp(kind, "PLUS") || !strcmp(kind, "MINUS")) return 6;
    if (!strcmp(kind, "STAR") || !strcmp(kind, "SLASH") || !strcmp(kind, "PERCENT") ||
        !strcmp(kind, "FLOOR_DIV")) return 7;
    if (!strcmp(kind, "POWER")) return 8;
    return 0;
}

static Expr *parse_expr(Runtime *r, int minimum);
static char *big_from_base(const char *digits,int base);
static Expr *parse_atom(Runtime *r);
static Expr *parse_atom_inner(Runtime *r) {
    separan_token *token = peek(r);
    if (accept(r, "NUMBER")) {
        Expr *e = new_expr(0); if (!e) return NULL;
        char *normalized = malloc(strlen(token->lexeme) + 1);
        if (!normalized) { free(e); return NULL; }
        size_t j = 0;
        for (size_t i = 0; token->lexeme[i]; i++) if (token->lexeme[i] != '_') normalized[j++] = token->lexeme[i];
        normalized[j] = 0;
        if(strchr(normalized,'.'))e->literal=floating_value(strtod(normalized,NULL));
        else {int base=10;const char *digits=normalized;if(normalized[0]=='0'&&(normalized[1]=='b'||normalized[1]=='B')){base=2;digits+=2;}
            else if(normalized[0]=='0'&&(normalized[1]=='o'||normalized[1]=='O')){base=8;digits+=2;}
            else if(normalized[0]=='0'&&(normalized[1]=='x'||normalized[1]=='X')){base=16;digits+=2;}
            errno=0;char *end=NULL;unsigned long long value=strtoull(digits,&end,base);
            if(!errno&&end&&!*end&&value<=(unsigned long long)INT64_MAX)e->literal=integer_value((int64_t)value);
            else if(base==10)e->literal=integer_text_value(normalized);
            else {char *decimal=big_from_base(digits,base);e->literal=decimal?integer_text_value(decimal):empty_value();free(decimal);}}
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
    if(accept(r,"FRONT")||accept(r,"BACK")){Expr *e=new_expr(0);if(e){e->literal.kind=V_POSITION;e->literal.integer=!strcmp(token->type,"BACK");}return e;}
    if (accept(r, "EMPTY")) return new_expr(0);
    if (accept(r,"EMPTYS")){Expr *e=new_expr(0);if(e)e->literal=emptys_marker();return e;}
    if (accept(r, "LBRACKET")) {
        Expr *e = new_expr(5); if (!e) return NULL;
        if (!at(r, "RBRACKET")) do {
            if (!add_arg(e, parse_expr(r, 1))) { fault(r, "out of memory"); break; }
        } while (accept(r, "COMMA"));
        expect_syntax(r,"RBRACKET","Expected ']' after list."); return e;
    }
    if (accept(r, "LPAREN")) {
        Expr *e = parse_expr(r, 1);
        expect_detail(r,"RPAREN","Syntax error","Expected ')' after expression.");
        return e;
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
            int saw_named = 0;
            if (!at(r, "RPAREN")) do {
                if (at(r,"IDENTIFIER") && r->at + 1 < r->tokens.count &&
                    !strcmp(r->tokens.tokens[r->at + 1].type,"EQUAL")) {
                    separan_token *argument_token=take(r);const char *argument_name=argument_token->lexeme;take(r);saw_named=1;
                    for(size_t i=0;i<e->argc;i++) if(e->arg_names[i] && !strcmp(e->arg_names[i],argument_name)){
                        char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                        snprintf(description,sizeof(description),"Named argument '%s' is already specified.",argument_name);
                        fault_detail_at(r,"duplicate named argument","Duplicate named argument",description,
                                        argument_name,argument_token->line,argument_token->column);
                    }
                    if(r->error || !add_named_arg(e,parse_expr(r,1),argument_name)) break;
                } else {
                    if(saw_named){separan_token *argument_token=peek(r);fault_detail_at(r,"positional argument after named argument",
                        "Positional argument after named argument","Positional arguments must appear before named arguments.",
                        argument_token->lexeme,argument_token->line,argument_token->column);break;}
                    if (!add_arg(e, parse_expr(r, 1))) break;
                }
            } while (accept(r, "COMMA"));
            expect_detail(r,"RPAREN","Syntax error","Expected ')' after arguments.");
        }
        return e;
    }
    fault(r, "expected expression"); return NULL;
}

static Expr *parse_atom(Runtime *r) {
    separan_token *token=peek(r);Expr *expression=parse_atom_inner(r);
    if(expression){expression->line=token->line;expression->column=token->column;}
    return expression;
}

static Expr *parse_primary(Runtime *r) {
    Expr *left = parse_atom(r);
    while (!r->error && (at(r, "LBRACKET") || at(r, "DOT"))) {
        if (accept(r, "LBRACKET")) {
            separan_token *opening=&r->tokens.tokens[r->at-1];
            Expr *index = new_expr(6);
            if (!index) { fault(r, "out of memory"); break; }
            index->left = left;index->line=opening->line;index->column=opening->column;
            index->right = parse_expr(r, 1);
            expect_syntax(r,"RBRACKET","Expected ']' after list index.");
            left = index;
        } else {
            separan_token *dot=take(r);
            Expr *member = new_expr(7);
            if (!member) { fault(r, "out of memory"); break; }
            member->left = left;member->line=dot->line;member->column=dot->column;
            if (at(r, "IDENTIFIER")) member->text = copy_text(take(r)->lexeme);
            else fault_syntax(r,"expected member name","Expected member name after '.'.");
            if(!r->error&&accept(r,"LPAREN")){
                member->kind=8;int saw_named=0;
                if(!at(r,"RPAREN")){do{
                    if(at(r,"IDENTIFIER")&&r->at+1<r->tokens.count&&!strcmp(r->tokens.tokens[r->at+1].type,"EQUAL")){
                        separan_token *argument_token=take(r);const char *argument_name=argument_token->lexeme;take(r);saw_named=1;
                        for(size_t i=0;i<member->argc;i++)if(member->arg_names[i]&&!strcmp(member->arg_names[i],argument_name)){
                            char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                            snprintf(description,sizeof(description),"Named argument '%s' is already specified.",argument_name);
                            fault_detail_at(r,"duplicate named argument","Duplicate named argument",description,
                                            argument_name,argument_token->line,argument_token->column);
                        }
                        if(r->error||!add_named_arg(member,parse_expr(r,1),argument_name)){fault(r,"out of memory");break;}
                    }else{if(saw_named){separan_token *argument_token=peek(r);fault_detail_at(r,"positional argument after named argument",
                        "Positional argument after named argument","Positional arguments must appear before named arguments.",
                        argument_token->lexeme,argument_token->line,argument_token->column);break;}if(!add_arg(member,parse_expr(r,1))){fault(r,"out of memory");break;}}
                }while(accept(r,"COMMA"));}expect_detail(r,"RPAREN","Syntax error","Expected ')' after arguments.");
            }
            left = member;
        }
    }
    return left;
}

static int is_state_literal(const Expr *expression) {
    return expression&&expression->kind==0&&expression->literal.kind==V_EMPTY;
}

static Expr *parse_expr(Runtime *r, int minimum) {
    Expr *left = parse_primary(r);
    while (!r->error) {
        int not_in=at(r,"NOT")&&r->at+1<r->tokens.count&&!strcmp(r->tokens.tokens[r->at+1].type,"IN");
        int level=not_in?5:precedence(peek(r)->type);
        if (level < minimum) break;
        int comparison=not_in||!strcmp(peek(r)->type,"IN")||!strcmp(peek(r)->type,"EQUAL_EQUAL")||!strcmp(peek(r)->type,"BANG_EQUAL")||
            !strcmp(peek(r)->type,"LESS")||!strcmp(peek(r)->type,"LESS_EQUAL")||!strcmp(peek(r)->type,"GREATER")||!strcmp(peek(r)->type,"GREATER_EQUAL");
        if(comparison&&left&&left->kind==3){const char *previous=left->text;if(!strcmp(previous,"IN")||!strcmp(previous,"NOT_IN")||!strcmp(previous,"EQUAL_EQUAL")||
            !strcmp(previous,"BANG_EQUAL")||!strcmp(previous,"LESS")||!strcmp(previous,"LESS_EQUAL")||!strcmp(previous,"GREATER")||!strcmp(previous,"GREATER_EQUAL")){fault(r,"chained comparison");break;}}
        separan_token *op = take(r);if(not_in)take(r);
        Expr *node = new_expr(3); if (!node) return left;
        node->line=op->line;node->column=op->column;
        node->text = copy_text(not_in?"NOT_IN":op->type); node->left = left;
        node->right = parse_expr(r, level + (!strcmp(op->type,"POWER")||!strcmp(op->type,"EMPTY_COALESCE") ? 0 : 1));
        if((!strcmp(op->type,"EQUAL_EQUAL")||!strcmp(op->type,"BANG_EQUAL"))&&
           (is_state_literal(node->left)||is_state_literal(node->right))){
            snprintf(r->error_category,sizeof(r->error_category),"Invalid state test");
            snprintf(r->error_description,sizeof(r->error_description),"Use 'is EMPTY' / 'is EMPTYS' state syntax instead of equality.");
            snprintf(r->error_expected,sizeof(r->error_expected),"is EMPTY or is EMPTYS");
            snprintf(r->error_actual,sizeof(r->error_actual),"%s",op->lexeme);
            fault_at(r,"EMPTY equality is invalid",op->line,op->column);
        }
        left = node;
    }
    if(minimum==1&&accept(r,"IS")){
        int negate=accept(r,"NOT");Expr *node=new_expr(9);if(!node)return left;
        node->left=left;node->literal.boolean=negate;
        if(accept(r,"EMPTY"))node->text=copy_text("EMPTY");
        else if(accept(r,"EMPTYS"))node->text=copy_text("EMPTYS");
        else{
            snprintf(r->error_category,sizeof(r->error_category),"Invalid state test");
            snprintf(r->error_description,sizeof(r->error_description),"The 'is' operator is reserved for EMPTY and EMPTYS state tests.");
            snprintf(r->error_expected,sizeof(r->error_expected),"EMPTY or EMPTYS");
            snprintf(r->error_actual,sizeof(r->error_actual),"%s",peek(r)->lexeme);
            fault(r,"expected EMPTY or EMPTYS");
        }
        left=node;
    }
    return left;
}

static int starts_index_assignment(Runtime *r) {
    if (!at(r,"IDENTIFIER") || r->at+1>=r->tokens.count ||
        strcmp(r->tokens.tokens[r->at+1].type,"LBRACKET")) return 0;
    size_t at=r->at+1;int depth=0,saw=0;
    for(;at<r->tokens.count;at++){
        const char *type=r->tokens.tokens[at].type;
        if(!strcmp(type,"LBRACKET")){depth++;saw=1;}
        else if(!strcmp(type,"RBRACKET")){if(--depth<0)return 0;}
        else if(!depth)return saw&&!strcmp(type,"EQUAL");
        if(!strcmp(type,"NEWLINE")||!strcmp(type,"EOF"))return 0;
    }
    return 0;
}
static int scalar_type_name(const char *name) {
    static const char *names[]={"number","string","boolean","bytes","object","duration","timezone","local_datetime","datetime","db_connection","exec_result","error"};
    for(size_t i=0;i<sizeof(names)/sizeof(*names);i++)if(!strcmp(name,names[i]))return 1;
    return 0;
}
static int starts_typed_declaration(Runtime *r) {
    if(at(r,"LIST"))return r->at+1<r->tokens.count&&!strcmp(r->tokens.tokens[r->at+1].type,"LESS");
    return at(r,"IDENTIFIER")&&scalar_type_name(peek(r)->lexeme)&&r->at+1<r->tokens.count&&
           !strcmp(r->tokens.tokens[r->at+1].type,"IDENTIFIER");
}
static char *parse_declared_type(Runtime *r) {
    if(accept(r,"LIST")){
        expect_syntax(r,"LESS","Typed lists require an element type, for example list<number>.");
        char *element=parse_declared_type(r);expect_syntax(r,"GREATER","Expected '>' after list element type.");
        if(!element)return NULL;size_t length=strlen(element)+7;char *type=malloc(length);
        if(type)snprintf(type,length,"list<%s>",element);free(element);return type;
    }
    if(at(r,"IDENTIFIER")&&scalar_type_name(peek(r)->lexeme))return copy_text(take(r)->lexeme);
    if(at(r,"IDENTIFIER")){
        separan_token *type_token=peek(r);char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
        snprintf(description,sizeof(description),"'%s' is not a supported Separan type.",type_token->lexeme);
        fault_detail_at(r,"invalid declared type","Unknown declared type",description,
                        type_token->lexeme,type_token->line,type_token->column);
        snprintf(r->error_expected,sizeof(r->error_expected),"a supported Separan type");
    }else fault(r,"invalid declared type");
    return NULL;
}
static Stmt *parse_typed_declaration(Runtime *r,int constant) {
    Stmt *s=new_stmt(19);s->constant=constant;s->declared_type=parse_declared_type(r);
    separan_token *name_token=at(r,"IDENTIFIER")?take(r):NULL;
    if(name_token)s->name=copy_text(name_token->lexeme);else fault_syntax(r,"expected variable name","Expected variable name after declared type.");
    if(!accept(r,"EQUAL")){
        if(name_token&&!r->error){
            char expected[SEPARAN_RUNTIME_DIAGNOSTIC_LEN],actual[SEPARAN_RUNTIME_DIAGNOSTIC_LEN],description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
            snprintf(expected,sizeof(expected),"%s %s = value",s->declared_type?s->declared_type:"",s->name?s->name:"");
            snprintf(actual,sizeof(actual),"%s %s",s->declared_type?s->declared_type:"",s->name?s->name:"");
            snprintf(description,sizeof(description),"Typed variable '%s' requires an initial value.",s->name?s->name:"");
            snprintf(r->error_category,sizeof(r->error_category),"Initializer required");
            snprintf(r->error_description,sizeof(r->error_description),"%s",description);
            snprintf(r->error_expected,sizeof(r->error_expected),"%s",expected);
            snprintf(r->error_actual,sizeof(r->error_actual),"%s",actual);
            fault_at(r,"initializer required",name_token->line,name_token->column);
        }else fault(r,"initializer required");
        return s;
    }
    s->expr=parse_expr(r,1);return s;
}
static const char *assignment_operator(const char *type) {
    if(!strcmp(type,"PLUS_EQUAL"))return "PLUS";if(!strcmp(type,"MINUS_EQUAL"))return "MINUS";
    if(!strcmp(type,"STAR_EQUAL"))return "STAR";if(!strcmp(type,"SLASH_EQUAL"))return "SLASH";
    if(!strcmp(type,"FLOOR_DIV_EQUAL"))return "FLOOR_DIV";if(!strcmp(type,"PERCENT_EQUAL"))return "PERCENT";
    if(!strcmp(type,"POWER_EQUAL"))return "POWER";return NULL;
}

static Body parse_body(Runtime *r, const char *stop_a, const char *stop_b);
static const char *expected_closer_type(const char *stop_a,const char *stop_b);
static Body parse_block_body(Runtime *r,separan_token *opener,const char *stop_a,const char *stop_b) {
    size_t old_line=r->parse_open_line,old_column=r->parse_open_column;
    const char *old_label=r->parse_open_label;
    ParseOpenFrame frame={0};
    if(opener){
        r->parse_open_line=opener->line;r->parse_open_column=opener->column;r->parse_open_label=opener->lexeme;
        frame.label=opener->lexeme;frame.closer=expected_closer_type(stop_a,stop_b);
        frame.line=opener->line;frame.column=opener->column;frame.parent=r->parse_open_frame;
        r->parse_open_frame=&frame;
    }
    Body body=parse_body(r,stop_a,stop_b);
    if(opener)r->parse_open_frame=frame.parent;
    r->parse_open_line=old_line;r->parse_open_column=old_column;r->parse_open_label=old_label;return body;
}
static int closer_token(const char *type) {
    const char *closers[]={"END_SEP","ENDIF","ENDWHILE","ENDFOR","END_OBJECT","END_LIST","ENDTRY","END_ERROR","END_HTTP_ROUTE","END_TRANSACTION","ELSE","ELSEIF","CATCH","FINALLY"};
    for(size_t i=0;i<sizeof(closers)/sizeof(*closers);i++)if(!strcmp(type,closers[i]))return 1;
    return 0;
}
static const char *expected_closer_type(const char *stop_a,const char *stop_b) {
    if(stop_b&&!strcmp(stop_b,"ENDIF"))return "ENDIF";
    if(stop_a&&(!strcmp(stop_a,"CATCH")||!strcmp(stop_a,"FINALLY")))return "ENDTRY";
    return stop_a;
}
static const char *closer_spelling(const char *type) {
    if(!type)return "end";
    if(!strcmp(type,"END_SEP"))return "END_SEP";
    if(!strcmp(type,"ENDIF"))return "endif";
    if(!strcmp(type,"ENDWHILE"))return "endwhile";
    if(!strcmp(type,"ENDFOR"))return "endfor";
    if(!strcmp(type,"END_OBJECT"))return "end_object";
    if(!strcmp(type,"END_LIST"))return "end_list";
    if(!strcmp(type,"ENDTRY"))return "endtry";
    if(!strcmp(type,"END_ERROR"))return "end_error";
    if(!strcmp(type,"END_HTTP_ROUTE"))return "end_http_route";
    if(!strcmp(type,"END_TRANSACTION"))return "end_transaction";
    return type;
}

static const char *integer_text(Value value,char buffer[32]) {
    if(value.big_integer)return value.big_integer;
    snprintf(buffer,32,"%lld",(long long)value.integer);return buffer;
}
static const char *big_abs(const char *value){return *value=='-'?value+1:value;}
static int big_abs_compare(const char *a,const char *b){a=big_abs(a);b=big_abs(b);size_t an=strlen(a),bn=strlen(b);return an!=bn?(an>bn?1:-1):strcmp(a,b)>0?1:strcmp(a,b)<0?-1:0;}
static int big_compare(const char *a,const char *b){int na=*a=='-',nb=*b=='-';if(na!=nb)return na?-1:1;int c=big_abs_compare(a,b);return na?-c:c;}
static char *big_abs_add(const char *a,const char *b){a=big_abs(a);b=big_abs(b);size_t an=strlen(a),bn=strlen(b),n=(an>bn?an:bn)+1;char *out=malloc(n+1);if(!out)return NULL;out[n]=0;int carry=0;for(size_t k=0;k<n;k++){int x=an>k?a[an-1-k]-'0':0,y=bn>k?b[bn-1-k]-'0':0,s=x+y+carry;out[n-1-k]=(char)('0'+s%10);carry=s/10;}char *start=out;while(start[0]=='0'&&start[1])start++;if(start!=out)memmove(out,start,strlen(start)+1);return out;}
static char *big_abs_sub(const char *a,const char *b){a=big_abs(a);b=big_abs(b);size_t an=strlen(a),bn=strlen(b);char *out=malloc(an+1);if(!out)return NULL;out[an]=0;int borrow=0;for(size_t k=0;k<an;k++){int x=a[an-1-k]-'0'-borrow,y=bn>k?b[bn-1-k]-'0':0;if(x<y){x+=10;borrow=1;}else borrow=0;out[an-1-k]=(char)('0'+x-y);}size_t skip=0;while(out[skip]=='0'&&out[skip+1])skip++;if(skip)memmove(out,out+skip,an-skip+1);return out;}
static char *big_signed(char *magnitude,int negative){if(!magnitude)return NULL;if(!negative||!strcmp(magnitude,"0"))return magnitude;size_t n=strlen(magnitude);char *out=malloc(n+2);if(!out){free(magnitude);return NULL;}out[0]='-';memcpy(out+1,magnitude,n+1);free(magnitude);return out;}
static char *big_add(const char *a,const char *b){int na=*a=='-',nb=*b=='-';if(na==nb)return big_signed(big_abs_add(a,b),na);int c=big_abs_compare(a,b);if(!c)return copy_text("0");return c>0?big_signed(big_abs_sub(a,b),na):big_signed(big_abs_sub(b,a),nb);}
static char *big_negate(const char *a){if(!strcmp(a,"0"))return copy_text(a);size_t n=strlen(a);if(*a=='-')return copy_text(a+1);char *out=malloc(n+2);if(out){out[0]='-';memcpy(out+1,a,n+1);}return out;}
static char *big_multiply(const char *a,const char *b){int negative=(*a=='-')!=(*b=='-');a=big_abs(a);b=big_abs(b);size_t an=strlen(a),bn=strlen(b);if(!strcmp(a,"0")||!strcmp(b,"0"))return copy_text("0");unsigned *digits=calloc(an+bn,sizeof(*digits));if(!digits)return NULL;for(size_t i=an;i--;)for(size_t j=bn;j--;)digits[i+j+1]+=(unsigned)(a[i]-'0')*(unsigned)(b[j]-'0');for(size_t i=an+bn-1;i;i--){digits[i-1]+=digits[i]/10;digits[i]%=10;}size_t skip=digits[0]?0:1,n=an+bn-skip;char *magnitude=malloc(n+1);if(!magnitude){free(digits);return NULL;}for(size_t i=0;i<n;i++)magnitude[i]=(char)('0'+digits[i+skip]);magnitude[n]=0;free(digits);return big_signed(magnitude,negative);}
static char *big_append_digit(const char *a,char digit){size_t skip=!strcmp(a,"0"),n=strlen(a)-skip;char *out=malloc(n+2);if(!out)return NULL;if(n)memcpy(out,a+skip,n);out[n]=digit;out[n+1]=0;return out;}
static int big_divmod_abs(const char *a,const char *b,char **quotient,char **remainder){if(!strcmp(b,"0"))return 0;size_t n=strlen(a);char *q=malloc(n+1),*rem=copy_text("0");if(!q||!rem){free(q);free(rem);return 0;}for(size_t i=0;i<n;i++){char *next=big_append_digit(rem,a[i]);free(rem);rem=next;if(!rem){free(q);return 0;}int digit=0;while(big_abs_compare(rem,b)>=0&&digit<10){next=big_abs_sub(rem,b);free(rem);rem=next;if(!rem){free(q);return 0;}digit++;}q[i]=(char)('0'+digit);}q[n]=0;size_t skip=0;while(q[skip]=='0'&&q[skip+1])skip++;if(skip)memmove(q,q+skip,n-skip+1);*quotient=q;*remainder=rem;return 1;}
static char *big_from_base(const char *digits,int base){char *value=copy_text("0");for(;*digits;digits++){char factor[4];snprintf(factor,sizeof(factor),"%d",base);char *scaled=big_multiply(value,factor);free(value);int digit=*digits>='0'&&*digits<='9'?*digits-'0':tolower((unsigned char)*digits)-'a'+10;char decimal[3];snprintf(decimal,sizeof(decimal),"%d",digit);value=big_add(scaled,decimal);free(scaled);if(!value)return NULL;}return value;}
static Value big_result(char *text){if(!text)return empty_value();Value result=integer_text_value(text);free(text);return result;}
static int big_divmod(const char *a,const char *b,char **quotient,char **remainder){int na=*a=='-',nb=*b=='-';char *q=NULL,*r=NULL;if(!big_divmod_abs(big_abs(a),big_abs(b),&q,&r))return 0;q=big_signed(q,na!=nb);r=big_signed(r,na);if(strcmp(r,"0")&&na!=nb){char *adjusted=big_add(q,"-1");free(q);q=adjusted;adjusted=big_add(r,b);free(r);r=adjusted;}if(!q||!r){free(q);free(r);return 0;}*quotient=q;*remainder=r;return 1;}
static char *big_power(const char *base,uint64_t exponent){char *result=copy_text("1"),*factor=copy_text(base);if(!result||!factor){free(result);free(factor);return NULL;}while(exponent){if(exponent&1){char *next=big_multiply(result,factor);free(result);result=next;if(!result){free(factor);return NULL;}}exponent>>=1;if(exponent){char *next=big_multiply(factor,factor);free(factor);factor=next;if(!factor){free(result);return NULL;}}}free(factor);return result;}
static char *big_gcd(const char *a,const char *b){char *left=copy_text(big_abs(a)),*right=copy_text(big_abs(b));if(!left||!right){free(left);free(right);return NULL;}while(strcmp(right,"0")){char *q=NULL,*remainder=NULL;if(!big_divmod_abs(left,right,&q,&remainder)){free(left);free(right);return NULL;}free(q);free(left);left=right;right=remainder;}free(right);return left;}
static int big_unsigned_u64(const char *text,uint64_t *value){
    if(!text||*text=='-')return 0;uint64_t result=0;
    for(;*text;text++){if(*text<'0'||*text>'9'||result>(UINT64_MAX-(uint64_t)(*text-'0'))/10)return 0;result=result*10+(uint64_t)(*text-'0');}
    *value=result;return 1;
}
static char *integer_span_text(Value minimum,Value maximum){
    char minimum_text[32],maximum_text[32];
    if(!minimum.exact_integer||!maximum.exact_integer||big_compare(integer_text(minimum,minimum_text),integer_text(maximum,maximum_text))>0)return NULL;
    char *negative=big_negate(integer_text(minimum,minimum_text));
    char *difference=negative?big_add(integer_text(maximum,maximum_text),negative):NULL;free(negative);
    char *inclusive=difference?big_add(difference,"1"):NULL;free(difference);return inclusive;
}
static int integer_span_u64(Value minimum,Value maximum,uint64_t *span){
    char *inclusive=integer_span_text(minimum,maximum);int ok=inclusive&&big_unsigned_u64(inclusive,span)&&*span;free(inclusive);return ok;
}
static Value integer_offset(Value minimum,uint64_t offset){
    char minimum_text[32],increment[32];snprintf(increment,sizeof(increment),"%llu",(unsigned long long)offset);
    return big_result(big_add(integer_text(minimum,minimum_text),increment));
}
static Value integer_offset_text(Value minimum,const char *offset){
    char minimum_text[32];return big_result(big_add(integer_text(minimum,minimum_text),offset));
}
static int big_power_within_limit(const char *base,uint64_t exponent){
    const char *magnitude=big_abs(base);size_t digits=strlen(magnitude);
    if(!exponent||!strcmp(magnitude,"0")||!strcmp(magnitude,"1"))return 1;
    return digits&&(exponent<=(SEPARAN_MAX_BIG_INTEGER_DIGITS-1)/digits);
}
static int number_compare(Value left,Value right){
    if(left.exact_integer&&right.exact_integer){char a[32],b[32];return big_compare(integer_text(left,a),integer_text(right,b));}
    if(!left.exact_integer&&!right.exact_integer)return (left.number>right.number)-(left.number<right.number);
    Value integer=left.exact_integer?left:right;double floating=left.exact_integer?right.number:left.number;int direction=left.exact_integer?1:-1;
    if(isnan(floating))return 0;if(isinf(floating))return (floating>0?-1:1)*direction;
    double floored=floor(floating);char decimal[512],ibuffer[32];snprintf(decimal,sizeof(decimal),"%.0f",floored);
    int compared=big_compare(integer_text(integer,ibuffer),decimal);
    if(!compared&&floating!=floored)compared=-1;
    return compared*direction;
}
static Stmt *parse_stmt_inner(Runtime *r) {
    separan_token *head = peek(r);
    if(at(r,"COLON")&&r->at+1<r->tokens.count&&!strcmp(r->tokens.tokens[r->at+1].type,"IDENTIFIER")&&
       !strcmp(r->tokens.tokens[r->at+1].lexeme,"end")){
        snprintf(r->error_category,sizeof(r->error_category),"Incomplete structural completion token");
        snprintf(r->error_description,sizeof(r->error_description),":end is an editor completion trigger, not executable Separan syntax.");
        snprintf(r->error_expected,sizeof(r->error_expected),"a complete block closer");
        snprintf(r->error_actual,sizeof(r->error_actual),":end");
        fault_at(r,"incomplete structural token",head->line,head->column);return new_stmt(6);
    }
    if(at(r,"COLON")){fault(r,"incomplete structural token");return new_stmt(6);}
    if(at(r,"TAG")){
        const char *category=r->parse_depth?"Function tag must appear before executable statements":"Function tag outside function";
        const char *description=r->parse_depth?
            "Function tags belong to the metadata area before the first executable statement.":
            "Function tags are valid only inside a function metadata area.";
        char actual[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];snprintf(actual,sizeof(actual),"@%s",head->lexeme);
        fault_detail_at(r,r->parse_depth?"tag after statement":"tag outside function",category,description,actual,head->line,head->column);
        return new_stmt(6);
    }
    if(at(r,"IDENTIFIER")&&!strcmp(head->lexeme,"system")){
        if(r->at+1<r->tokens.count&&!strcmp(r->tokens.tokens[r->at+1].type,"DOT")){
            const char *member=r->at+2<r->tokens.count?r->tokens.tokens[r->at+2].lexeme:"";
            char actual[SEPARAN_RUNTIME_DIAGNOSTIC_LEN],description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
            snprintf(actual,sizeof(actual),"system.%s",member);
            snprintf(description,sizeof(description),"Cannot assign to read-only member '%s'.",actual);
            fault_detail_at(r,"immutable system member","Immutable member",description,actual,head->line,head->column);
        }else{
            fault_detail_at(r,"reserved system binding","Reserved context name",
                            "Name 'system' is reserved for a read-only runtime context.","system",head->line,head->column);
        }
        return new_stmt(6);
    }
    if(at(r,"IDENTIFIER")&&(!strcmp(head->lexeme,"function")||!strcmp(head->lexeme,"end_function"))){
        fault(r,"legacy function syntax");return new_stmt(6);
    }
    if(accept(r,"IMPORT")){
        Stmt *s=new_stmt(15);if(at(r,"STRING"))s->expr=parse_atom(r);else fault_syntax(r,"expected import path","Expected quoted .sep path after import.");
        expect_syntax(r,"AS","Expected 'as' after import path.");if(at(r,"IDENTIFIER"))s->name=copy_text(take(r)->lexeme);else fault_syntax(r,"expected import alias","Expected import alias.");return s;
    }
    if (accept(r, "SEP")) {
        Stmt *s = new_stmt(5);
        separan_token *block_label=NULL;
        expect_syntax(r,"COLON","Expected ':' after function.");
        if (at(r, "IDENTIFIER")){block_label=take(r);s->name = copy_text(block_label->lexeme);s->name_line=block_label->line;s->name_column=block_label->column;} else fault_syntax(r,"expected function name","Expected function name.");
        if (accept(r, "LPAREN")) {
            if (!at(r, "RPAREN")) do {
                if (!at(r, "IDENTIFIER")) { fault_syntax(r,"expected parameter","Expected parameter name."); break; }
                separan_token *parameter_token=take(r);char *parameter=copy_text(parameter_token->lexeme);char *type=NULL;
                if(!strcmp(parameter,"system"))fault_detail_at(r,"reserved system binding","Reserved context name",
                    "Name 'system' is reserved for a read-only runtime context.","system",parameter_token->line,parameter_token->column);
                for(size_t i=0;i<s->parameter_count;i++)if(!strcmp(s->parameters[i],parameter)){
                    if(!r->error){
                        snprintf(r->error_category,sizeof(r->error_category),"Duplicate parameter");
                        snprintf(r->error_description,sizeof(r->error_description),"Parameter '%s' is already defined.",parameter);
                        snprintf(r->error_actual,sizeof(r->error_actual),"%s",parameter);
                    }
                    fault_at(r,"duplicate parameter",parameter_token->line,parameter_token->column);
                }
                if(accept(r,"COLON"))type=parse_declared_type(r);
                char **next = realloc(s->parameters, (s->parameter_count + 1) * sizeof(*next));
                char **next_types=realloc(s->parameter_types,(s->parameter_count+1)*sizeof(*next_types));
                if (!next||!next_types) {free(parameter);free(type);fault(r, "out of memory"); break; }
                s->parameters=next;s->parameter_types=next_types;s->parameters[s->parameter_count]=parameter;
                s->parameter_types[s->parameter_count++]=type;
            } while (accept(r, "COMMA"));
            expect_syntax(r,"RPAREN","Expected ')' after parameters.");
        }
        expect_line_end(r);
        while(at(r,"TAG")){separan_token *tag_token=take(r);const char *tag=tag_token->lexeme;if(strlen(tag)<2)fault_at(r,"tag outside function",tag_token->line,tag_token->column);
            for(size_t i=0;i<s->tag_count;i++)if(!strcmp(s->tags[i],tag)){
                char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN],actual[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                snprintf(description,sizeof(description),"Tag '@%s' is already attached to function '%s'.",tag,s->name?s->name:"");
                snprintf(actual,sizeof(actual),"@%s",tag);
                fault_detail_at(r,"invalid or duplicate function tag","Duplicate function tag",description,actual,
                                tag_token->line,tag_token->column);
            }
            char **next=realloc(s->tags,(s->tag_count+1)*sizeof(*next));if(!next)fault(r,"out of memory");else{s->tags=next;s->tags[s->tag_count++]=copy_text(tag);}expect_line_end(r);}
        s->body = parse_block_body(r,block_label?block_label:head,"END_SEP", NULL);
        s->end_line=peek(r)->line;
        expect_block_closer(r,"END_SEP","SEP"); expect_block_closer_colon(r);
        if (s->name) check_closing_label(r,s->name,"function label mismatch",s->name_line,s->name_column);
        else if (!r->error) fault_syntax(r,"expected function label","Expected closing block label.");
        return s;
    }
    if (accept(r, "FOR")) {
        Stmt *s = new_stmt(7);
        separan_token *block_label=NULL;
        if (at(r, "IDENTIFIER")) {
            s->parameters = calloc(1, sizeof(*s->parameters));
            if (!s->parameters) { fault(r, "out of memory"); return s; }
            s->parameters[0] = copy_text(take(r)->lexeme); s->parameter_count = 1;
        } else fault_syntax(r,"expected loop variable","Expected loop variable.");
        expect_syntax(r,"IN","Expected 'in' after loop variable."); s->expr = parse_expr(r, 1);
        expect_syntax(r,"COLON","Expected :label after for expression.");
        if (at_label(r)){block_label=take(r);s->name = copy_text(block_label->lexeme);s->name_line=block_label->line;s->name_column=block_label->column;} else fault_syntax(r,"expected label","Expected block label after ':'.");
        expect_line_end(r); s->body = parse_block_body(r,block_label?block_label:head,"ENDFOR", NULL);
        expect_block_closer(r,"ENDFOR","for"); expect_block_closer_colon(r);
        if (s->name) check_closing_label(r,s->name,"block label mismatch",s->name_line,s->name_column);
        return s;
    }
    if (accept(r, "IF") || accept(r, "WHILE")) {
        int is_if = strcmp(head->type, "IF") == 0;
        Stmt *s = new_stmt(is_if ? 3 : 4);
        separan_token *block_label=NULL;
        s->expr = parse_expr(r, 1);
        expect_open_label_colon(r,is_if?"if":"while");
        if (at_label(r)){block_label=take(r);s->name = copy_text(block_label->lexeme);s->name_line=block_label->line;s->name_column=block_label->column;} else fault_syntax(r,"expected label","Expected block label after ':'.");
        expect_line_end(r);
        s->body = parse_block_body(r,block_label?block_label:head,is_if ? "ELSE" : "ENDWHILE", is_if ? "ENDIF" : NULL);
        Stmt *branch = s;
        while (is_if && accept(r, "ELSEIF")) {
            Stmt *next = new_stmt(3);
            if (!next || !add_stmt(&branch->other, next)) { fault(r, "out of memory"); break; }
            next->name = copy_text(s->name);
            next->expr = parse_expr(r, 1); expect_syntax(r,"COLON","Expected ':' after elseif.");
            if(s->name)check_closing_label(r,s->name,"branch label mismatch",s->name_line,s->name_column);
            expect_line_end(r);
            next->body = parse_block_body(r,block_label?block_label:head,"ELSE", "ENDIF");
            branch = next;
        }
        if (is_if && accept(r, "ELSE")) {
            expect_syntax(r,"COLON","Expected ':' after else.");
            if(s->name)check_closing_label(r,s->name,"branch label mismatch",s->name_line,s->name_column);
            expect_line_end(r); branch->other = parse_block_body(r,block_label?block_label:head,"ENDIF", NULL);
        }
        expect_block_closer(r,is_if?"ENDIF":"ENDWHILE",is_if?"if":"while"); expect_block_closer_colon(r);
        if (s->name) check_closing_label(r,s->name,"block label mismatch",s->name_line,s->name_column);
        return s;
    }
    if (accept(r,"TRY")) {
        Stmt *s=new_stmt(12);separan_token *block_label=NULL;
        if(!r->parse_depth){
            fault_detail_at(r,"top-level expression is not allowed","Invalid top-level statement",
                "Only function definitions, data blocks, const declarations, assignments, and print are allowed at top level.",head->lexeme,head->line,head->column);
        }
        expect_open_label_colon(r,"try");
        if(at_label(r)){block_label=take(r);s->name=copy_text(block_label->lexeme);s->name_line=block_label->line;s->name_column=block_label->column;}else fault_syntax(r,"expected label","Expected block label after ':'.");
        expect_line_end(r);s->body=parse_block_body(r,block_label?block_label:head,"CATCH","FINALLY");
        while(accept(r,"CATCH")){
            Stmt *branch=new_stmt(13);if(!branch||!add_stmt(&s->other,branch)){fault(r,"out of memory");break;}
            if(at(r,"IDENTIFIER")){separan_token *category=take(r);branch->name=copy_text(category->lexeme);branch->name_line=category->line;branch->name_column=category->column;}else fault_syntax(r,"expected error category","Expected error category after catch.");
            for(size_t i=0;branch->name&&i+1<s->other.count;i++){
                if(!strcmp(s->other.items[i]->name,branch->name)){
                    char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                    snprintf(description,sizeof(description),"Error category '%s' is already caught.",branch->name);
                    fault_detail_at(r,"duplicate catch","Duplicate catch",description,branch->name,
                                    branch->name_line,branch->name_column);
                }
                if(!strcmp(s->other.items[i]->name,"any"))
                    fault_detail_at(r,"catch after any","Catch after any","catch any must be the final catch branch.",
                                    branch->name,branch->name_line,branch->name_column);
            }
            expect_syntax(r,"COLON","Expected ':' after catch.");if(s->name)check_closing_label(r,s->name,"branch label mismatch",s->name_line,s->name_column);
            else if(!r->error)fault_syntax(r,"expected label","Expected label after catch.");
            expect_line_end(r);branch->body=parse_block_body(r,block_label?block_label:head,"CATCH","FINALLY");
        }
        if(accept(r,"FINALLY")){
            expect_syntax(r,"COLON","Expected ':' after finally.");if(s->name)check_closing_label(r,s->name,"branch label mismatch",s->name_line,s->name_column);
            else if(!r->error)fault_syntax(r,"expected label","Expected label after finally.");
            expect_line_end(r);s->final=parse_block_body(r,block_label?block_label:head,"ENDTRY",NULL);
        }
        if(!s->other.count&&!s->final.count)
            fault_detail_at(r,"empty try handler","Empty try handler",
                            "A try block requires at least one catch or finally branch.","",head->line,head->column);
        expect_block_closer(r,"ENDTRY","try");expect_block_closer_colon(r);
        if(s->name)check_closing_label(r,s->name,"block label mismatch",s->name_line,s->name_column);
        return s;
    }
    if(accept(r,"THROW")){Stmt *s=new_stmt(11);s->expr=parse_expr(r,1);return s;}
    if(accept(r,"ERROR")){
        Stmt *s=new_stmt(14);expect_syntax(r,"COLON","Expected ':' after error.");if(at(r,"IDENTIFIER")){separan_token *name=take(r);s->name=copy_text(name->lexeme);s->name_line=name->line;s->name_column=name->column;}else fault_syntax(r,"expected error name","Expected custom error name.");
        expect_line_end(r);newlines(r);expect_block_closer(r,"END_ERROR","error");expect_block_closer_colon(r);
        if(s->name)check_closing_label(r,s->name,"error label mismatch",s->name_line,s->name_column);return s;
    }
    if(accept(r,"HTTP_ROUTE")){
        Stmt *s=new_stmt(20);separan_token *block_label=NULL;
                    separan_token *method=at(r,"IDENTIFIER")?take(r):NULL;if(method)s->method=copy_text(method->lexeme);else fault(r,"invalid route method");
        if(s->method&&strcmp(s->method,"GET")&&strcmp(s->method,"HEAD")&&strcmp(s->method,"POST")&&
                            strcmp(s->method,"PUT")&&strcmp(s->method,"PATCH")&&strcmp(s->method,"DELETE"))
                        fault_detail_at(r,"invalid route method","Invalid route method",
                                "Route method must be an uppercase supported HTTP method.",s->method,method->line,method->column);
        if(at(r,"STRING")){Expr *path=parse_atom(r);if(path&&path->literal.kind==V_STRING){s->path=copy_text(path->literal.string);s->path_line=path->line;s->path_column=path->column;}free_expr(path);}
        else fault(r,"invalid route path");
        if(s->path&&(s->path[0]!='/'||strchr(s->path,'?')||strchr(s->path,'#')))
            fault_detail_at(r,"invalid route path","Invalid route path",
                "Route path must start with '/' and exclude query/fragment.",s->path,s->path_line,s->path_column);
        expect_open_label_colon(r,"http_route");if(at_label(r)){block_label=take(r);s->name=copy_text(block_label->lexeme);s->name_line=block_label->line;s->name_column=block_label->column;}else fault_syntax(r,"expected label","Expected block label after ':'.");
        expect_line_end(r);s->body=parse_block_body(r,block_label?block_label:head,"END_HTTP_ROUTE",NULL);expect_block_closer(r,"END_HTTP_ROUTE","http_route");expect_block_closer_colon(r);
        if(s->name)check_closing_label(r,s->name,"block label mismatch",s->name_line,s->name_column);return s;
    }
    if(accept(r,"TRANSACTION")){
        Stmt *s=new_stmt(17);separan_token *block_label=NULL;s->expr=parse_expr(r,1);expect_open_label_colon(r,"transaction");
        if(at_label(r)){block_label=take(r);s->name=copy_text(block_label->lexeme);s->name_line=block_label->line;s->name_column=block_label->column;}else fault_syntax(r,"expected label","Expected block label after ':'.");
        expect_line_end(r);s->body=parse_block_body(r,block_label?block_label:head,"END_TRANSACTION",NULL);expect_block_closer(r,"END_TRANSACTION","transaction");expect_block_closer_colon(r);
        if(s->name)check_closing_label(r,s->name,"block label mismatch",s->name_line,s->name_column);return s;
    }
    if(accept(r,"PRINT_ERROR")){Stmt *s=new_stmt(16);s->expr=parse_expr(r,1);return s;}
    if (accept(r, "PRINT") || accept(r, "RETURN")) {
        Stmt *s = new_stmt(strcmp(head->type, "PRINT") == 0 ? 1 : 2);
        if (!at(r, "NEWLINE") && !at(r, "EOF")) s->expr = parse_expr(r, 1);
        return s;
    }
    if(at(r,"CONST")&&r->at+1<r->tokens.count){
        size_t saved=r->at;take(r);if(starts_typed_declaration(r))return parse_typed_declaration(r,1);r->at=saved;
    }
    if(starts_typed_declaration(r))return parse_typed_declaration(r,0);
    if (accept(r, "CONST")) {
        Stmt *s = new_stmt(8);
        if (at(r, "IDENTIFIER")) s->name = copy_text(take(r)->lexeme);
        else fault_syntax(r,"expected constant name","Expected constant name after 'const'.");
        expect_syntax(r,"EQUAL","Expected '=' after constant name."); s->expr = parse_expr(r, 1); return s;
    }
    if (accept(r, "OBJECT")) {
        Stmt *s = new_stmt(9);separan_token *block_label=NULL;
        expect_syntax(r,"COLON","Expected ':' after object.");
        if (at(r, "IDENTIFIER")){block_label=take(r);s->name = copy_text(block_label->lexeme);s->name_line=block_label->line;s->name_column=block_label->column;}
        else fault_syntax(r,"expected object name","Expected object name.");
        expect_line_end(r);
        s->body = parse_block_body(r,block_label?block_label:head,"END_OBJECT", NULL);
        for(size_t i=0;i<s->body.count&&!r->error;i++){
            Stmt *field=s->body.items[i];if(field->kind!=0&&field->kind!=9&&field->kind!=10&&field->kind!=19)fault_at(r,"invalid object entry",field->line,field->column);
            for(size_t j=0;j<i&&!r->error;j++)if(field->name&&s->body.items[j]->name&&!strcmp(field->name,s->body.items[j]->name)){
                if(!r->error){
                    snprintf(r->error_category,sizeof(r->error_category),"Duplicate object field");
                    snprintf(r->error_description,sizeof(r->error_description),"Field '%s' is already defined in object :%s.",field->name,s->name?s->name:"");
                    snprintf(r->error_actual,sizeof(r->error_actual),"%s",field->name);
                }
                fault_at(r,"duplicate object field",field->line,field->column);
            }
        }
        expect_block_closer(r,"END_OBJECT","object"); expect_block_closer_colon(r);
        if(s->name)check_closing_label(r,s->name,"object label mismatch",s->name_line,s->name_column);
        return s;
    }
    if (accept(r, "LIST")) {
        Stmt *s = new_stmt(10);separan_token *block_label=NULL;
        expect_syntax(r,"COLON","Expected ':' after list.");
        if (at(r, "IDENTIFIER")){block_label=take(r);s->name = copy_text(block_label->lexeme);s->name_line=block_label->line;s->name_column=block_label->column;}
        else fault_syntax(r,"expected list name","Expected list name.");
        expect_line_end(r);
        s->body = parse_block_body(r,block_label?block_label:head,"END_LIST", NULL);
        expect_block_closer(r,"END_LIST","list"); expect_block_closer_colon(r);
        if(s->name)check_closing_label(r,s->name,"list label mismatch",s->name_line,s->name_column);
        return s;
    }
    if(starts_index_assignment(r)){
        Stmt *s=new_stmt(18);s->target=parse_primary(r);expect_syntax(r,"EQUAL","Expected '=' after indexed target.");s->expr=parse_expr(r,1);return s;
    }
    if (at(r, "IDENTIFIER") && r->at + 1 < r->tokens.count &&
        (!strcmp(r->tokens.tokens[r->at + 1].type,"EQUAL")||assignment_operator(r->tokens.tokens[r->at+1].type))) {
        Stmt *s = new_stmt(0);
        s->name = copy_text(take(r)->lexeme);
        if (!strcmp(s->name, "system")) fault_detail_at(r,"reserved system binding","Reserved context name",
            "Name 'system' is reserved for a read-only runtime context.","system",s->line,s->column);
        separan_token *assignment = take(r);
        Expr *right = parse_expr(r, 1);
        const char *op = assignment_operator(assignment->type);
        if (op) {
            Expr *binary = new_expr(3), *left = new_expr(1);
            if (!binary || !left) {
                free_expr(binary); free_expr(left); fault(r, "out of memory"); s->expr = right; return s;
            }
            left->text = copy_text(s->name); binary->text = copy_text(op); binary->left = left; binary->right = right; s->expr = binary;
        }
        else s->expr=right;return s;
    }
    Stmt *s = new_stmt(6); s->expr = parse_expr(r, 1); return s;
}

static Stmt *parse_stmt(Runtime *r) {
    separan_token *head=peek(r);Stmt *statement=parse_stmt_inner(r);
    if(statement){statement->line=head->line;statement->column=head->column;}
    return statement;
}

static Body parse_body(Runtime *r, const char *stop_a, const char *stop_b) {
    Body body = {0}; int seen_non_import=0,nested=stop_a||stop_b;if(nested)r->parse_depth++;newlines(r);
    while (!r->error && !at(r, "EOF") && !(stop_a && at(r, stop_a)) && !(stop_b && at(r, stop_b)) &&
           !(stop_a && strcmp(stop_a, "ELSE") == 0 && at(r, "ELSEIF")) &&
           !(stop_a && strcmp(stop_a,"CATCH")==0 && at(r,"ENDTRY"))) {
        if((at(r,"ELSE")||at(r,"ELSEIF"))&&stop_a&&strcmp(stop_a,"ELSE")&&strcmp(stop_a,"ELSEIF")){
            fault_detail_at(r,"invalid branch order","Invalid if branch",
                            "else must be the final branch and may occur only once.",peek(r)->lexeme,
                            peek(r)->line,peek(r)->column);break;
        }
        if(closer_token(peek(r)->type)){
            separan_token *closer=peek(r);const char *expected_type=expected_closer_type(stop_a,stop_b);
            separan_token *actual_label=(r->at+2<r->tokens.count&&
                !strcmp(r->tokens.tokens[r->at+1].type,"COLON"))?&r->tokens.tokens[r->at+2]:NULL;
            if(expected_type&&strcmp(closer->type,expected_type)&&r->parse_open_frame&&actual_label&&
               (!strcmp(actual_label->type,"IDENTIFIER")||!strcmp(actual_label->type,"LABEL"))){
                ParseOpenFrame *current=r->parse_open_frame;
                if(current->label&&!strcmp(actual_label->lexeme,current->label)){
                    snprintf(r->error_expected,sizeof(r->error_expected),"%s:%s",
                             closer_spelling(expected_type),current->label);
                    snprintf(r->error_actual,sizeof(r->error_actual),"%s:%s",
                             closer->lexeme,actual_label->lexeme);
                    r->error_related_line=current->line;
                    r->error_related_column=current->column;
                    fault_at(r,"block kind mismatch",closer->line,closer->column);
                    break;
                }
                for(ParseOpenFrame *ancestor=current->parent;ancestor;ancestor=ancestor->parent){
                    if(ancestor->closer&&!strcmp(ancestor->closer,closer->type)&&ancestor->label&&
                       !strcmp(ancestor->label,actual_label->lexeme)){
                        snprintf(r->error_expected,sizeof(r->error_expected),"%s:%s",
                                 closer_spelling(expected_type),current->label?current->label:"");
                        snprintf(r->error_actual,sizeof(r->error_actual),"%s:%s",
                                 closer->lexeme,actual_label->lexeme);
                        r->error_related_line=current->line;
                        r->error_related_column=current->column;
                        fault_at(r,"block nesting error",closer->line,closer->column);
                        break;
                    }
                }
                if(r->error)break;
            }
            char actual[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
            if(actual_label)snprintf(actual,sizeof(actual),"%s:%s",closer->lexeme,actual_label->lexeme);
            else snprintf(actual,sizeof(actual),"%s",closer->lexeme);
            snprintf(r->error_actual,sizeof(r->error_actual),"%s",actual);
            fault_at(r,"unexpected closer",closer->line,closer->column);break;
        }
        size_t old = r->at;
        Stmt *stmt = parse_stmt(r);
        if (!stmt || !add_stmt(&body, stmt)) { fault(r, "out of memory"); break; }
        if(stmt->kind==15){
            if(stop_a||stop_b)fault_detail_at(r,"nested import","Nested import",
                "Imports are allowed only at top level.","",stmt->line,stmt->column);
            else if(seen_non_import)fault_detail_at(r,"import order","Late import",
                "Imports must appear before other top-level declarations and statements.","",stmt->line,stmt->column);
        }else{
            if((stop_a||stop_b)&&stmt->kind==20)fault_detail_at(r,"nested HTTP route","Nested HTTP route",
                "HTTP routes may only be declared at top level.","",stmt->line,stmt->column);
            seen_non_import=1;
            if(!stop_a&&!stop_b&&(stmt->kind==2||stmt->kind==3||stmt->kind==4||stmt->kind==7||stmt->kind==11||stmt->kind==12||stmt->kind==17))fault_detail_at(r,"top-level expression is not allowed","Invalid top-level statement",
                "Only function definitions, data blocks, const declarations, assignments, and print are allowed at top level.",r->tokens.tokens[old].lexeme,stmt->line,stmt->column);
            if((stop_a||stop_b)&&stmt->kind==5)fault_detail_at(r,"top-level expression is not allowed","Invalid top-level statement",
                "Only function definitions, data blocks, const declarations, assignments, and print are allowed at top level.",r->tokens.tokens[old].lexeme,stmt->line,stmt->column);
            if((stop_a||stop_b)&&stmt->kind==14)
                fault_detail_at(r,"nested error declaration","Nested error declaration",
                                "Custom errors may only be declared at top level.","",stmt->line,stmt->column);
        }
        if (!stop_a && !stop_b && stmt->kind == 6) fault_detail_at(r,"top-level expression is not allowed","Invalid top-level statement",
            "Only function definitions, data blocks, const declarations, assignments, and print are allowed at top level.",r->tokens.tokens[old].lexeme,stmt->line,stmt->column);
        if (!at(r, "EOF") && !at(r, "NEWLINE")) fault(r, "expected end of line");
        newlines(r);
        if (old == r->at) { fault(r, "parser did not advance"); break; }
    }
    if(!r->error&&at(r,"EOF")&&(stop_a||stop_b)){
        if(r->parse_open_frame&&r->parse_open_frame->closer&&r->parse_open_frame->label){
            snprintf(r->error_expected,sizeof(r->error_expected),"%s:%s",
                     closer_spelling(r->parse_open_frame->closer),r->parse_open_frame->label);
            r->error_related_line=r->parse_open_frame->line;
            r->error_related_column=r->parse_open_frame->column;
        }
        fault_at(r,"unclosed block",r->parse_open_line?r->parse_open_line:peek(r)->line,
                 r->parse_open_column?r->parse_open_column:peek(r)->column);
    }
    if(nested)r->parse_depth--;return body;
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
static int value_matches_type_part(Value value,const char *type,size_t length) {
    if(value.kind==V_EMPTY)return 1;
    if(length>6&&!memcmp(type,"list<",5)&&type[length-1]=='>'){
        if(value.kind!=V_LIST)return 0;
        for(size_t i=0;i<value.count;i++)if(!value_matches_type_part(value.items[i],type+5,length-6))return 0;
        return 1;
    }
    struct {const char *name;ValueKind kind;} types[]={
        {"number",V_NUMBER},{"string",V_STRING},{"boolean",V_BOOL},{"bytes",V_BYTES},
        {"object",V_OBJECT},{"duration",V_DURATION},{"timezone",V_TIMEZONE},
        {"local_datetime",V_LOCAL_DATETIME},{"datetime",V_DATETIME},{"db_connection",V_DB},
        {"exec_result",V_EXEC_RESULT},{"error",V_ERROR}};
    for(size_t i=0;i<sizeof(types)/sizeof(*types);i++)
        if(strlen(types[i].name)==length&&!memcmp(type,types[i].name,length))return value.kind==types[i].kind;
    return 0;
}
static int value_matches_type(Value value,const char *type) {
    return type&&value_matches_type_part(value,type,strlen(type));
}
static void retain_value_type_part(Value *value,const char *type,size_t length) {
    if(value->kind==V_EMPTY){
        free(value->retained_type);value->retained_type=malloc(length+1);
        if(value->retained_type){memcpy(value->retained_type,type,length);value->retained_type[length]=0;}
        return;
    }
    if(value->kind==V_LIST&&length>6&&!memcmp(type,"list<",5)&&type[length-1]=='>'){
        free(value->retained_type);value->retained_type=malloc(length+1);
        if(value->retained_type){memcpy(value->retained_type,type,length);value->retained_type[length]=0;}
        for(size_t i=0;i<value->count;i++)retain_value_type_part(&value->items[i],type+5,length-6);
    }
}
static void retain_value_type(Value *value,const char *type) {
    if(type)retain_value_type_part(value,type,strlen(type));
}
static int is_emptys_marker(Value value) {
    return value.kind==V_EMPTY&&value.retained_type&&!strcmp(value.retained_type,"__EMPTYS__");
}
static const char *scalar_kind_type(ValueKind kind) {
    static const char *types[]={"EMPTY","number","boolean","string","list","object","VOID","bytes","duration","timezone","local_datetime","datetime","db_connection","exec_result","error","namespace","EMPTY","regex_match_result"};
    return kind<sizeof(types)/sizeof(*types)?types[kind]:"EMPTY";
}
static char *value_type_text(Value value) {
    if(value.kind==V_EMPTY)return value.retained_type?copy_text(value.retained_type):NULL;
    if(value.retained_type)return copy_text(value.retained_type);
    if(value.kind!=V_LIST)return copy_text(scalar_kind_type(value.kind));
    char *element=NULL;
    for(size_t i=0;i<value.count&&!element;i++)element=value_type_text(value.items[i]);
    if(!element)return NULL;
    size_t length=strlen(element)+7;char *result=malloc(length);
    if(result)snprintf(result,length,"list<%s>",element);free(element);return result;
}
static void clear_effective_values(Value *value) {
    if(value->kind==V_LIST||value->kind==V_OBJECT||value->kind==V_EXEC_RESULT){
        for(size_t i=0;i<value->count;i++)clear_effective_values(&value->items[i]);return;
    }
    if(value->kind==V_EMPTY)return;
    char *type=copy_text(scalar_kind_type(value->kind));free_value(*value);*value=empty_value();value->retained_type=type;
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
    next[frame->count].declared_type = NULL;
    frame->count++; return 1;
}
static int bind_typed(Frame *frame,const char *name,const char *type,Value value,int constant) {
    if(lookup_local(frame,name)||!value_matches_type(value,type))return 0;
    if(!bind(frame,name,value,constant))return 0;
    Binding *binding=lookup_local(frame,name);binding->declared_type=copy_text(type);retain_value_type(&binding->value,type);
    return binding->declared_type!=NULL;
}
static void free_frame(Frame *frame) {
    for (size_t i = 0; i < frame->count; i++) { free(frame->bindings[i].name); free(frame->bindings[i].declared_type); free_value(frame->bindings[i].value); }
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
static Value invoke_named(Runtime *r, const char *name, Value *arguments, size_t count) {
    Stmt *function = find_function(r, name);
    if (!function) { fault(r, "unknown function"); return empty_value(); }
    if (function->parameter_count != count) { fault(r, "wrong argument count"); return empty_value(); }
    Frame local = {0}; local.parent = &r->global;
    for (size_t i = 0; i < count && !r->error; i++) {
        if(function->parameter_types&&function->parameter_types[i]){
            if(!value_matches_type(arguments[i],function->parameter_types[i]))fault(r,"variable type cannot change");
            else if(!bind_typed(&local,function->parameters[i],function->parameter_types[i],arguments[i],0))fault(r,"cannot bind parameter");
        }else if(arguments[i].kind==V_EMPTY&&!arguments[i].retained_type)fault(r,"untyped EMPTY");
        else {if(!function->inferred_parameter_types)function->inferred_parameter_types=calloc(function->parameter_count,sizeof(*function->inferred_parameter_types));
            char *actual=value_type_text(arguments[i]);if(!function->inferred_parameter_types||!actual)fault(r,"cannot bind parameter");
            else if(function->inferred_parameter_types[i]&&strcmp(function->inferred_parameter_types[i],actual))fault(r,"parameter type cannot change");
            else {if(!function->inferred_parameter_types[i])function->inferred_parameter_types[i]=copy_text(actual);bind(&local,function->parameters[i],arguments[i],0);}free(actual);}
    }
    execute_body(r, &local, function->body);
    Value result = r->returning ? r->returned : empty_value();
    r->returning = 0; r->returned = empty_value(); free_frame(&local); return result;
}
static int same_value(Value a, Value b) {
    if (a.kind != b.kind) return 0;
    if (a.kind == V_DB) return a.external == b.external;
    if(a.kind==V_NUMBER)return !number_compare(a,b);
    if (a.kind == V_BOOL) return a.boolean == b.boolean;
    if (a.kind == V_DURATION) return a.integer == b.integer;
    if (a.kind == V_DATETIME) return a.integer == b.integer;
    if (a.kind == V_TIMEZONE || a.kind == V_LOCAL_DATETIME)
        return a.string_length == b.string_length && !memcmp(a.string, b.string, a.string_length);
    if (a.kind == V_STRING || a.kind == V_BYTES) return a.string_length == b.string_length &&
        memcmp(a.string, b.string, a.string_length) == 0;
    if (a.kind == V_LIST || a.kind == V_OBJECT || a.kind == V_EXEC_RESULT || a.kind == V_ERROR || a.kind == V_REGEX) {
        if (a.count != b.count) return 0;
        for (size_t i = 0; i < a.count; i++) {
            if ((a.kind == V_OBJECT || a.kind == V_EXEC_RESULT || a.kind == V_ERROR || a.kind == V_REGEX) && strcmp(a.keys[i], b.keys[i])) return 0;
            if (!same_value(a.items[i], b.items[i])) return 0;
        }
    }
    return 1;
}
static int glob_segment_match(const char *pattern, const char *text) {
    while (*pattern) {
        if (*pattern == '*') {
            while (*pattern == '*') pattern++;
            if (!*pattern) return 1;
            do { if (glob_segment_match(pattern, text)) return 1; } while (*text++);
            return 0;
        }
        if (*pattern == '?') { if (!*text) return 0; pattern++; text++; continue; }
        if (*pattern == '[') {
            pattern++; int matched = 0, negate = *pattern == '!' || *pattern == '^'; if (negate) pattern++;
            unsigned char value = (unsigned char)*text; if (!value) return 0;
            while (*pattern && *pattern != ']') {
                unsigned char first = (unsigned char)*pattern++;
                if (*pattern == '-' && pattern[1] && pattern[1] != ']') {
                    pattern++; unsigned char last = (unsigned char)*pattern++;
                    if (value >= first && value <= last) matched = 1;
                } else if (value == first) matched = 1;
            }
            if (*pattern != ']') return 0; pattern++; text++;
            if (matched == negate) return 0;
            continue;
        }
        if (*pattern != *text) return 0;
        pattern++; text++;
    }
    return *text == 0;
}
static int glob_path_match(const char *pattern, const char *path) {
    const char *pattern_slash = strchr(pattern, '/'), *path_slash = strchr(path, '/');
    size_t pattern_length = pattern_slash ? (size_t)(pattern_slash-pattern) : strlen(pattern);
    size_t path_length = path_slash ? (size_t)(path_slash-path) : strlen(path);
    if (pattern_length == 2 && pattern[0] == '*' && pattern[1] == '*') {
        const char *rest = pattern_slash ? pattern_slash + 1 : pattern + 2;
        if (!*rest) return 1;
        if (glob_path_match(rest, path)) return 1;
        return path_slash ? glob_path_match(pattern, path_slash + 1) : 0;
    }
    if (pattern_length != strlen(pattern) || path_length != strlen(path)) {
        char *p = malloc(pattern_length + 1), *s = malloc(path_length + 1); int result = 0;
        if (!p || !s) { free(p); free(s); return 0; }
        memcpy(p,pattern,pattern_length);p[pattern_length]=0;memcpy(s,path,path_length);s[path_length]=0;
        if (glob_segment_match(p,s) && pattern_slash && path_slash) result=glob_path_match(pattern_slash+1,path_slash+1);
        free(p);free(s);return result;
    }
    return glob_segment_match(pattern,path);
}
static int append_glob_value(Value *list, const char *path) {
    Value *next = realloc(list->items, (list->count + 1) * sizeof(*next)); if (!next) return 0;
    list->items = next; list->items[list->count++] = string_value(path); return list->items[list->count-1].string != NULL;
}
static int collect_glob(Runtime *r, const char *directory, const char *pattern, Value *result, size_t depth) {
    if (depth > 64 || result->count > 100000) return 0;
    char **names = NULL; size_t count = 0;
    if (separan_files_list_directory(&r->files, directory, &names, &count)) return 0;
    for (size_t i=0;i<count;i++) {
        size_t directory_length = !strcmp(directory,".") ? 0 : strlen(directory);
        size_t length = directory_length + (directory_length?1:0) + strlen(names[i]);
        char *path = malloc(length+1); if (!path) { separan_files_list_free(names,count); return 0; }
        if(directory_length){memcpy(path,directory,directory_length);path[directory_length]='/';strcpy(path+directory_length+1,names[i]);}else strcpy(path,names[i]);
        if (glob_path_match(pattern,path) && !append_glob_value(result,path)) { free(path);separan_files_list_free(names,count);return 0; }
        int is_directory=0; if (!separan_files_directory_exists(&r->files,path,&is_directory) && is_directory)
            if (!collect_glob(r,path,pattern,result,depth+1)) { free(path);separan_files_list_free(names,count);return 0; }
        free(path);
    }
    separan_files_list_free(names,count); return 1;
}
static int compare_string_values(const void *left,const void *right) {
    const Value *a=left,*b=right;return strcmp(a->string,b->string);
}
static const char *error_categories[] = {
    "network_operation_unavailable",
    "runtime_error",
    "type_error",
    "value_error",
    "index_error",
    "io_error",
    "parse_error",
    "import_error",
    "regex_error",
    "glob_error",
    "argument_error",
    "permission_error",
    "auth_error",
    "secret_error",
    "oauth_error",
    "crypto_error",
    "crypto_authentication_error",
    "mail_error",
    "mail_address_error",
    "mail_attachment_error",
    "mail_provider_error",
    "mail_connection_error",
    "mail_authentication_error",
    "mail_send_error",
    "yaml_error",
    "yaml_parse_error",
    "yaml_encode_error",
    "yaml_type_error",
    "yaml_limit_error",
    "xml_error",
    "xml_parse_error",
    "xml_model_error",
    "xml_security_error",
    "xml_limit_error",
    "xml_path_error",
    "xml_escape_error",
    "cookie_error",
    "db_connection_error",
    "db_auth_error",
    "db_query_error",
    "db_constraint_error",
    "db_timeout_error",
    "db_transaction_error",
    "db_driver_error",
    "board_error",
    "pin_error",
    "peripheral_mapping_error",
    "embedded_backend_error",
    "network_error",
    "network_dns_error",
    "network_interface_error",
    "network_connection_error",
    "network_timeout_error",
    "network_limit_error",
    "network_closed_error",
    "network_protocol_error",
    "network_address_error",
    "network_service_error",
    "dhcp_server_error",
    "dns_server_error",
    "wifi_access_point_error",
 };
static int error_category_name(const char *name) {
    for(size_t i=0;i<sizeof(error_categories)/sizeof(*error_categories);i++)if(!strcmp(name,error_categories[i]))return 1;
    return 0;
}
typedef struct { const char *name; size_t minimum,maximum; const char *named; } HostSignature;
static const HostSignature host_signatures[] = {
    {"regex_match",2,2,"dot_all|ignore_case|multiline"},
    {"regex_search",2,2,"dot_all|ignore_case|multiline"},
    {"regex_find",2,2,"dot_all|ignore_case|multiline"},
    {"regex_find_all",2,2,"dot_all|ignore_case|multiline"},
    {"regex_replace",3,3,"dot_all|ignore_case|multiline"},
    {"regex_split",2,2,"dot_all|ignore_case|multiline"},
    {"regex_text",1,1,""},
    {"regex_start",1,1,""},
    {"regex_end",1,1,""},
    {"regex_group",2,2,""},
    {"http_profile",1,1,"accept|accept_encoding|language|user_agent"},
    {"http_profile_headers",1,1,""},
    {"http_request",1,1,"auth|body|cookie_jar|cookies|encoding|headers|max_bytes|max_redirects|method|profile|redirect|timeout"},
    {"http_get",1,1,"auth|cookie_jar|cookies|encoding|headers|max_bytes|max_redirects|profile|redirect|timeout"},
    {"secret_get",1,1,""},
    {"secret_from_environment",1,1,""},
    {"basic_auth",2,2,""},
    {"bearer_auth",1,1,""},
    {"api_key_auth",2,2,"location"},
    {"jwt_sign",2,2,"algorithm"},
    {"jwt_verify",2,2,"algorithm"},
    {"password_hash",1,1,""},
    {"password_verify",2,2,""},
    {"oauth_client_credentials",3,3,"scope"},
    {"derive_key_from_password",2,2,""},
    {"encrypt_authenticated",2,2,""},
    {"decrypt_authenticated",2,2,""},
    {"encrypt_with_password",2,2,""},
    {"decrypt_with_password",2,2,""},
    {"mail_address",1,1,"display_name"},
    {"mail_create_message",0,0,""},
    {"mail_set_sender",2,2,""},
    {"mail_add_recipient",2,2,""},
    {"mail_add_cc_recipient",2,2,""},
    {"mail_add_bcc_recipient",2,2,""},
    {"mail_set_subject",2,2,""},
    {"mail_set_text_body",2,2,""},
    {"mail_set_html_body",2,2,""},
    {"mail_add_attachment",2,2,"content_type"},
    {"mail_add_attachment_bytes",4,4,""},
    {"mail_add_inline_attachment",3,3,"content_type"},
    {"mail_add_inline_attachment_bytes",5,5,""},
    {"mail_create_sender",0,0,"host|password|port|provider|region|security|timeout|username"},
    {"mail_send_message",2,2,""},
    {"yaml_to_object",1,1,""},
    {"object_to_yaml",1,1,"indent|sort_keys"},
    {"yaml_file_to_object",1,1,""},
    {"object_to_yaml_file",2,2,"indent|sort_keys"},
    {"yaml_to_objects",1,1,""},
    {"objects_to_yaml",1,1,"indent|sort_keys"},
    {"yaml_file_to_objects",1,1,""},
    {"objects_to_yaml_file",2,2,"indent|sort_keys"},
    {"yaml_validate",1,1,""},
    {"yaml_validate_file",1,1,""},
    {"xml_to_object",1,1,""},
    {"object_to_xml",1,1,"declaration|indent"},
    {"xml_file_to_object",1,1,""},
    {"object_to_xml_file",2,2,"declaration|indent"},
    {"xml_document_parse",1,1,""},
    {"xml_document_read",1,1,""},
    {"xml_document_to_text",1,1,"declaration|indent"},
    {"xml_document_write",2,2,"declaration|indent"},
    {"xml_create_element",1,1,"namespace_uri"},
    {"xml_root",1,1,""},
    {"xml_element_name",1,1,""},
    {"xml_element_text",1,1,""},
    {"xml_set_element_text",2,2,""},
    {"xml_get_attribute",2,2,"namespace_uri"},
    {"xml_set_attribute",3,3,"namespace_uri"},
    {"xml_remove_attribute",2,2,"namespace_uri"},
    {"xml_children",1,1,""},
    {"xml_child",2,2,""},
    {"xml_add_child",2,2,""},
    {"xml_remove_child",2,2,""},
    {"xml_find",2,2,""},
    {"xml_find_all",2,2,""},
    {"xml_namespace_uri",1,1,""},
    {"xml_namespace_prefix",1,1,""},
    {"cookie_jar",0,0,""},
    {"cookie_get",2,2,""},
    {"cookie_set",3,3,"domain|http_only|path|same_site|secure"},
    {"cookie_remove",2,2,""},
    {"cookie_clear",1,1,""},
    {"cookie_all",1,1,""},
    {"cookie_save_secure",2,2,"key|password"},
    {"cookie_load_secure",1,1,"key|password"},
    {"http_host",0,0,"host|port"},
    {"http_static",0,0,"directory|url"},
    {"board_select",1,1,""},
    {"board_name",0,0,""},
    {"board_family",0,0,""},
    {"board_cpu",0,0,""},
    {"board_voltage",0,0,""},
    {"board_has",1,1,""},
    {"board_pins",0,0,""},
    {"board_features",0,0,""},
    {"pin_exists",1,1,""},
    {"pin_has",2,2,""},
    {"pin_capabilities",1,1,""},
    {"gpio_set_mode",2,2,""},
    {"gpio_write",2,2,""},
    {"gpio_read",1,1,""},
    {"analog_read",1,1,""},
    {"analog_write",2,2,""},
    {"pwm_write",2,2,""},
    {"i2c_open",0,1,"scl|sda"},
    {"spi_open",0,1,"chip_select|clock|miso|mosi"},
    {"uart_open",0,1,"rx|tx"},
    {"delay_milliseconds",1,1,""},
    {"i2c_probe",2,2,""},
    {"uart_write",2,2,""},
    {"uart_read_line",1,1,""},
    {"ip_address",1,1,""},
    {"ip_address_version",1,1,""},
    {"ip_address_is_private",1,1,""},
    {"ip_address_is_loopback",1,1,""},
    {"ip_address_is_global",1,1,""},
    {"network_interfaces",0,0,""},
    {"network_interface",1,1,""},
    {"network_status",1,1,""},
    {"network_is_connected",1,1,""},
    {"network_ip_address",1,1,""},
    {"network_ip_addresses",1,1,""},
    {"network_gateway",1,1,""},
    {"network_subnet_mask",1,1,""},
    {"network_dns_servers",1,1,""},
    {"network_mac_address",1,1,""},
    {"network_hostname",0,0,""},
    {"network_set_preferred_interfaces",1,1,""},
    {"network_preferred_interface",0,0,""},
    {"network_use_dhcp",1,1,""},
    {"network_set_static_address",5,5,""},
    {"network_use_link_local",1,1,""},
    {"network_refresh_address",1,1,""},
    {"network_release_address",1,1,""},
    {"network_enable_link_local_fallback",1,1,""},
    {"network_disable_link_local_fallback",1,1,""},
    {"network_address_mode",1,1,""},
    {"network_dhcp_status",1,1,""},
    {"network_dhcp_lease",1,1,""},
    {"network_wait_until_addressed",2,2,""},
    {"ethernet_open",0,1,""},
    {"ethernet_status",1,1,""},
    {"wifi_open",0,1,""},
    {"wifi_scan",1,1,""},
    {"wifi_status",1,1,""},
    {"wifi_is_connected",1,1,""},
    {"wifi_ssid",1,1,""},
    {"wifi_bssid",1,1,""},
    {"wifi_channel",1,1,""},
    {"wifi_signal_strength",1,1,""},
    {"wifi_wait_until_connected",2,2,""},
    {"dns_resolve",1,1,""},
    {"dns_reverse_lookup",1,1,""},
    {"tcp_connect",2,2,"timeout"},
    {"tcp_send",2,2,""},
    {"tcp_receive",1,2,"timeout"},
    {"tcp_close",1,1,""},
    {"udp_open",0,0,"local_address|local_port|timeout"},
    {"udp_send",4,4,""},
    {"udp_receive",1,2,"timeout"},
    {"udp_close",1,1,""},
    {"wifi_start_access_point",1,1,"channel|password|ssid"},
    {"wifi_stop_access_point",1,1,""},
    {"wifi_access_point_status",1,1,""},
    {"dhcp_server_start",1,1,"dns_servers|gateway|lease_time|pool_end|pool_start|prefix|reservations|server_address"},
    {"dhcp_server_stop",1,1,""},
    {"dhcp_server_status",1,1,""},
    {"dhcp_server_leases",1,1,""},
    {"dns_server_start",1,1,"catch_all|records|server_address"},
    {"dns_server_stop",1,1,""},
    {"dns_server_status",1,1,""},
 };
static const HostSignature *host_signature(const char *name) {
    for(size_t i=0;i<sizeof(host_signatures)/sizeof(*host_signatures);i++)
        if(!strcmp(name,host_signatures[i].name))return &host_signatures[i];
    return NULL;
}
static const HostSignature native_http_signatures[] = {
    {"request_method",0,0,""},{"request_path",0,0,""},{"request_header",1,1,""},
    {"request_param",1,1,""},{"request_query",1,1,""},{"request_body",0,0,"encoding"},
    {"request_cookie",1,1,""},{"return_http",0,0,"body|content_type|headers|status"},
    {"redirect_http",1,1,"status"},{"http_set_cookie",2,2,"http_only|path|same_site|secure"}
};
static const HostSignature *native_http_signature(const char *name) {
    for(size_t i=0;i<sizeof(native_http_signatures)/sizeof(*native_http_signatures);i++)
        if(!strcmp(name,native_http_signatures[i].name))return &native_http_signatures[i];
    return NULL;
}
static const HostSignature *any_host_signature(const char *name) {
    const HostSignature *signature=native_http_signature(name);return signature?signature:host_signature(name);
}
static int host_named_argument(const HostSignature *signature,const char *name) {
    if(!signature||!name||!*name)return 0;size_t length=strlen(name);const char *at=signature->named;
    while(*at){const char *end=strchr(at,'|');size_t part=end?(size_t)(end-at):strlen(at);
        if(part==length&&!memcmp(at,name,length))return 1;if(!end)break;at=end+1;}
    return 0;
}
static int builtin_name(const char *name) {
    if(any_host_signature(name)||error_category_name(name)) return 1;
    const char *names[] = {"len", "length", "is_empty", "size", "first", "last",
                           "list_append", "append", "list_insert", "list_remove_horizontal", "list_remove_vertical", "contains", "abs", "sum",
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
                           "base64_decode", "bytes_to_base64", "base64_to_bytes", "pow",
                           "min", "max", "average", "range", "count", "unique",
                           "remove_at", "flatten", "absolute", "minimum", "maximum",
                           "truncate", "clamp", "sign", "square_root", "cube_root",
                           "power", "hypotenuse", "exponential", "exponential_base2",
                           "natural_log", "log_base2", "log_base10", "log_one_plus",
                           "arc_sin", "arc_cos", "arc_tan", "arc_tan2", "sinh", "cosh",
                           "tanh", "arc_sinh", "arc_cosh", "arc_tanh", "to_radians",
                           "to_degrees", "is_finite", "is_infinite", "is_nan",
                           "is_close", "is_integer_value", "greatest_common_divisor",
                           "least_common_multiple", "factorial", "median", "variance",
                           "sample_variance", "standard_deviation", "sample_standard_deviation",
                           "percentile", "moving_average", "number_to_binary", "number_to_octal",
                           "number_to_hexadecimal", "binary_to_number", "octal_to_number",
                           "hexadecimal_to_number", "number_to_base", "base_to_number",
                           "object_get", "object_has", "object_set", "object_remove",
                           "object_keys", "object_values", "list_remove", "remove",
                           "sort", "sort_descending", "sort_ignore_case",
                           "sort_ignore_case_descending", "sort_natural",
                           "sort_natural_descending", "sort_natural_ignore_case",
                           "sort_natural_ignore_case_descending", "sort_by", "sort_by_descending",
                           "map", "filter", "reduce", "split", "join", "replace", "char_at",
                           "compare", "compare_ignore_case", "count_occurrences", "repeat",
                           "pad_left", "pad_right", "clip_utf8", "find_all", "substring",
                           "substring_before", "substring_after", "exp", "log", "log2", "log10",
                           "is_number", "is_boolean", "is_string", "is_list", "is_object",
                           "is_bytes", "is_datetime", "is_duration", "is_secret", "format",
                           "random_seed", "random_number", "random_int", "random_float",
                           "random_bool", "random_pick", "random_shuffle", "random_sample",
                           "constant_time_equal", "input", "secure_random_bytes",
                           "secure_random_int", "secure_random_number", "secure_random_string",
                           "number_range", "type_of", "command_args", "script_path",
                           "arg_exists", "arg_value", "glob", "sha256_hash", "sha512_hash", "sha3_256_hash", "sha3_512_hash",
                           "sha256_hmac", "hmac_sha256", "sha512_hmac",
                           "env_get", "env_exists", "env_set", "env_remove", "unix_time",
                           "xml_escape_text", "xml_escape_attribute", "xml_unescape",
                           "db_connect", "db_close", "db_query", "db_query_one", "db_scalar", "db_execute",
                           "db_begin", "db_commit", "db_rollback", "db_tables", "db_columns", "db_indexes",
                           "db_primary_key", "db_server_info", "db_version",
                           "exec", "exec_checked", "shell_exec", "command_exists",
                           "duration", "duration_milliseconds", "timezone", "local_datetime",
                           "datetime", "datetime_parse", "datetime_from_local", "datetime_in_timezone",
                           "datetime_from_unix", "datetime_from_unix_milliseconds", "datetime_from_unix_seconds",
                           "unix_milliseconds_from_datetime", "unix_seconds_from_datetime", "datetime_offset",
                           "datetime_timezone", "datetime_year", "datetime_month", "datetime_day", "datetime_hour",
                           "datetime_minute", "datetime_second", "datetime_millisecond", "datetime_weekday",
                           "datetime_now", "datetime_valid", "datetime_format"};
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
static int buffer_display(TextBuffer *buffer, Value value) {
    char number[64];
    if(value.kind==V_NUMBER&&value.big_integer)return buffer_append(buffer,value.big_integer,strlen(value.big_integer));
    if (value.kind == V_NUMBER) { format_number(number, sizeof(number), value); return buffer_append(buffer, number, strlen(number)); }
    if (value.kind == V_STRING) return buffer_append(buffer, value.string, value.string_length);
    if (value.kind == V_TIMEZONE || value.kind == V_LOCAL_DATETIME || value.kind == V_DATETIME)
        return buffer_append(buffer, value.string, value.string_length);
    if (value.kind == V_BOOL) return buffer_append(buffer, value.boolean ? "true" : "false", value.boolean ? 4 : 5);
    if (value.kind == V_DURATION) {
        format_duration_value(number, sizeof(number), value.integer);
        return buffer_append(buffer, number, strlen(number));
    }
    if (value.kind == V_BYTES) {
        if (!buffer_append(buffer, "0x", 2)) return 0;
        static const char hex[] = "0123456789abcdef";
        for (size_t i = 0; i < value.string_length; i++) {
            char pair[2] = {hex[(unsigned char)value.string[i] >> 4], hex[(unsigned char)value.string[i] & 15]};
            if (!buffer_append(buffer, pair, 2)) return 0;
        }
        return 1;
    }
    if (value.kind == V_LIST) {
        if (!buffer_append(buffer, "[", 1)) return 0;
        for (size_t i = 0; i < value.count; i++) {
            if (i && !buffer_append(buffer, ", ", 2)) return 0;
            if (!buffer_display(buffer, value.items[i])) return 0;
        }
        return buffer_append(buffer, "]", 1);
    }
    return buffer_append(buffer, "EMPTY", 5);
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
        if(value.big_integer)return buffer_append(buffer,value.big_integer,strlen(value.big_integer));
        if (!isfinite(value.number)) return 0;
        char number[64]; format_number(number, sizeof(number), value);
        return buffer_append(buffer, number, strlen(number));
    }
    if (value.kind == V_STRING) return json_string(buffer, value.string, value.string_length);
    if (value.kind == V_DURATION) {
        char number[32]; snprintf(number,sizeof(number),"%lld",(long long)value.integer);
        return buffer_append(buffer,number,strlen(number));
    }
    if (value.kind == V_TIMEZONE || value.kind == V_LOCAL_DATETIME || value.kind == V_DATETIME)
        return json_string(buffer,value.string,value.string_length);
    if (value.kind == V_BYTES) {
        static const char hex[]="0123456789ABCDEF";
        if(!buffer_append(buffer,"{\"$bytes\":\"",11))return 0;
        for(size_t i=0;i<value.string_length;i++){char pair[2]={hex[(unsigned char)value.string[i]>>4],hex[(unsigned char)value.string[i]&15]};if(!buffer_append(buffer,pair,2))return 0;}
        return buffer_append(buffer,"\"}",2);
    }
    if (value.kind == V_LIST) {
        if (!buffer_char(buffer, '[')) return 0;
        for (size_t i = 0; i < value.count; i++) {
            if (i && !buffer_char(buffer, ',')) return 0;
            if (!json_value(buffer, value.items[i], depth + 1)) return 0;
        }
        return buffer_char(buffer, ']');
    }
    if (value.kind == V_OBJECT || value.kind == V_EXEC_RESULT || value.kind == V_REGEX) {
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
static int json_decode_bytes_tag(Value *value) {
    if(value->kind!=V_OBJECT||value->count!=1||strcmp(value->keys[0],"$bytes")||
       value->items[0].kind!=V_STRING||value->items[0].string_length%2)return 1;
    Value *text=&value->items[0];size_t length=text->string_length/2;char *bytes=malloc(length+1);
    if(!bytes)return 0;
    for(size_t i=0;i<length;i++){char high=text->string[i*2],low=text->string[i*2+1];
        if(!isxdigit((unsigned char)high)||!isxdigit((unsigned char)low)){free(bytes);return 1;}
        bytes[i]=(char)((hex_value(high)<<4)|hex_value(low));}
    bytes[length]=0;free(text->string);free(value->keys[0]);free(value->keys);free(value->items);
    *value=empty_value();value->kind=V_BYTES;value->string=bytes;value->string_length=length;return 1;
}
static int normalize_decoded_list(Value *list) {
    char *element_type=NULL;
    for(size_t i=0;i<list->count;i++){
        char *current=value_type_text(list->items[i]);
        if(current){
            if(element_type&&strcmp(element_type,current)){free(current);free(element_type);return 0;}
            if(!element_type)element_type=copy_text(current);
        }
        free(current);
    }
    if(element_type){
        for(size_t i=0;i<list->count;i++){
            if(list->items[i].kind==V_EMPTY&&!list->items[i].retained_type)
                list->items[i].retained_type=copy_text(element_type);
            else if(list->items[i].kind==V_LIST&&list->items[i].retained_type&&
                    !strcmp(list->items[i].retained_type,"__JSON_UNKNOWN_LIST__")){
                free(list->items[i].retained_type);list->items[i].retained_type=NULL;
                retain_value_type(&list->items[i],element_type);
            }
        }
    }else if(list->count)list->retained_type=copy_text("__JSON_UNKNOWN_LIST__");
    free(element_type);return 1;
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
            if (cursor->error) {
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
            if (c == (object ? '}' : ']')) {
                if(object&&!json_decode_bytes_tag(&result)){free_value(result);cursor->error=1;return empty_value();}
                if(!object&&!normalize_decoded_list(&result)){free_value(result);cursor->error=1;return empty_value();}
                return result;
            }
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
    if(floating)result=floating_value(strtod(number,NULL));
    else result=integer_text_value(number);
    free(number);
    if (!result.big_integer&&!isfinite(result.number)) cursor->error = 1;
    return result;
}
static int compare_doubles(const void *left, const void *right) {
    double a = *(const double *)left, b = *(const double *)right;
    return (a > b) - (a < b);
}
static int ordered_compare(Value left, Value right, int ignore_case) {
    if (left.kind == V_NUMBER) return number_compare(left,right);
    if (left.kind == V_DURATION || left.kind == V_DATETIME)
        return (left.integer > right.integer) - (left.integer < right.integer);
    if (left.kind != V_STRING && left.kind != V_LOCAL_DATETIME) return 0;
    size_t length = left.string_length < right.string_length ? left.string_length : right.string_length;
    for (size_t i = 0; i < length; i++) {
        unsigned char a = (unsigned char)left.string[i], b = (unsigned char)right.string[i];
        if (ignore_case) { a = (unsigned char)tolower(a); b = (unsigned char)tolower(b); }
        if (a != b) return (a > b) - (a < b);
    }
    return (left.string_length > right.string_length) - (left.string_length < right.string_length);
}
static int natural_string_compare(Value left, Value right, int ignore_case) {
    size_t a = 0, b = 0;
    while (a < left.string_length && b < right.string_length) {
        unsigned char ca = (unsigned char)left.string[a], cb = (unsigned char)right.string[b];
        if (isdigit(ca) && isdigit(cb)) {
            size_t a_end = a, b_end = b, a_sig = a, b_sig = b;
            while (a_end < left.string_length && isdigit((unsigned char)left.string[a_end])) a_end++;
            while (b_end < right.string_length && isdigit((unsigned char)right.string[b_end])) b_end++;
            while (a_sig + 1 < a_end && left.string[a_sig] == '0') a_sig++;
            while (b_sig + 1 < b_end && right.string[b_sig] == '0') b_sig++;
            size_t a_digits = a_end - a_sig, b_digits = b_end - b_sig;
            if (a_digits != b_digits) return (a_digits > b_digits) - (a_digits < b_digits);
            int compared = memcmp(left.string + a_sig, right.string + b_sig, a_digits);
            if (compared) return compared > 0 ? 1 : -1;
            a = a_end; b = b_end; continue;
        }
        if (ignore_case) { ca = (unsigned char)tolower(ca); cb = (unsigned char)tolower(cb); }
        if (ca != cb) return (ca > cb) - (ca < cb);
        a++; b++;
    }
    return (a < left.string_length) - (b < right.string_length);
}
static long long integer_gcd(long long a, long long b) {
    if (a < 0) a = -a;
    if (b < 0) b = -b;
    while (b) { long long remainder = a % b; a = b; b = remainder; }
    return a;
}
static int integer_argument(Value value, long long *out) {
    if(value.kind==V_NUMBER&&value.exact_integer&&!value.big_integer){*out=(long long)value.integer;return 1;}
    if (value.kind != V_NUMBER || !isfinite(value.number) || floor(value.number) != value.number ||
        value.number < -9007199254740991.0 || value.number > 9007199254740991.0) return 0;
    *out = (long long)value.number;
    return 1;
}
static Value number_to_base_value(Runtime *r, Value number, int base) {
    if(number.kind==V_NUMBER&&number.exact_integer&&number.big_integer&&base>=2&&base<=36){static const char digits[]="0123456789abcdefghijklmnopqrstuvwxyz";const char *source=big_abs(number.big_integer);char divisor[3];snprintf(divisor,sizeof(divisor),"%d",base);size_t capacity=strlen(source)*4+3,count=0;char *reversed=malloc(capacity),*current=copy_text(source);if(!reversed||!current){free(reversed);free(current);fault(r,"out of memory");return empty_value();}
        do{char *quotient=NULL,*remainder=NULL;if(!big_divmod_abs(current,divisor,&quotient,&remainder)){free(current);free(reversed);fault(r,"math range error");return empty_value();}int digit=atoi(remainder);free(remainder);free(current);current=quotient;reversed[count++]=digits[digit];}while(strcmp(current,"0"));free(current);size_t sign=*number.big_integer=='-',length=count+(size_t)sign;char *output=malloc(length+1);if(!output){free(reversed);fault(r,"out of memory");return empty_value();}size_t at=0;if(sign)output[at++]='-';while(count)output[at++]=reversed[--count];output[at]=0;free(reversed);Value result=string_value(output);free(output);return result;}
    long long value;
    if (!integer_argument(number, &value) || base < 2 || base > 36) {
        fault(r, "integer and base 2..36 required"); return empty_value();
    }
    static const char digits[] = "0123456789abcdefghijklmnopqrstuvwxyz";
    char reversed[70], output[72]; size_t count = 0, at = 0;
    unsigned long long magnitude = value < 0 ? (unsigned long long)(-(value + 1)) + 1 : (unsigned long long)value;
    do { reversed[count++] = digits[magnitude % (unsigned)base]; magnitude /= (unsigned)base; } while (magnitude);
    if (value < 0) output[at++] = '-';
    while (count) output[at++] = reversed[--count];
    output[at] = 0;
    return string_value(output);
}
static Value base_to_number_value(Runtime *r, Value text, int base) {
    if (text.kind != V_STRING || base < 2 || base > 36 || !text.string_length) {
        fault(r, "string and base 2..36 required"); return empty_value();
    }
    size_t at = 0; int negative = 0, previous_underscore = 0, saw_digit = 0;
    if (text.string[at] == '-') { negative = 1; at++; }
    char *value=copy_text("0");if(!value){fault(r,"out of memory");return empty_value();}
    for (; at < text.string_length; at++) {
        unsigned char c = (unsigned char)text.string[at];
        if (c == '_') {
            if (!saw_digit || previous_underscore || at + 1 == text.string_length) { free(value);fault(r, "invalid base integer"); return empty_value(); }
            previous_underscore = 1; continue;
        }
        int digit = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'z' ? c - 'a' + 10 :
                    c >= 'A' && c <= 'Z' ? c - 'A' + 10 : -1;
        if (digit < 0 || digit >= base) {free(value);fault(r, "invalid base integer"); return empty_value();}
        char factor[3],decimal[3];snprintf(factor,sizeof(factor),"%d",base);snprintf(decimal,sizeof(decimal),"%d",digit);char *scaled=big_multiply(value,factor);free(value);value=scaled?big_add(scaled,decimal):NULL;free(scaled);if(!value){fault(r,"out of memory");return empty_value();}saw_digit = 1; previous_underscore = 0;
    }
    if (!saw_digit) {free(value);fault(r, "invalid base integer"); return empty_value(); }
    if(negative){char *signed_value=big_signed(value,1);value=signed_value;}
    return big_result(value);
}
static uint32_t random_next(Runtime *r) {
    uint64_t old = r->random_state;
    r->random_state = old * UINT64_C(6364136223846793005) + UINT64_C(109);
    uint32_t shifted = (uint32_t)((((old >> 18) ^ old) >> 27) & UINT32_MAX);
    unsigned rotation = (unsigned)(old >> 59);
    return (shifted >> rotation) | (shifted << ((-(int)rotation) & 31));
}
static void random_seed_runtime(Runtime *r, uint64_t seed) {
    r->random_state = 0; random_next(r); r->random_state += seed; random_next(r);
}
static uint64_t random_bits(Runtime *r, unsigned count) {
    uint64_t result = 0; unsigned produced = 0;
    while (produced < count) {
        unsigned take = count - produced < 32 ? count - produced : 32;
        result = (result << take) | (random_next(r) >> (32 - take)); produced += take;
    }
    return result;
}
static uint64_t random_below(Runtime *r, uint64_t upper) {
    unsigned bits = 0; uint64_t maximum = upper - 1;
    while (maximum) { bits++; maximum >>= 1; }
    for (;;) { uint64_t candidate = random_bits(r, bits); if (candidate < upper) return candidate; }
}
static double random_number_value(Runtime *r) {
    return ((double)(random_next(r) >> 5) * 67108864.0 + (double)(random_next(r) >> 6)) / 9007199254740992.0;
}
static int secure_fill(unsigned char *data, size_t length) {
#ifdef _WIN32
    size_t at = 0;
    while (at < length) {
        unsigned int value;
        if (rand_s(&value)) return 0;
        size_t take = length - at < sizeof(value) ? length - at : sizeof(value);
        memcpy(data + at, &value, take); at += take;
    }
    return 1;
#else
    FILE *source = fopen("/dev/urandom", "rb");
    if (!source) return 0;
    int ok = fread(data, 1, length, source) == length;
    fclose(source); return ok;
#endif
}
static int secure_below(uint64_t upper, uint64_t *result) {
    if (!upper) return 0;
    uint64_t limit = UINT64_MAX - (UINT64_MAX % upper);
    uint64_t value;
    do { if (!secure_fill((unsigned char *)&value, sizeof(value))) return 0; } while (value >= limit);
    *result = value % upper; return 1;
}
static char *random_big_below(Runtime *r,const char *upper,int secure) {
    size_t length=strlen(upper);char *candidate=malloc(length+1);if(!candidate)return NULL;
    for(;;){
        for(size_t i=0;i<length;i++){uint64_t digit;if(secure?!secure_below(10,&digit):(digit=random_below(r,10),0)){free(candidate);return NULL;}candidate[i]=(char)('0'+digit);}candidate[length]=0;
        if(big_abs_compare(candidate,upper)<0)return candidate;
    }
}
static uint32_t rotate_right32(uint32_t value, unsigned shift) {
    return (value >> shift) | (value << (32 - shift));
}
static int sha256_digest(const unsigned char *data, size_t length, unsigned char output[32]) {
    static const uint32_t constants[64] = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    if (length > (SIZE_MAX - 72)) return 0;
    size_t padded = ((length + 9 + 63) / 64) * 64;
    unsigned char *message = calloc(padded, 1);
    if (!message) return 0;
    memcpy(message, data, length); message[length] = 0x80;
    uint64_t bits = (uint64_t)length * 8;
    for (size_t i = 0; i < 8; i++) message[padded - 1 - i] = (unsigned char)(bits >> (i * 8));
    uint32_t hash[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    for (size_t block = 0; block < padded; block += 64) {
        uint32_t words[64];
        for (size_t i = 0; i < 16; i++) words[i] = ((uint32_t)message[block+i*4] << 24) |
            ((uint32_t)message[block+i*4+1] << 16) | ((uint32_t)message[block+i*4+2] << 8) | message[block+i*4+3];
        for (size_t i = 16; i < 64; i++) {
            uint32_t s0 = rotate_right32(words[i-15],7) ^ rotate_right32(words[i-15],18) ^ (words[i-15] >> 3);
            uint32_t s1 = rotate_right32(words[i-2],17) ^ rotate_right32(words[i-2],19) ^ (words[i-2] >> 10);
            words[i] = words[i-16] + s0 + words[i-7] + s1;
        }
        uint32_t a=hash[0],b=hash[1],c=hash[2],d=hash[3],e=hash[4],f=hash[5],g=hash[6],h=hash[7];
        for (size_t i = 0; i < 64; i++) {
            uint32_t s1=rotate_right32(e,6)^rotate_right32(e,11)^rotate_right32(e,25), ch=(e&f)^((~e)&g);
            uint32_t first=h+s1+ch+constants[i]+words[i];
            uint32_t s0=rotate_right32(a,2)^rotate_right32(a,13)^rotate_right32(a,22), majority=(a&b)^(a&c)^(b&c);
            uint32_t second=s0+majority; h=g; g=f; f=e; e=d+first; d=c; c=b; b=a; a=first+second;
        }
        hash[0]+=a;hash[1]+=b;hash[2]+=c;hash[3]+=d;hash[4]+=e;hash[5]+=f;hash[6]+=g;hash[7]+=h;
    }
    free(message);
    for (size_t i = 0; i < 8; i++) for (size_t j = 0; j < 4; j++) output[i*4+j]=(unsigned char)(hash[i]>>(24-j*8));
    return 1;
}
static int sha256_hmac_digest(const unsigned char *key, size_t key_length, const unsigned char *data,
                              size_t data_length, unsigned char output[32]) {
    unsigned char normalized[64] = {0}, inner_hash[32];
    if (key_length > 64) { if (!sha256_digest(key, key_length, normalized)) return 0; }
    else memcpy(normalized, key, key_length);
    unsigned char *inner = malloc(64 + data_length), outer[96];
    if (!inner) return 0;
    for (size_t i = 0; i < 64; i++) { inner[i] = normalized[i] ^ 0x36; outer[i] = normalized[i] ^ 0x5c; }
    memcpy(inner + 64, data, data_length);
    int ok = sha256_digest(inner, 64 + data_length, inner_hash);
    free(inner); if (!ok) return 0;
    memcpy(outer + 64, inner_hash, 32); return sha256_digest(outer, sizeof(outer), output);
}
static uint64_t rotate_right64(uint64_t value, unsigned bits) { return (value >> bits) | (value << (64 - bits)); }
static int sha512_digest(const unsigned char *data, size_t length, unsigned char output[64]) {
    static const uint64_t k[80] = {
        UINT64_C(0x428a2f98d728ae22),UINT64_C(0x7137449123ef65cd),UINT64_C(0xb5c0fbcfec4d3b2f),UINT64_C(0xe9b5dba58189dbbc),UINT64_C(0x3956c25bf348b538),UINT64_C(0x59f111f1b605d019),UINT64_C(0x923f82a4af194f9b),UINT64_C(0xab1c5ed5da6d8118),
        UINT64_C(0xd807aa98a3030242),UINT64_C(0x12835b0145706fbe),UINT64_C(0x243185be4ee4b28c),UINT64_C(0x550c7dc3d5ffb4e2),UINT64_C(0x72be5d74f27b896f),UINT64_C(0x80deb1fe3b1696b1),UINT64_C(0x9bdc06a725c71235),UINT64_C(0xc19bf174cf692694),
        UINT64_C(0xe49b69c19ef14ad2),UINT64_C(0xefbe4786384f25e3),UINT64_C(0x0fc19dc68b8cd5b5),UINT64_C(0x240ca1cc77ac9c65),UINT64_C(0x2de92c6f592b0275),UINT64_C(0x4a7484aa6ea6e483),UINT64_C(0x5cb0a9dcbd41fbd4),UINT64_C(0x76f988da831153b5),
        UINT64_C(0x983e5152ee66dfab),UINT64_C(0xa831c66d2db43210),UINT64_C(0xb00327c898fb213f),UINT64_C(0xbf597fc7beef0ee4),UINT64_C(0xc6e00bf33da88fc2),UINT64_C(0xd5a79147930aa725),UINT64_C(0x06ca6351e003826f),UINT64_C(0x142929670a0e6e70),
        UINT64_C(0x27b70a8546d22ffc),UINT64_C(0x2e1b21385c26c926),UINT64_C(0x4d2c6dfc5ac42aed),UINT64_C(0x53380d139d95b3df),UINT64_C(0x650a73548baf63de),UINT64_C(0x766a0abb3c77b2a8),UINT64_C(0x81c2c92e47edaee6),UINT64_C(0x92722c851482353b),
        UINT64_C(0xa2bfe8a14cf10364),UINT64_C(0xa81a664bbc423001),UINT64_C(0xc24b8b70d0f89791),UINT64_C(0xc76c51a30654be30),UINT64_C(0xd192e819d6ef5218),UINT64_C(0xd69906245565a910),UINT64_C(0xf40e35855771202a),UINT64_C(0x106aa07032bbd1b8),
        UINT64_C(0x19a4c116b8d2d0c8),UINT64_C(0x1e376c085141ab53),UINT64_C(0x2748774cdf8eeb99),UINT64_C(0x34b0bcb5e19b48a8),UINT64_C(0x391c0cb3c5c95a63),UINT64_C(0x4ed8aa4ae3418acb),UINT64_C(0x5b9cca4f7763e373),UINT64_C(0x682e6ff3d6b2b8a3),
        UINT64_C(0x748f82ee5defb2fc),UINT64_C(0x78a5636f43172f60),UINT64_C(0x84c87814a1f0ab72),UINT64_C(0x8cc702081a6439ec),UINT64_C(0x90befffa23631e28),UINT64_C(0xa4506cebde82bde9),UINT64_C(0xbef9a3f7b2c67915),UINT64_C(0xc67178f2e372532b),
        UINT64_C(0xca273eceea26619c),UINT64_C(0xd186b8c721c0c207),UINT64_C(0xeada7dd6cde0eb1e),UINT64_C(0xf57d4f7fee6ed178),UINT64_C(0x06f067aa72176fba),UINT64_C(0x0a637dc5a2c898a6),UINT64_C(0x113f9804bef90dae),UINT64_C(0x1b710b35131c471b),
        UINT64_C(0x28db77f523047d84),UINT64_C(0x32caab7b40c72493),UINT64_C(0x3c9ebe0a15c9bebc),UINT64_C(0x431d67c49c100d4c),UINT64_C(0x4cc5d4becb3e42b6),UINT64_C(0x597f299cfc657e2a),UINT64_C(0x5fcb6fab3ad6faec),UINT64_C(0x6c44198c4a475817)};
    if (length > SIZE_MAX - 145) return 0;
    size_t padded = ((length + 144) / 128) * 128; unsigned char *message = calloc(padded, 1); if (!message) return 0;
    memcpy(message, data, length); message[length] = 0x80; uint64_t low=(uint64_t)length<<3, high=(uint64_t)length>>61;
    for(size_t i=0;i<8;i++){message[padded-1-i]=(unsigned char)(low>>(8*i));message[padded-9-i]=(unsigned char)(high>>(8*i));}
    uint64_t hash[8]={UINT64_C(0x6a09e667f3bcc908),UINT64_C(0xbb67ae8584caa73b),UINT64_C(0x3c6ef372fe94f82b),UINT64_C(0xa54ff53a5f1d36f1),UINT64_C(0x510e527fade682d1),UINT64_C(0x9b05688c2b3e6c1f),UINT64_C(0x1f83d9abfb41bd6b),UINT64_C(0x5be0cd19137e2179)};
    for(size_t block=0;block<padded;block+=128){uint64_t w[80];for(size_t i=0;i<16;i++){w[i]=0;for(size_t j=0;j<8;j++)w[i]=(w[i]<<8)|message[block+i*8+j];}for(size_t i=16;i<80;i++){uint64_t s0=rotate_right64(w[i-15],1)^rotate_right64(w[i-15],8)^(w[i-15]>>7),s1=rotate_right64(w[i-2],19)^rotate_right64(w[i-2],61)^(w[i-2]>>6);w[i]=w[i-16]+s0+w[i-7]+s1;}uint64_t a=hash[0],b=hash[1],c=hash[2],d=hash[3],e=hash[4],f=hash[5],g=hash[6],h=hash[7];for(size_t i=0;i<80;i++){uint64_t s1=rotate_right64(e,14)^rotate_right64(e,18)^rotate_right64(e,41),ch=(e&f)^((~e)&g),t1=h+s1+ch+k[i]+w[i],s0=rotate_right64(a,28)^rotate_right64(a,34)^rotate_right64(a,39),maj=(a&b)^(a&c)^(b&c),t2=s0+maj;h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;}hash[0]+=a;hash[1]+=b;hash[2]+=c;hash[3]+=d;hash[4]+=e;hash[5]+=f;hash[6]+=g;hash[7]+=h;}
    free(message);for(size_t i=0;i<8;i++)for(size_t j=0;j<8;j++)output[i*8+j]=(unsigned char)(hash[i]>>(56-j*8));return 1;
}
static int sha512_hmac_digest(const unsigned char *key,size_t key_length,const unsigned char *data,size_t data_length,unsigned char output[64]) {
    unsigned char normalized[128]={0},inner_hash[64];if(key_length>128){if(!sha512_digest(key,key_length,normalized))return 0;}else memcpy(normalized,key,key_length);if(data_length>SIZE_MAX-128)return 0;unsigned char *inner=malloc(128+data_length),outer[192];if(!inner)return 0;for(size_t i=0;i<128;i++){inner[i]=normalized[i]^0x36;outer[i]=normalized[i]^0x5c;}memcpy(inner+128,data,data_length);int ok=sha512_digest(inner,128+data_length,inner_hash);free(inner);if(!ok)return 0;memcpy(outer+128,inner_hash,64);return sha512_digest(outer,sizeof(outer),output);
}
static uint64_t rotate_left64(uint64_t value,unsigned bits){return bits?(value<<bits)|(value>>(64-bits)):value;}
static void keccak_f1600(uint64_t state[25]) {
    static const uint64_t rc[24]={UINT64_C(0x1),UINT64_C(0x8082),UINT64_C(0x800000000000808a),UINT64_C(0x8000000080008000),UINT64_C(0x808b),UINT64_C(0x80000001),UINT64_C(0x8000000080008081),UINT64_C(0x8000000000008009),UINT64_C(0x8a),UINT64_C(0x88),UINT64_C(0x80008009),UINT64_C(0x8000000a),UINT64_C(0x8000808b),UINT64_C(0x800000000000008b),UINT64_C(0x8000000000008089),UINT64_C(0x8000000000008003),UINT64_C(0x8000000000008002),UINT64_C(0x8000000000000080),UINT64_C(0x800a),UINT64_C(0x800000008000000a),UINT64_C(0x8000000080008081),UINT64_C(0x8000000000008080),UINT64_C(0x80000001),UINT64_C(0x8000000080008008)};static const unsigned rho[25]={0,1,62,28,27,36,44,6,55,20,3,10,43,25,39,41,45,15,21,8,18,2,61,56,14};
    for(size_t round=0;round<24;round++){uint64_t c[5],d[5],b[25];for(size_t x=0;x<5;x++)c[x]=state[x]^state[x+5]^state[x+10]^state[x+15]^state[x+20];for(size_t x=0;x<5;x++)d[x]=c[(x+4)%5]^rotate_left64(c[(x+1)%5],1);for(size_t y=0;y<5;y++)for(size_t x=0;x<5;x++)state[x+5*y]^=d[x];for(size_t y=0;y<5;y++)for(size_t x=0;x<5;x++)b[y+5*((2*x+3*y)%5)]=rotate_left64(state[x+5*y],rho[x+5*y]);for(size_t y=0;y<5;y++)for(size_t x=0;x<5;x++)state[x+5*y]=b[x+5*y]^((~b[(x+1)%5+5*y])&b[(x+2)%5+5*y]);state[0]^=rc[round];}
}
static void sha3_digest(const unsigned char *data,size_t length,unsigned char *output,size_t output_length) {
    size_t rate=200-2*output_length,at=0;uint64_t state[25]={0};while(length>=rate){for(size_t i=0;i<rate;i++)state[i/8]^=(uint64_t)data[i]<<(8*(i%8));keccak_f1600(state);data+=rate;length-=rate;}for(size_t i=0;i<length;i++)state[i/8]^=(uint64_t)data[i]<<(8*(i%8));state[length/8]^=(uint64_t)0x06<<(8*(length%8));state[(rate-1)/8]^=(uint64_t)0x80<<(8*((rate-1)%8));keccak_f1600(state);while(at<output_length){size_t take=output_length-at<rate?output_length-at:rate;for(size_t i=0;i<take;i++)output[at+i]=(unsigned char)(state[i/8]>>(8*(i%8)));at+=take;if(at<output_length)keccak_f1600(state);}
}
static size_t positional_count(const Expr *e) {
    size_t count=0; while(count<e->argc && !e->arg_names[count]) count++; return count;
}
static Value *named_argument(const Expr *e,Value *args,const char *name) {
    for(size_t i=0;i<e->argc;i++) if(e->arg_names[i] && !strcmp(e->arg_names[i],name)) return &args[i];
    return NULL;
}
static const char *bytes_encoding(Runtime *r,const Expr *e,Value *args) {
    Value *encoding=named_argument(e,args,"encoding");
    if(!encoding)return "utf-8";
    if(encoding->kind!=V_STRING){fault(r,"encoding must be a string");return NULL;}
    if(strcmp(encoding->string,"utf-8")&&strcmp(encoding->string,"utf-16le")&&
       strcmp(encoding->string,"utf-16be")&&strcmp(encoding->string,"ascii")){
        fault(r,"unsupported encoding");return NULL;
    }
    return encoding->string;
}
static int utf8_next_codepoint(const char *text,size_t length,size_t *offset,unsigned *codepoint) {
    if(*offset>=length)return 0;
    unsigned char first=(unsigned char)text[*offset];
    size_t width=first<0x80?1:first<0xE0?2:first<0xF0?3:4;
    unsigned value=first&(width==1?0x7F:width==2?0x1F:width==3?0x0F:0x07);
    for(size_t index=1;index<width;index++)
        value=(value<<6)|((unsigned char)text[*offset+index]&0x3F);
    *offset+=width;*codepoint=value;return 1;
}
static int append_utf16_unit(TextBuffer *buffer,unsigned unit,int little_endian) {
    char bytes[2];
    bytes[little_endian?0:1]=(char)(unit&0xFF);
    bytes[little_endian?1:0]=(char)(unit>>8);
    return buffer_append(buffer,bytes,sizeof(bytes));
}
static Value encode_bytes(Runtime *r,Value text,const char *encoding) {
    TextBuffer buffer={0};
    if(!valid_utf8_bytes(text.string,text.string_length))fault(r,"bytes encode error");
    else if(!strcmp(encoding,"utf-8")){
        if(!buffer_append(&buffer,text.string,text.string_length))fault(r,"out of memory");
    }else{
        size_t offset=0;int little_endian=!strcmp(encoding,"utf-16le");
        while(offset<text.string_length&&!r->error){
            unsigned codepoint=0;utf8_next_codepoint(text.string,text.string_length,&offset,&codepoint);
            if(!strcmp(encoding,"ascii")){
                if(codepoint>0x7F)fault(r,"bytes encode error");
                else{char byte=(char)codepoint;if(!buffer_append(&buffer,&byte,1))fault(r,"out of memory");}
            }else if(codepoint<0x10000){
                if(!append_utf16_unit(&buffer,codepoint,little_endian))fault(r,"out of memory");
            }else{
                codepoint-=0x10000;
                if(!append_utf16_unit(&buffer,0xD800+(codepoint>>10),little_endian)||
                   !append_utf16_unit(&buffer,0xDC00+(codepoint&0x3FF),little_endian))fault(r,"out of memory");
            }
        }
    }
    Value result=empty_value();
    if(!r->error){result=string_bytes(buffer.data?buffer.data:"",buffer.length);result.kind=V_BYTES;
        if(!result.string)fault(r,"out of memory");}
    free(buffer.data);return result;
}
static Value decode_bytes(Runtime *r,Value bytes,const char *encoding) {
    TextBuffer buffer={0};
    if(!strcmp(encoding,"utf-8")){
        if(!valid_utf8_bytes(bytes.string,bytes.string_length))fault(r,"bytes decode error");
        else if(!buffer_append(&buffer,bytes.string,bytes.string_length))fault(r,"out of memory");
    }else if(!strcmp(encoding,"ascii")){
        for(size_t index=0;index<bytes.string_length&&!r->error;index++){
            unsigned char byte=(unsigned char)bytes.string[index];
            if(byte>0x7F)fault(r,"bytes decode error");
            else if(!buffer_append(&buffer,(const char *)&bytes.string[index],1))fault(r,"out of memory");
        }
    }else{
        int little_endian=!strcmp(encoding,"utf-16le");size_t offset=0;
        if(bytes.string_length%2)fault(r,"bytes decode error");
        while(offset<bytes.string_length&&!r->error){
            unsigned first=(unsigned char)bytes.string[offset++];
            unsigned second=(unsigned char)bytes.string[offset++];
            unsigned unit=little_endian?first|(second<<8):(first<<8)|second;
            unsigned codepoint=unit;
            if(unit>=0xD800&&unit<=0xDBFF){
                if(offset+1>=bytes.string_length){fault(r,"bytes decode error");break;}
                first=(unsigned char)bytes.string[offset++];second=(unsigned char)bytes.string[offset++];
                unsigned low=little_endian?first|(second<<8):(first<<8)|second;
                if(low<0xDC00||low>0xDFFF){fault(r,"bytes decode error");break;}
                codepoint=0x10000+((unit-0xD800)<<10)+(low-0xDC00);
            }else if(unit>=0xDC00&&unit<=0xDFFF){fault(r,"bytes decode error");break;}
            char encoded[4];size_t width=append_utf8(encoded,codepoint);
            if(!buffer_append(&buffer,encoded,width))fault(r,"out of memory");
        }
    }
    Value result=empty_value();
    if(!r->error){result=string_bytes(buffer.data?buffer.data:"",buffer.length);result.kind=V_STRING;
        if(!result.string)fault(r,"out of memory");}
    free(buffer.data);return result;
}
static void database_release(const separan_database_adapter *adapter,char *value) {
    if(!value)return;if(adapter->release_string)adapter->release_string(adapter->context,value);else free(value);
}
static const char *database_status_message(int status) {
    static const char *messages[]={"database operation error","database driver error","database connection error",
        "database authentication error","database query error","database constraint error","database timeout error",
        "database transaction error"};
    return status>=1&&status<=7?messages[status]:messages[0];
}
static const char *process_status_message(int status) {
    static const char *messages[]={"process operation error","process permission error","invalid command",
        "command not found or denied","invalid process cwd","command spawn error","process limit error",
        "process operation error","command error","command timeout error"};
    return status>=1&&status<=9?messages[status]:messages[0];
}
static void process_release(const separan_process_adapter *adapter,char *value) {
    if(!value)return;if(adapter->release_string)adapter->release_string(adapter->context,value);else free(value);
}
static int database_json(Value value,char **json) {
    TextBuffer buffer={0}; if(!json_value(&buffer,value,0)){free(buffer.data);return 0;}
    if(!buffer_append(&buffer,"",1)){free(buffer.data);return 0;} buffer.length--; *json=buffer.data; return 1;
}
static Value adapter_parse_json(Runtime *r,const char *text,const char *missing,const char *invalid) {
    if(!text){fault(r,missing);return empty_value();}
    JsonCursor cursor={text,strlen(text),0,0};Value result=json_parse_value(&cursor,0);json_space(&cursor);
    if(cursor.error||cursor.at!=cursor.length){free_value(result);fault(r,invalid);return empty_value();}
    return result;
}
static void host_release(const separan_host_adapter *adapter,char *value) {
    if(!value)return;if(adapter->release_string)adapter->release_string(adapter->context,value);else free(value);
}
static Value *object_field(Value *object,const char *name) {
    if(object->kind!=V_OBJECT&&object->kind!=V_EXEC_RESULT&&object->kind!=V_ERROR&&object->kind!=V_REGEX)return NULL;
    for(size_t i=0;i<object->count;i++)if(!strcmp(object->keys[i],name))return &object->items[i];
    return NULL;
}
static int normalize_regex_match(Value *value) {
    if(value->kind==V_EMPTY){if(!value->retained_type)value->retained_type=copy_text("regex_match_result");return value->retained_type!=NULL;}
    if(value->kind!=V_OBJECT||value->count!=4)return 0;
    Value *text=object_field(value,"text"),*start=object_field(value,"start"),*end=object_field(value,"end"),*groups=object_field(value,"groups");
    if(!text||text->kind!=V_STRING||!start||start->kind!=V_NUMBER||!start->exact_integer||start->big_integer||start->integer<0||
       !end||end->kind!=V_NUMBER||!end->exact_integer||end->big_integer||end->integer<start->integer||!groups||groups->kind!=V_LIST)return 0;
    for(size_t i=0;i<groups->count;i++)if(groups->items[i].kind!=V_STRING&&groups->items[i].kind!=V_EMPTY)return 0;
    value->kind=V_REGEX;return 1;
}
static int set_retained_type(Value *value,const char *type) {
    free(value->retained_type);value->retained_type=copy_text(type);return value->retained_type!=NULL;
}
static int exact_object_shape(Value *value,const char *const *fields,size_t count) {
    if(value->kind!=V_OBJECT||value->count!=count)return 0;
    for(size_t i=0;i<count;i++)if(!object_field(value,fields[i]))return 0;
    return 1;
}
static int opaque_host_handle(Value *value,const char *type) {
    static const char *fields[]={"kind"};
    if(!exact_object_shape(value,fields,1))return 0;
    Value *kind=object_field(value,"kind");
    return kind&&kind->kind==V_STRING&&!strcmp(kind->string,type)&&set_retained_type(value,type);
}
static int string_list(Value *value) {
    if(value->kind!=V_LIST)return 0;
    for(size_t i=0;i<value->count;i++)if(value->items[i].kind!=V_STRING)return 0;
    return 1;
}
static int exact_integer(Value *value) {
    return value&&value->kind==V_NUMBER&&value->exact_integer&&!value->big_integer;
}
static int normalize_pin(Value *value) {
    static const char *fields[]={"name","physical_pin","backend_pin","voltage","capabilities"};
    if(!exact_object_shape(value,fields,5))return 0;Value *name=object_field(value,"name"),*physical=object_field(value,"physical_pin"),*backend=object_field(value,"backend_pin"),*voltage=object_field(value,"voltage"),*capabilities=object_field(value,"capabilities");
    return name&&name->kind==V_STRING&&physical&&(physical->kind==V_STRING||exact_integer(physical))&&backend&&backend->kind==V_STRING&&voltage&&voltage->kind==V_NUMBER&&capabilities&&string_list(capabilities)&&set_retained_type(value,"pin");
}
static int normalize_network_ip(Value *value) {
    return (value->kind==V_EMPTY&&set_retained_type(value,"ip_address"))||
           (value->kind==V_STRING&&set_retained_type(value,"ip_address"));
}
static int normalize_network_ip_list(Value *value) {
    if(value->kind!=V_LIST)return 0;
    for(size_t i=0;i<value->count;i++)if(!normalize_network_ip(&value->items[i])||value->items[i].kind==V_EMPTY)return 0;
    return 1;
}
static int normalize_network_interface(Value *value) {
    static const char *fields[]={"name","index","description","kind","connected","addresses","ip_address","gateway","subnet_mask","dns_servers","mac_address","ssid","bssid","channel","signal_strength","address_mode","dhcp_status","dhcp_lease","link_local_fallback"};
    if(!exact_object_shape(value,fields,19))return 0;
    Value *name=object_field(value,"name"),*index=object_field(value,"index"),*description=object_field(value,"description"),*kind=object_field(value,"kind"),*connected=object_field(value,"connected"),*addresses=object_field(value,"addresses"),*address=object_field(value,"ip_address"),*gateway=object_field(value,"gateway"),*mask=object_field(value,"subnet_mask"),*dns=object_field(value,"dns_servers"),*mac=object_field(value,"mac_address"),*ssid=object_field(value,"ssid"),*bssid=object_field(value,"bssid"),*channel=object_field(value,"channel"),*signal=object_field(value,"signal_strength"),*mode=object_field(value,"address_mode"),*dhcp=object_field(value,"dhcp_status"),*lease=object_field(value,"dhcp_lease"),*fallback=object_field(value,"link_local_fallback");
    return name&&name->kind==V_STRING&&exact_integer(index)&&description&&description->kind==V_STRING&&kind&&kind->kind==V_STRING&&connected&&connected->kind==V_BOOL&&addresses&&normalize_network_ip_list(addresses)&&address&&normalize_network_ip(address)&&gateway&&normalize_network_ip(gateway)&&mask&&normalize_network_ip(mask)&&dns&&normalize_network_ip_list(dns)&&mac&&(mac->kind==V_STRING||mac->kind==V_EMPTY)&&ssid&&(ssid->kind==V_STRING||ssid->kind==V_EMPTY)&&bssid&&(bssid->kind==V_STRING||bssid->kind==V_EMPTY)&&channel&&(channel->kind==V_NUMBER||channel->kind==V_EMPTY)&&signal&&(signal->kind==V_NUMBER||signal->kind==V_EMPTY)&&mode&&mode->kind==V_STRING&&dhcp&&dhcp->kind==V_STRING&&lease&&(lease->kind==V_OBJECT||lease->kind==V_EMPTY)&&fallback&&fallback->kind==V_BOOL&&set_retained_type(value,"network_interface");
}
static int normalize_host_result(const char *name,Value *value) {
    if(!strcmp(name,"regex_match")||!strcmp(name,"regex_search"))return value->kind==V_BOOL;
    if(!strcmp(name,"regex_find"))return normalize_regex_match(value);
    if(!strcmp(name,"regex_find_all")){if(value->kind!=V_LIST)return 0;for(size_t i=0;i<value->count;i++)if(!normalize_regex_match(&value->items[i])||value->items[i].kind==V_EMPTY)return 0;return 1;}
    if(!strcmp(name,"regex_replace"))return value->kind==V_STRING;
    if(!strcmp(name,"regex_split")){if(value->kind!=V_LIST)return 0;for(size_t i=0;i<value->count;i++)if(value->items[i].kind!=V_STRING)return 0;return 1;}
    if(!strcmp(name,"regex_text"))return value->kind==V_STRING;
    if(!strcmp(name,"regex_start")||!strcmp(name,"regex_end"))return value->kind==V_NUMBER&&value->exact_integer&&!value->big_integer&&value->integer>=0;
    if(!strcmp(name,"regex_group"))return value->kind==V_STRING||value->kind==V_EMPTY;
    if(!strcmp(name,"http_get")||!strcmp(name,"http_request")){
        if(value->kind!=V_OBJECT||value->count!=8)return 0;Value *status=object_field(value,"status"),*url=object_field(value,"url"),*headers=object_field(value,"headers"),*bytes=object_field(value,"bytes"),*text=object_field(value,"text"),*encoding=object_field(value,"encoding"),*redirects=object_field(value,"redirects"),*cookies=object_field(value,"cookies");
        if(!status||status->kind!=V_NUMBER||!status->exact_integer||status->big_integer||status->integer<100||status->integer>599||!url||url->kind!=V_STRING||!headers||headers->kind!=V_OBJECT||!bytes||bytes->kind!=V_BYTES||!text||(text->kind!=V_STRING&&text->kind!=V_EMPTY)||!encoding||(encoding->kind!=V_STRING&&encoding->kind!=V_EMPTY)||!redirects||redirects->kind!=V_LIST||!cookies||cookies->kind!=V_OBJECT)return 0;
        for(size_t i=0;i<redirects->count;i++)if(redirects->items[i].kind!=V_STRING)return 0;
        value->retained_type=copy_text("http_response");return value->retained_type!=NULL;
    }
    if(!strcmp(name,"mail_address")){
        if(value->kind!=V_OBJECT||value->count!=2)return 0;Value *address=object_field(value,"address"),*display=object_field(value,"display_name");
        if(!address||address->kind!=V_STRING||!display||(display->kind!=V_STRING&&display->kind!=V_EMPTY))return 0;
        value->retained_type=copy_text("mail_address");return value->retained_type!=NULL;
    }
    if(!strcmp(name,"mail_send_message")){
        if(value->kind!=V_OBJECT||value->count!=3)return 0;Value *provider=object_field(value,"provider"),*message=object_field(value,"message_id"),*accepted=object_field(value,"accepted_recipients");
        if(!provider||provider->kind!=V_STRING||!message||message->kind!=V_STRING||!accepted||accepted->kind!=V_NUMBER||!accepted->exact_integer||accepted->big_integer||accepted->integer<0)return 0;
        return set_retained_type(value,"mail_send_result");
    }
    if(!strcmp(name,"secret_get")||!strcmp(name,"secret_from_environment"))return value->kind==V_BYTES&&set_retained_type(value,"secret");
    if(!strcmp(name,"basic_auth")||!strcmp(name,"bearer_auth")||!strcmp(name,"api_key_auth")){
        static const char *fields[]={"kind","name","value","location"};
        if(!exact_object_shape(value,fields,4))return 0;Value *kind=object_field(value,"kind"),*key=object_field(value,"name"),*secret=object_field(value,"value"),*location=object_field(value,"location");
        return kind&&kind->kind==V_STRING&&key&&key->kind==V_STRING&&secret&&secret->kind==V_BYTES&&
               set_retained_type(secret,"secret")&&location&&location->kind==V_STRING&&set_retained_type(value,"http_auth");
    }
    if(!strcmp(name,"oauth_client_credentials")){
        static const char *fields[]={"access_token","token_type","expires_in","scope"};
        if(!exact_object_shape(value,fields,4))return 0;Value *token=object_field(value,"access_token"),*kind=object_field(value,"token_type"),*expires=object_field(value,"expires_in"),*scope=object_field(value,"scope");
        if(!token||token->kind!=V_BYTES||!set_retained_type(token,"secret")||!kind||kind->kind!=V_STRING||!expires||
           (expires->kind!=V_EMPTY&&!(expires->kind==V_NUMBER&&expires->exact_integer&&!expires->big_integer&&expires->integer>=0))||
           !scope||(scope->kind!=V_EMPTY&&scope->kind!=V_STRING))return 0;
        if(expires->kind==V_EMPTY&&!set_retained_type(expires,"number"))return 0;
        if(scope->kind==V_EMPTY&&!set_retained_type(scope,"string"))return 0;
        return set_retained_type(value,"oauth_token");
    }
    if(!strcmp(name,"http_profile")){
        static const char *fields[]={"name","user_agent","accept","language","accept_encoding"};
        if(!exact_object_shape(value,fields,5))return 0;
        for(size_t i=0;i<5;i++){Value *field=object_field(value,fields[i]);if(!field||field->kind!=V_STRING)return 0;}
        return set_retained_type(value,"http_profile");
    }
    if(!strcmp(name,"cookie_jar")||!strcmp(name,"cookie_load_secure"))return opaque_host_handle(value,"cookie_jar");
    if(!strcmp(name,"cookie_get"))return value->kind==V_BYTES?set_retained_type(value,"secret"):
        value->kind==V_EMPTY&&set_retained_type(value,"secret");
    if(!strcmp(name,"mail_create_message"))return opaque_host_handle(value,"mail_message");
    if(!strcmp(name,"mail_create_sender"))return opaque_host_handle(value,"mail_sender");
    if(!strcmp(name,"xml_document_parse")||!strcmp(name,"xml_document_read"))return opaque_host_handle(value,"xml_document");
    if(!strcmp(name,"xml_create_element")||!strcmp(name,"xml_root"))return opaque_host_handle(value,"xml_element");
    if(!strcmp(name,"xml_child")||!strcmp(name,"xml_find"))return value->kind==V_EMPTY?
        set_retained_type(value,"xml_element"):opaque_host_handle(value,"xml_element");
    if(!strcmp(name,"xml_children")||!strcmp(name,"xml_find_all")){
        if(value->kind!=V_LIST)return 0;for(size_t i=0;i<value->count;i++)if(!opaque_host_handle(&value->items[i],"xml_element"))return 0;return 1;
    }
    if(!strcmp(name,"board_select")){
        static const char *fields[]={"id","name","family","cpu","voltage","flash_bytes","ram_bytes","features"};
        if(!exact_object_shape(value,fields,8))return 0;
        for(size_t i=0;i<4;i++){Value *field=object_field(value,fields[i]);if(!field||field->kind!=V_STRING)return 0;}
        Value *voltage=object_field(value,"voltage"),*flash=object_field(value,"flash_bytes"),*ram=object_field(value,"ram_bytes"),*features=object_field(value,"features");
        return voltage&&voltage->kind==V_NUMBER&&exact_integer(flash)&&exact_integer(ram)&&features&&string_list(features)&&set_retained_type(value,"board");
    }
    if(!strcmp(name,"i2c_open")||!strcmp(name,"spi_open")||!strcmp(name,"uart_open")){
        static const char *fields[]={"board","kind","index","pins"};
        if(!exact_object_shape(value,fields,4))return 0;Value *board=object_field(value,"board"),*kind=object_field(value,"kind"),*index=object_field(value,"index"),*pins=object_field(value,"pins");
        if(!board||board->kind!=V_STRING||!kind||kind->kind!=V_STRING||!exact_integer(index)||!pins||pins->kind!=V_LIST)return 0;
        for(size_t i=0;i<pins->count;i++)if(!normalize_pin(&pins->items[i]))return 0;
        return set_retained_type(value,"embedded_bus");
    }
    if(!strcmp(name,"ip_address"))return value->kind==V_STRING&&set_retained_type(value,"ip_address");
    if(!strcmp(name,"network_interface")||!strcmp(name,"ethernet_open")||!strcmp(name,"wifi_open"))return normalize_network_interface(value);
    if(!strcmp(name,"network_preferred_interface"))return value->kind==V_EMPTY?
        set_retained_type(value,"network_interface"):normalize_network_interface(value);
    if(!strcmp(name,"network_interfaces")){
        if(value->kind!=V_LIST)return 0;for(size_t i=0;i<value->count;i++)if(!normalize_network_interface(&value->items[i]))return 0;return 1;
    }
    if(!strcmp(name,"network_ip_address")||!strcmp(name,"network_gateway")||!strcmp(name,"network_subnet_mask"))
        return normalize_network_ip(value);
    if(!strcmp(name,"network_ip_addresses")||!strcmp(name,"network_dns_servers")||!strcmp(name,"dns_resolve"))
        return normalize_network_ip_list(value);
    if(!strcmp(name,"tcp_connect"))return opaque_host_handle(value,"tcp_connection");
    if(!strcmp(name,"udp_open"))return opaque_host_handle(value,"udp_socket");
    if(!strcmp(name,"dhcp_server_start"))return opaque_host_handle(value,"dhcp_server");
    if(!strcmp(name,"dns_server_start"))return opaque_host_handle(value,"dns_server");
    return 1;
}
static int fixed_object_member(const Value *value,const char *name) {
    if(!value->retained_type)return 1;
    if(!strcmp(value->retained_type,"http_response")){
        static const char *members[]={"status","url","headers","bytes","text","encoding","redirects","cookies"};
        for(size_t i=0;i<sizeof(members)/sizeof(*members);i++)if(!strcmp(name,members[i]))return 1;
        return 0;
    }
    if(!strcmp(value->retained_type,"mail_address"))return !strcmp(name,"address")||!strcmp(name,"display_name");
    if(!strcmp(value->retained_type,"mail_send_result"))return !strcmp(name,"provider")||!strcmp(name,"message_id")||!strcmp(name,"accepted_recipients");
    if(!strcmp(value->retained_type,"http_auth"))return !strcmp(name,"kind")||!strcmp(name,"name")||!strcmp(name,"value")||!strcmp(name,"location");
    if(!strcmp(value->retained_type,"oauth_token"))return !strcmp(name,"access_token")||!strcmp(name,"token_type")||!strcmp(name,"expires_in")||!strcmp(name,"scope");
    if(!strcmp(value->retained_type,"http_profile"))return !strcmp(name,"name")||!strcmp(name,"user_agent")||!strcmp(name,"accept")||!strcmp(name,"language")||!strcmp(name,"accept_encoding");
    if(!strcmp(value->retained_type,"board")){static const char *members[]={"id","name","family","cpu","voltage","flash_bytes","ram_bytes","features"};for(size_t i=0;i<8;i++)if(!strcmp(name,members[i]))return 1;return 0;}
    if(!strcmp(value->retained_type,"pin")){static const char *members[]={"name","physical_pin","backend_pin","voltage","capabilities"};for(size_t i=0;i<5;i++)if(!strcmp(name,members[i]))return 1;return 0;}
    if(!strcmp(value->retained_type,"embedded_bus"))return !strcmp(name,"board")||!strcmp(name,"kind")||!strcmp(name,"index")||!strcmp(name,"pins");
    if(!strcmp(value->retained_type,"network_interface")){static const char *members[]={"name","index","description","kind","connected","addresses","ip_address","gateway","subnet_mask","dns_servers","mac_address","ssid","bssid","channel","signal_strength","address_mode","dhcp_status","dhcp_lease","link_local_fallback"};for(size_t i=0;i<19;i++)if(!strcmp(name,members[i]))return 1;return 0;}
    if(!strcmp(value->retained_type,"cookie_jar")||!strcmp(value->retained_type,"mail_message")||!strcmp(value->retained_type,"mail_sender")||!strcmp(value->retained_type,"xml_document")||!strcmp(value->retained_type,"xml_element")||!strcmp(value->retained_type,"tcp_connection")||!strcmp(value->retained_type,"udp_socket")||!strcmp(value->retained_type,"dhcp_server")||!strcmp(value->retained_type,"dns_server"))return 0;
    return 1;
}
static void module_retain(ModuleResource *module){module->references++;}
static void module_release(ModuleResource *module){
    if(!module||--module->references)return;
    free_value(module->runtime.thrown);free_value(module->runtime.returned);free_frame(&module->runtime.global);
    free_body(module->runtime.program);separan_tokens_free(&module->runtime.tokens);separan_files_free(&module->runtime.files);free(module->path);free(module);
}
static Value error_value(const char *category,Value message) {
    Value value=empty_value();value.kind=V_ERROR;value.count=2;
    value.keys=calloc(2,sizeof(*value.keys));value.items=calloc(2,sizeof(*value.items));
    if(!value.keys||!value.items){free(value.keys);free(value.items);return empty_value();}
    value.keys[0]=copy_text("category");value.keys[1]=copy_text("message");
    if(!value.keys[0]||!value.keys[1]){free_value(value);return empty_value();}
    value.items[0]=string_value(category);value.items[1]=clone_value(message);return value;
}
static int string_has_nul(Value value) {
    return value.kind==V_STRING&&memchr(value.string,0,value.string_length)!=NULL;
}
static int process_decode_hex(Value *value) {
    if(value->kind!=V_STRING||value->string_length%2)return 0;
    size_t length=value->string_length/2;char *bytes=malloc(length?length:1);if(!bytes)return 0;
    for(size_t i=0;i<length;i++){
        char high=value->string[i*2],low=value->string[i*2+1];
        if(!isxdigit((unsigned char)high)||!isxdigit((unsigned char)low)){free(bytes);return 0;}
        bytes[i]=(char)((hex_value(high)<<4)|hex_value(low));
    }
    free(value->string);value->string=bytes;value->string_length=length;value->kind=V_BYTES;return 1;
}
static int normalize_exec_result(Value *value) {
    if(value->kind!=V_OBJECT)return 0;
    Value *exit_code=object_field(value,"exit_code"),*stdout_text=object_field(value,"stdout"),
          *stderr_text=object_field(value,"stderr"),*stdout_bytes=object_field(value,"stdout_bytes"),
          *stderr_bytes=object_field(value,"stderr_bytes"),*timed_out=object_field(value,"timed_out"),
          *duration=object_field(value,"duration"),*command=object_field(value,"command");
    if(!exit_code||exit_code->kind!=V_NUMBER||exit_code->floating||
       !stdout_text||(stdout_text->kind!=V_STRING&&stdout_text->kind!=V_EMPTY)||
       !stderr_text||(stderr_text->kind!=V_STRING&&stderr_text->kind!=V_EMPTY)||
       !stdout_bytes||!stderr_bytes||!timed_out||timed_out->kind!=V_BOOL||
       !duration||duration->kind!=V_NUMBER||duration->floating||duration->number<0||
       !command||command->kind!=V_STRING)return 0;
    if(!process_decode_hex(stdout_bytes)||!process_decode_hex(stderr_bytes))return 0;
    duration->kind=V_DURATION;duration->integer=(int64_t)duration->number;duration->number=0;
    value->kind=V_EXEC_RESULT;return 1;
}
static int accepts_named_argument(const char *function,const char *argument) {
    const HostSignature *host=any_host_signature(function);if(host)return host_named_argument(host,argument);
    if(!strcmp(function,"exec")||!strcmp(function,"exec_checked")||!strcmp(function,"shell_exec")) {
        const char *names[]={"cwd","timeout","env","inherit_env","input","encoding","max_stdout_bytes","max_stderr_bytes"};
        for(size_t i=0;i<sizeof(names)/sizeof(*names);i++)if(!strcmp(argument,names[i]))return 1;
    }
    if((!strcmp(function,"bytes_from_string") || !strcmp(function,"string_from_bytes")) && !strcmp(argument,"encoding")) return 1;
    if((!strcmp(function,"env_get") || !strcmp(function,"arg_value")) && !strcmp(argument,"default")) return 1;
    if(!strcmp(function,"datetime") && !strcmp(argument,"timezone")) return 1;
    if(!strcmp(function,"db_connect")) {
        const char *names[]={"driver","host","port","database","user","password","timeout","charset","ssl","mode"};
        for(size_t i=0;i<sizeof(names)/sizeof(*names);i++)if(!strcmp(argument,names[i]))return 1;
    }
    if((!strcmp(function,"db_query")||!strcmp(function,"db_query_one")||!strcmp(function,"db_scalar")||!strcmp(function,"db_execute"))&&!strcmp(argument,"timeout"))return 1;
    return 0;
}
static Value *shape_target(Runtime *r,Frame *frame,Expr *expression) {
    if(expression->kind==1){Binding *binding=lookup(frame,expression->text);if(!binding){fault(r,"undefined variable");return NULL;}
        if(binding->constant){fault(r,"constant cannot be reassigned");return NULL;}return &binding->value;}
    if(expression->kind==6){Value *parent=shape_target(r,frame,expression->left);if(!parent||r->error)return NULL;
        Value index=evaluate(r,frame,expression->right);if(index.kind!=V_NUMBER||index.floating||index.number<0||
            index.number>=(double)parent->count||parent->kind!=V_LIST){free_value(index);fault(r,"list index out of range or invalid");return NULL;}
        size_t at=(size_t)index.number;free_value(index);return &parent->items[at];}
    fault(r,"list shape target required");return NULL;
}
static int shape_integer(Runtime *r,Value value,int positive) {
    if(value.kind!=V_NUMBER||value.floating||value.number<(positive?1:0)||value.number>(double)SIZE_MAX){fault(r,"list shape integer required");return 0;}
    return 1;
}
static Value *object_field(Value *object,const char *name);
static Value object_value(size_t count) {
    Value value=empty_value();value.kind=V_OBJECT;value.count=count;
    value.keys=calloc(count?count:1,sizeof(*value.keys));value.items=calloc(count?count:1,sizeof(*value.items));return value;
}
static Value http_default_response(int status,const char *body) {
    Value response=object_value(4);if(!response.keys||!response.items){free_value(response);return empty_value();}
    response.keys[0]=copy_text("status");response.items[0]=number_value(status);
    response.keys[1]=copy_text("headers");response.items[1]=object_value(status==204?0:1);
    if(status!=204){response.items[1].keys[0]=copy_text("Content-Type");response.items[1].items[0]=string_value("text/plain; charset=utf-8");}
    response.keys[2]=copy_text("body");response.items[2]=string_value(body?body:"");
    response.keys[3]=copy_text("cookies");response.items[3].kind=V_LIST;return response;
}
static Value *object_field_ci(Value *object,const char *name) {
    if(object->kind!=V_OBJECT)return NULL;
    for(size_t i=0;i<object->count;i++){const char *a=object->keys[i],*b=name;while(*a&&*b&&tolower((unsigned char)*a)==tolower((unsigned char)*b)){a++;b++;}if(!*a&&!*b)return &object->items[i];}
    return NULL;
}
static int native_http_builtin(Runtime *r,const char *name,const Expr *e,Value *args,Value *result) {
    if(strcmp(name,"request_method")&&strcmp(name,"request_path")&&strcmp(name,"request_header")&&
       strcmp(name,"request_param")&&strcmp(name,"request_query")&&strcmp(name,"request_body")&&
       strcmp(name,"request_cookie")&&strcmp(name,"return_http")&&strcmp(name,"redirect_http")&&strcmp(name,"http_set_cookie"))return 0;
    if(!r->http_active){if(r->host&&r->host->call)return 0;fault(r,"no HTTP request context");return 1;}
    Value *method=object_field(&r->http_request,"method"),*path=object_field(&r->http_request,"path");
    if(!strcmp(name,"request_method")){*result=method?clone_value(*method):empty_value();return 1;}
    if(!strcmp(name,"request_path")){*result=path?clone_value(*path):empty_value();return 1;}
    if(!strcmp(name,"request_body")){Value *body=object_field(&r->http_request,"body"),*encoding=named_argument(e,args,"encoding");const char *codec=encoding&&encoding->kind==V_STRING?encoding->string:"utf-8";
        if(encoding&&encoding->kind!=V_STRING){fault(r,"HTTP request decode error");return 1;}
        if(!body){*result=string_value("");return 1;}if(body->kind==V_STRING){*result=clone_value(*body);return 1;}
        if(body->kind!=V_BYTES||(strcmp(codec,"utf-8")&&strcmp(codec,"ascii"))){fault(r,"HTTP request decode error");return 1;}
        if((!strcmp(codec,"utf-8")&&!valid_utf8_bytes(body->string,body->string_length))||(!strcmp(codec,"ascii")&&memchr(body->string,0x80,0))){fault(r,"HTTP request decode error");return 1;}
        if(!strcmp(codec,"ascii"))for(size_t i=0;i<body->string_length;i++)if((unsigned char)body->string[i]>=0x80){fault(r,"HTTP request decode error");return 1;}
        *result=string_bytes(body->string,body->string_length);return 1;}
    if(!strcmp(name,"request_header")||!strcmp(name,"request_param")||!strcmp(name,"request_query")||!strcmp(name,"request_cookie")){
        if(args[0].kind!=V_STRING){fault(r,"incompatible operand types");return 1;}Value *found=NULL;
        if(!strcmp(name,"request_param"))found=object_field(&r->http_params,args[0].string);
        else if(!strcmp(name,"request_query")){Value *query=object_field(&r->http_request,"query");found=query?object_field(query,args[0].string):NULL;if(found&&found->kind==V_LIST)found=found->count?&found->items[0]:NULL;}
        else {Value *headers=object_field(&r->http_request,"headers");
            if(!strcmp(name,"request_header"))found=headers?object_field_ci(headers,args[0].string):NULL;
            else {Value *cookie=headers?object_field_ci(headers,"cookie"):NULL;if(cookie&&cookie->kind==V_STRING){size_t n=args[0].string_length;
                const char *p=cookie->string;while(*p){while(*p==' '||*p==';')p++;if(!strncmp(p,args[0].string,n)&&p[n]=='='){const char *v=p+n+1,*end=strchr(v,';');*result=string_bytes(v,end?(size_t)(end-v):strlen(v));return 1;}p=strchr(p,';');if(!p)break;}}}}
        if(found&&found->kind==V_STRING)*result=clone_value(*found);else{*result=empty_value();result->retained_type=copy_text("string");}return 1;
    }
    if(!strcmp(name,"http_set_cookie")){
        if(args[0].kind!=V_STRING||args[1].kind!=V_STRING){fault(r,"invalid HTTP response");return 1;}
        Value *path_arg=named_argument(e,args,"path"),*secure=named_argument(e,args,"secure"),*http_only=named_argument(e,args,"http_only"),*same=named_argument(e,args,"same_site");
        for(size_t i=0;i<args[0].string_length;i++)if(strchr("()<>@,;:\\\"/[]?={} \t\r\n",args[0].string[i])){fault(r,"invalid HTTP response");return 1;}
        for(size_t i=0;i<args[1].string_length;i++)if((unsigned char)args[1].string[i]>=128||args[1].string[i]==';'||args[1].string[i]=='\r'||args[1].string[i]=='\n'){fault(r,"invalid HTTP response");return 1;}
        if(!args[0].string_length||(secure&&secure->kind!=V_BOOL)||(http_only&&http_only->kind!=V_BOOL)){fault(r,"invalid HTTP response");return 1;}
        const char *cookie_path=path_arg&&path_arg->kind==V_STRING?path_arg->string:"/";const char *same_text=same&&same->kind==V_STRING?same->string:"Lax";
        if((path_arg&&path_arg->kind!=V_STRING)||cookie_path[0]!='/'||strchr(cookie_path,'\r')||strchr(cookie_path,'\n')||
           (same&&same->kind!=V_STRING)||(strcmp(same_text,"Lax")&&strcmp(same_text,"Strict")&&strcmp(same_text,"None"))){fault(r,"invalid HTTP response");return 1;}
        size_t length=args[0].string_length+args[1].string_length+strlen(cookie_path)+strlen(same_text)+48;char *text=malloc(length);
        if(!text){fault(r,"out of memory");return 1;}snprintf(text,length,"%s=%s; Path=%s%s%s%s%s",args[0].string,args[1].string,cookie_path,
            secure&&secure->kind==V_BOOL&&secure->boolean?"; Secure":"",(!http_only||http_only->kind!=V_BOOL||http_only->boolean)?"; HttpOnly":"",*same_text?"; SameSite=":"",same_text);
        Value *items=realloc(r->http_cookies.items,(r->http_cookies.count+1)*sizeof(*items));if(!items){free(text);fault(r,"out of memory");return 1;}
        r->http_cookies.items=items;r->http_cookies.items[r->http_cookies.count++]=string_value(text);free(text);result->kind=V_VOID;return 1;
    }
    if(!strcmp(name,"redirect_http")){
        Value *status=named_argument(e,args,"status");int code=status&&status->kind==V_NUMBER?(int)status->number:302;
        if(args[0].kind!=V_STRING||(code!=301&&code!=302&&code!=303&&code!=307&&code!=308)){fault(r,"invalid HTTP response");return 1;}
        r->http_response=http_default_response(code,"");Value *headers=object_field(&r->http_response,"headers");free_value(*headers);*headers=object_value(1);headers->keys[0]=copy_text("Location");headers->items[0]=clone_value(args[0]);
    }else{
        Value *status=named_argument(e,args,"status"),*body=named_argument(e,args,"body"),*content=named_argument(e,args,"content_type"),*headers_arg=named_argument(e,args,"headers");
        int code=status&&status->kind==V_NUMBER&&!status->floating?(int)status->number:200;if(code<100||code>599||(body&&(body->kind!=V_STRING&&body->kind!=V_BYTES))){fault(r,"invalid HTTP response");return 1;}
        r->http_response=http_default_response(code,body&&body->kind==V_STRING?body->string:"");Value *headers=object_field(&r->http_response,"headers");
        if(body&&body->kind==V_BYTES){Value *response_body=object_field(&r->http_response,"body");free_value(*response_body);*response_body=clone_value(*body);}
        if(content&&content->kind==V_STRING&&headers->count){free_value(headers->items[0]);headers->items[0]=clone_value(*content);}
        if(headers_arg&&headers_arg->kind==V_OBJECT){free_value(*headers);*headers=clone_value(*headers_arg);}
    }
    Value *cookies=object_field(&r->http_response,"cookies");free_value(*cookies);*cookies=clone_value(r->http_cookies);r->http_returned=1;result->kind=V_VOID;return 1;
}
static int shape_position(Runtime *r,Value value,size_t length,size_t count,int insertion,size_t *position) {
    if(value.kind==V_POSITION){
        if(!value.integer)*position=0;else if(insertion)*position=length;
        else if(count<=length)*position=length-count;else{fault(r,"invalid list shape range");return 0;}
        return 1;
    }
    if(!shape_integer(r,value,0))return 0;*position=(size_t)value.number;return 1;
}
static int list_delete_range(Value *list,size_t at,size_t count) {
    for(size_t i=at;i<at+count;i++)free_value(list->items[i]);
    memmove(list->items+at,list->items+at+count,(list->count-at-count)*sizeof(*list->items));list->count-=count;return 1;
}
static int list_insert_empty(Value *list,size_t at,size_t count) {
    if(count>SIZE_MAX-list->count)return 0;Value *items=realloc(list->items,(list->count+count)*sizeof(*items));if(!items)return 0;
    list->items=items;memmove(items+at+count,items+at,(list->count-at)*sizeof(*items));
    memset(items+at,0,count*sizeof(*items));list->count+=count;return 1;
}
static Value builtin_call(Runtime *r, Frame *frame, Expr *e) {
    Value *args = calloc(e->argc ? e->argc : 1, sizeof(*args));
    Value result = empty_value();
    if (!args) { fault(r, "out of memory"); return result; }
    const char *name = e->text;
    const HostSignature *host_api=any_host_signature(name);
    int error_constructor=error_category_name(name);
    size_t positional = positional_count(e);
    int shape_operation=!strcmp(name,"list_insert")||(!strcmp(name,"list_remove")&&positional==3)||
        !strcmp(name,"list_remove_horizontal")||!strcmp(name,"list_remove_vertical");
    for(size_t i=positional;i<e->argc;i++) if(!accepts_named_argument(name,e->arg_names[i])) {
        fault(r,"unknown named argument"); free(args); return result;
    }
    int variable = !strcmp(name, "min") || !strcmp(name, "max") || !strcmp(name, "minimum") ||
                   !strcmp(name, "maximum") || !strcmp(name, "range") ||
                   !strcmp(name, "pad_left") || !strcmp(name, "pad_right") || !strcmp(name, "substring") ||
                   !strcmp(name, "format") || !strcmp(name, "random_number") || !strcmp(name, "random_bool") ||
                   !strcmp(name, "number_range") || !strcmp(name, "command_args") ||
                   !strcmp(name, "script_path") || !strcmp(name, "arg_exists") || !strcmp(name, "unix_time");
    variable = variable || !strcmp(name, "round") || !strcmp(name, "datetime") || !strcmp(name, "datetime_from_unix") || !strcmp(name, "datetime_now") || !strcmp(name,"db_connect");
    variable = variable || !strcmp(name, "input");
    variable = variable || host_api != NULL;
    variable = variable || shape_operation;
    int three = !strcmp(name, "slice") || !strcmp(name, "slice_bytes") || !strcmp(name, "clamp") ||
                !strcmp(name, "object_set") || !strcmp(name, "reduce") || !strcmp(name, "replace") ||
                !strcmp(name, "datetime_valid") || !strcmp(name,"db_query") || !strcmp(name,"db_query_one") ||
                !strcmp(name,"db_scalar") || !strcmp(name,"db_execute");
    int two = !strcmp(name, "list_append") || !strcmp(name, "append") || !strcmp(name, "prepend") ||
              !strcmp(name, "contains") || !strcmp(name, "starts_with") || !strcmp(name, "ends_with") ||
              !strcmp(name, "index_of") || !strcmp(name, "last_index_of") ||
              !strcmp(name, "write_text") || !strcmp(name, "write_bytes") || !strcmp(name, "append_text") ||
              !strcmp(name, "copy_file") || !strcmp(name, "move_file") ||
              !strcmp(name, "bytes_get") || !strcmp(name, "bytes_concat") || !strcmp(name, "pow") ||
              !strcmp(name, "power") || !strcmp(name, "hypotenuse") || !strcmp(name, "arc_tan2") ||
              !strcmp(name, "is_close") || !strcmp(name, "greatest_common_divisor") ||
              !strcmp(name, "least_common_multiple") || !strcmp(name, "percentile") ||
              !strcmp(name, "moving_average") || !strcmp(name, "number_to_base") ||
              !strcmp(name, "base_to_number") || !strcmp(name, "object_get") || !strcmp(name, "object_has") ||
              !strcmp(name, "object_remove") || !strcmp(name, "list_remove") || !strcmp(name, "remove") ||
              !strcmp(name, "sort_by") || !strcmp(name, "sort_by_descending") ||
              !strcmp(name, "map") || !strcmp(name, "filter") ||
              !strcmp(name, "split") || !strcmp(name, "join") || !strcmp(name, "char_at") ||
              !strcmp(name, "compare") || !strcmp(name, "compare_ignore_case") ||
              !strcmp(name, "count_occurrences") || !strcmp(name, "repeat") ||
              !strcmp(name, "clip_utf8") || !strcmp(name, "find_all") ||
              !strcmp(name, "substring_before") || !strcmp(name, "substring_after") ||
              !strcmp(name, "random_int") || !strcmp(name, "random_float") || !strcmp(name, "random_sample") ||
              !strcmp(name, "secure_random_int") || !strcmp(name, "secure_random_number") ||
              !strcmp(name, "constant_time_equal") ||
              !strcmp(name, "sha256_hmac") || !strcmp(name, "hmac_sha256") || !strcmp(name, "sha512_hmac") ||
              !strcmp(name, "env_set") ||
              !strcmp(name, "datetime_from_local") || !strcmp(name, "datetime_in_timezone") ||
              !strcmp(name, "datetime_from_unix_milliseconds") || !strcmp(name, "datetime_from_unix_seconds") ||
              !strcmp(name, "datetime_format") ||
              !strcmp(name, "count") || !strcmp(name, "remove_at") || !strcmp(name,"db_columns") ||
              !strcmp(name,"db_indexes") || !strcmp(name,"db_primary_key") || !strcmp(name,"exec") ||
              !strcmp(name,"exec_checked");
    if ((shape_operation&&positional!=(size_t)((!strcmp(name,"list_insert")||!strcmp(name,"list_remove"))?3:4)) ||
        (host_api&&(positional<host_api->minimum||positional>host_api->maximum)) ||
        (!variable && positional != (size_t)(three ? 3 : two ? 2 : 1)) ||
        ((!strcmp(name, "min") || !strcmp(name, "max") || !strcmp(name, "minimum") || !strcmp(name, "maximum")) &&
         (positional < 1 || positional > 64)) ||
        ((!strcmp(name, "range") || !strcmp(name, "number_range")) && (positional < 1 || positional > 3)) ||
        ((!strcmp(name, "pad_left") || !strcmp(name, "pad_right")) && (positional < 2 || positional > 3)) ||
        (!strcmp(name, "substring") && (positional < 2 || positional > 3)) ||
        (!strcmp(name, "round") && (positional < 1 || positional > 2)) ||
        (!strcmp(name, "format") && (positional < 1 || positional > 64)) ||
        ((!strcmp(name, "random_number") || !strcmp(name, "random_bool")) && positional != 0) ||
        (!strcmp(name, "input") && positional > 1) ||
        ((!strcmp(name, "command_args") || !strcmp(name, "script_path")) && positional != 0) ||
        (!strcmp(name, "arg_exists") && (positional < 1 || positional > 32)) ||
        (!strcmp(name, "unix_time") && positional > 1) ||
        (!strcmp(name, "datetime_from_unix") && (positional < 1 || positional > 2)) ||
        (!strcmp(name, "datetime") && positional != 1 && positional != 6) ||
        (!strcmp(name, "datetime_now") && positional > 1) ||
        (!strcmp(name, "db_connect") && positional != 0)) {
        fault(r, "wrong argument count"); free(args); return result;
    }
    int callback_mode = !strcmp(name, "map") || !strcmp(name, "filter") || !strcmp(name, "reduce");
    size_t callback_index = callback_mode ? 1 : SIZE_MAX;
    Value callback_owner=empty_value();Runtime *callback_runtime=r;const char *callback_name=callback_mode?e->args[callback_index]->text:NULL;
    if(callback_mode&&e->args[callback_index]->kind==0&&e->args[callback_index]->literal.kind==V_EMPTY){fault(r,"EMPTY value cannot be used");}
    else if(callback_mode&&e->args[callback_index]->kind==7){callback_owner=evaluate(r,frame,e->args[callback_index]->left);
        if(callback_owner.kind==V_NAMESPACE&&module_exported(callback_owner.external,e->args[callback_index]->text,1))callback_runtime=&((ModuleResource *)callback_owner.external)->runtime;
        else fault(r,"function reference required");
    }else if (callback_mode && (e->args[callback_index]->kind != 1 || !find_function(r, callback_name))) {
        fault(r, "function reference required");
    }
    if(r->error){free_value(callback_owner);free(args);return result;}
    for (size_t i = 0; i < e->argc && !r->error; i++)
        if (i != callback_index && !(shape_operation&&i==0)) args[i] = evaluate(r, frame, e->args[i]);
    if (r->error) goto done;
    int accepts_empty=!strcmp(name,"type")||!strcmp(name,"type_of")||!strcmp(name,"json_encode")||
        !strcmp(name,"is_number")||!strcmp(name,"is_string")||!strcmp(name,"is_boolean")||
        !strcmp(name,"is_list")||!strcmp(name,"is_object")||!strcmp(name,"is_bytes")||
        !strcmp(name,"is_datetime")||!strcmp(name,"is_duration")||!strcmp(name,"is_secret");
    if(!accepts_empty)for(size_t i=0;i<e->argc;i++)
        if(i!=callback_index&&!(shape_operation&&i==0)&&!(!strcmp(name,"object_set")&&i==2)&&
           args[i].kind==V_EMPTY&&!args[i].retained_type){fault(r,"EMPTY value cannot be used");goto done;}
    if(!shape_operation)for(size_t i=0;i<e->argc;i++)if(args[i].kind==V_POSITION){fault(r,"position selector outside list operation");goto done;}
    if (shape_operation) {
        Value *target=shape_target(r,frame,e->args[0]);if(!target||r->error)goto done;
        if(target->kind!=V_LIST){fault(r,"list shape target required");goto done;}
        if(!strcmp(name,"list_insert")){
            if(!shape_integer(r,args[2],1))goto done;size_t count=(size_t)args[2].number,at;if(!shape_position(r,args[1],target->count,count,1,&at))goto done;
            if(at>target->count){fault(r,"invalid list shape range");goto done;}
            char *list_type=target->retained_type?copy_text(target->retained_type):value_type_text(*target);
            if(!list_type||strncmp(list_type,"list<",5)){free(list_type);fault(r,"list element type required");goto done;}
            size_t type_length=strlen(list_type);if(!list_insert_empty(target,at,count)){free(list_type);fault(r,"out of memory");goto done;}
            for(size_t i=at;i<at+count;i++)retain_value_type_part(&target->items[i],list_type+5,type_length-6);free(list_type);
        }else if(!strcmp(name,"list_remove")){
            if(!shape_integer(r,args[2],1))goto done;size_t count=(size_t)args[2].number,at;if(!shape_position(r,args[1],target->count,count,0,&at))goto done;
            if(at>target->count||count>target->count-at){fault(r,"invalid list shape range");goto done;}list_delete_range(target,at,count);
        }else if(!strcmp(name,"list_remove_horizontal")){
            if(!shape_integer(r,args[1],0)||!shape_integer(r,args[3],1))goto done;
            size_t row=(size_t)args[1].number,count=(size_t)args[3].number,at;
            if(row>=target->count||target->items[row].kind!=V_LIST||!shape_position(r,args[2],target->items[row].count,count,0,&at))goto done;
            if(row>=target->count||target->items[row].kind!=V_LIST||at>target->items[row].count||count>target->items[row].count-at){fault(r,"invalid list shape range");goto done;}
            list_delete_range(&target->items[row],at,count);
        }else{
            if(!shape_integer(r,args[1],0)||!shape_integer(r,args[3],1))goto done;
            size_t column=(size_t)args[1].number,count=(size_t)args[3].number,row;if(!shape_position(r,args[2],target->count,count,0,&row))goto done;
            if(row>target->count||count>target->count-row){fault(r,"invalid list shape range");goto done;}
            for(size_t i=row;i<target->count;i++)if(target->items[i].kind!=V_LIST||column>=target->items[i].count){fault(r,"invalid list shape range");goto done;}
            for(size_t i=row;i+count<target->count;i++){free_value(target->items[i].items[column]);target->items[i].items[column]=clone_value(target->items[i+count].items[column]);}
            for(size_t i=target->count-count;i<target->count;i++){Value *slot=&target->items[i].items[column];char *type=value_type_text(*slot);
                free_value(*slot);*slot=empty_value();slot->retained_type=type;}
        }result.kind=V_VOID;
    } else if (error_constructor) {
        if(args[0].kind!=V_STRING){fault(r,"error message must be string");goto done;}
        result=error_value(name,args[0]);if(result.kind!=V_ERROR)fault(r,"out of memory");
    } else if (host_api && native_http_builtin(r,name,e,args,&result)) {
        /* Handled against the active native HTTP request context. */
    } else if (host_api) {
        if(!r->host||!r->host->call){fault(r,"capability denied");goto done;}
        Value request=empty_value();request.kind=V_OBJECT;request.count=2;
        request.keys=calloc(2,sizeof(*request.keys));request.items=calloc(2,sizeof(*request.items));
        if(!request.keys||!request.items){free(request.keys);free(request.items);fault(r,"out of memory");goto done;}
        request.keys[0]=copy_text("arguments");request.items[0].kind=V_LIST;request.items[0].count=positional;
        request.items[0].items=calloc(positional?positional:1,sizeof(Value));
        request.keys[1]=copy_text("named");request.items[1].kind=V_OBJECT;request.items[1].count=e->argc-positional;
        request.items[1].items=calloc(request.items[1].count?request.items[1].count:1,sizeof(Value));
        request.items[1].keys=calloc(request.items[1].count?request.items[1].count:1,sizeof(char *));
        if(!request.keys[0]||!request.keys[1]||!request.items[0].items||!request.items[1].items||!request.items[1].keys){
            free_value(request);fault(r,"out of memory");goto done;
        }
        for(size_t i=0;i<positional;i++)request.items[0].items[i]=clone_value(args[i]);
        for(size_t i=positional;i<e->argc;i++){size_t j=i-positional;request.items[1].keys[j]=copy_text(e->arg_names[i]);request.items[1].items[j]=clone_value(args[i]);}
        char *json=NULL,*response=NULL,*error_code=NULL,*error_message=NULL;
        if(!database_json(request,&json))fault(r,"host request encode error");
        else {int status=r->host->call(r->host->context,name,json,&response,&error_code,&error_message);
            if(status)external_fault(r,error_code,error_message);else {result=adapter_parse_json(r,response,"host adapter returned no result","host adapter returned invalid JSON");
                if(!r->error&&!normalize_host_result(name,&result)){free_value(result);result=empty_value();fault(r,"host adapter returned invalid result");}}}
        free(json);host_release(r->host,response);host_release(r->host,error_code);host_release(r->host,error_message);free_value(request);
    } else if (!strcmp(name,"exec")||!strcmp(name,"exec_checked")||!strcmp(name,"shell_exec")||!strcmp(name,"command_exists")) {
        if(!r->process||!r->process->call){fault(r,"process permission error");goto done;}
        if(args[0].kind!=V_STRING||!args[0].string_length||string_has_nul(args[0])){fault(r,"invalid command");goto done;}
        if((!strcmp(name,"exec")||!strcmp(name,"exec_checked"))&&args[1].kind!=V_LIST){fault(r,"invalid command");goto done;}
        if(!strcmp(name,"exec")||!strcmp(name,"exec_checked"))for(size_t i=0;i<args[1].count;i++)
            if(args[1].items[i].kind!=V_STRING||string_has_nul(args[1].items[i])){fault(r,"invalid command");goto done;}
        Value request=empty_value();request.kind=V_OBJECT;request.count=1+(positional==2)+(e->argc-positional);
        request.items=calloc(request.count,sizeof(*request.items));request.keys=calloc(request.count,sizeof(*request.keys));
        if(!request.items||!request.keys){free(request.items);free(request.keys);fault(r,"out of memory");goto done;}
        size_t at=0;request.keys[at]=copy_text("command");request.items[at++]=clone_value(args[0]);
        if(positional==2){request.keys[at]=copy_text("arguments");request.items[at++]=clone_value(args[1]);}
        for(size_t i=positional;i<e->argc;i++){request.keys[at]=copy_text(e->arg_names[i]);request.items[at++]=clone_value(args[i]);}
        char *json=NULL,*response=NULL,*error_message=NULL;
        if(!database_json(request,&json))fault(r,"process request encode error");
        else {int status=r->process->call(r->process->context,name,json,&response,&error_message);
            if(status)fault(r,process_status_message(status));
            else {result=adapter_parse_json(r,response,"process adapter returned no result","process adapter returned invalid JSON");
                if(!r->error&& !strcmp(name,"command_exists")){if(result.kind!=V_BOOL){free_value(result);result=empty_value();fault(r,"process adapter returned invalid result");}}
                else if(!r->error&&!normalize_exec_result(&result)){free_value(result);result=empty_value();fault(r,"process adapter returned invalid result");}
                if(!r->error&&!strcmp(name,"exec_checked")){
                    Value *timed_out=object_field(&result,"timed_out"),*exit_code=object_field(&result,"exit_code");
                    if(timed_out->boolean)fault(r,"command timeout error");else if(exit_code->number!=0)fault(r,"command error");
                }
            }
        }
        free(json);process_release(r->process,response);process_release(r->process,error_message);free_value(request);
    } else if (!strcmp(name,"db_connect")) {
        if(!r->database||!r->database->connect||!r->database->call||!r->database->close){fault(r,"database capability denied");goto done;}
        Value request=empty_value();request.kind=V_OBJECT;request.count=e->argc;
        request.items=calloc(request.count?request.count:1,sizeof(*request.items));request.keys=calloc(request.count?request.count:1,sizeof(*request.keys));
        if(!request.items||!request.keys){free(request.items);free(request.keys);fault(r,"out of memory");goto done;}
        for(size_t i=0;i<request.count;i++){request.keys[i]=copy_text(e->arg_names[i]);request.items[i]=clone_value(args[i]);}
        char *json=NULL,*error_message=NULL;void *native=NULL;
        if(!database_json(request,&json)){fault(r,"database request encode error");}
        else {int status=r->database->connect(r->database->context,json,&native,&error_message);if(status)fault(r,database_status_message(status));
        else {DatabaseResource *resource=calloc(1,sizeof(*resource));if(!resource){r->database->close(r->database->context,native);fault(r,"out of memory");}else{resource->references=1;resource->native=native;resource->adapter=*r->database;result.kind=V_DB;result.external=resource;}}}
        free(json);database_release(r->database,error_message);free_value(request);
    } else if (!strcmp(name,"db_close")) {
        if(args[0].kind!=V_DB||!args[0].external){fault(r,"database connection required");goto done;}
        DatabaseResource *resource=args[0].external;
        if(!resource->closed){resource->adapter.close(resource->adapter.context,resource->native);resource->closed=1;resource->native=NULL;}
        result.kind=V_VOID;
    } else if (!strncmp(name,"db_",3)) {
        if(args[0].kind!=V_DB||!args[0].external){fault(r,"database connection required");goto done;}
        DatabaseResource *resource=args[0].external;if(resource->closed){fault(r,"database connection is closed");goto done;}
        Value request=empty_value();request.kind=V_OBJECT;
        if(!strcmp(name,"db_query")||!strcmp(name,"db_query_one")||!strcmp(name,"db_scalar")||!strcmp(name,"db_execute")){
            request.keys=calloc(2,sizeof(*request.keys));request.items=calloc(2,sizeof(*request.items));
            if(request.keys&&request.items){request.count=2;request.keys[0]=copy_text("sql");request.keys[1]=copy_text("parameters");request.items[0]=clone_value(args[1]);request.items[1]=clone_value(args[2]);}
        }else if(!strcmp(name,"db_columns")||!strcmp(name,"db_indexes")||!strcmp(name,"db_primary_key")){
            request.keys=calloc(1,sizeof(*request.keys));request.items=calloc(1,sizeof(*request.items));
            if(request.keys&&request.items){request.count=1;request.keys[0]=copy_text("table");request.items[0]=clone_value(args[1]);}
        }
        int request_required=!strcmp(name,"db_query")||!strcmp(name,"db_query_one")||!strcmp(name,"db_scalar")||!strcmp(name,"db_execute")||!strcmp(name,"db_columns")||!strcmp(name,"db_indexes")||!strcmp(name,"db_primary_key");
        if(request_required&&!request.count){free(request.keys);free(request.items);fault(r,"out of memory");goto done;}
        char *json=NULL,*response=NULL,*error_message=NULL;
        if(!database_json(request,&json))fault(r,"database request encode error");
        else {int status=resource->adapter.call(resource->adapter.context,resource->native,name,json,&response,&error_message);
        if(status)fault(r,database_status_message(status));
        else if(!strcmp(name,"db_begin")||!strcmp(name,"db_commit")||!strcmp(name,"db_rollback"))result.kind=V_VOID;
        else result=adapter_parse_json(r,response,"database adapter returned no result","database adapter returned invalid JSON");}
        free(json);database_release(&resource->adapter,response);database_release(&resource->adapter,error_message);free_value(request);
    } else if (!strcmp(name, "timezone")) {
        if (args[0].kind != V_STRING) { fault(r, "timezone text required"); goto done; }
        int offset = 0;
        if (args[0].string_length == 3 && !memcmp(args[0].string, "UTC", 3)) offset = 0;
        else if (args[0].string_length == 6 && (args[0].string[0] == '+' || args[0].string[0] == '-') &&
                 args[0].string[3] == ':') {
            int hours, minutes;
            if (!decimal_part(args[0].string, 1, 2, &hours) || !decimal_part(args[0].string, 4, 2, &minutes) ||
                minutes > 59 || hours > 14 || (hours == 14 && minutes) || !memcmp(args[0].string, "-00:00", 6)) {
                fault(r, "invalid timezone"); goto done;
            }
            offset = (hours * 60 + minutes) * (args[0].string[0] == '-' ? -1 : 1);
        } else { fault(r, "unsupported timezone"); goto done; }
        result = string_bytes(offset ? args[0].string : "UTC", offset ? args[0].string_length : 3);
        result.kind = V_TIMEZONE; result.integer = offset;
    } else if (!strcmp(name, "local_datetime")) {
        if (args[0].kind != V_STRING) { fault(r, "string required"); goto done; }
        if (args[0].string_length < 19 || args[0].string_length > 23 ||
            args[0].string[4] != '-' || args[0].string[7] != '-' || args[0].string[10] != 'T' ||
            args[0].string[13] != ':' || args[0].string[16] != ':') {
            fault(r, "invalid local datetime"); goto done;
        }
        int values[7] = {0};
        if (!decimal_part(args[0].string,0,4,&values[0]) || !decimal_part(args[0].string,5,2,&values[1]) ||
            !decimal_part(args[0].string,8,2,&values[2]) || !decimal_part(args[0].string,11,2,&values[3]) ||
            !decimal_part(args[0].string,14,2,&values[4]) || !decimal_part(args[0].string,17,2,&values[5]) ||
            !values[0] || values[2] < 1 || values[2] > calendar_days(values[0], values[1]) ||
            values[3] > 23 || values[4] > 59 || values[5] > 59) {
            fault(r, "invalid local datetime"); goto done;
        }
        if (args[0].string_length > 19) {
            size_t digits = args[0].string_length - 20;
            if (args[0].string[19] != '.' || digits < 1 || digits > 3 ||
                !decimal_part(args[0].string,20,digits,&values[6])) { fault(r, "invalid local datetime"); goto done; }
            if (digits == 1) values[6] *= 100; else if (digits == 2) values[6] *= 10;
        }
        char canonical[32];
        if (values[6]) snprintf(canonical,sizeof(canonical),"%04d-%02d-%02dT%02d:%02d:%02d.%03d",
                                values[0],values[1],values[2],values[3],values[4],values[5],values[6]);
        else snprintf(canonical,sizeof(canonical),"%04d-%02d-%02dT%02d:%02d:%02d",
                      values[0],values[1],values[2],values[3],values[4],values[5]);
        result = string_value(canonical); result.kind = V_LOCAL_DATETIME;
        memcpy(result.temporal, values, sizeof(values));
    } else if (!strcmp(name, "datetime_now")) {
        int offset=0;
        if (e->argc) {
            if (args[0].kind==V_TIMEZONE) offset=(int)args[0].integer;
            else if (args[0].kind==V_STRING && timezone_offset_text(args[0].string,args[0].string_length,&offset)) {}
            else { fault(r,"timezone required"); goto done; }
        }
        time_t now=time(NULL); if (now==(time_t)-1) fault(r,"clock unavailable");
        else result=datetime_epoch_value((int64_t)now*1000,offset);
    } else if (!strcmp(name, "datetime_valid")) {
        long long year,month,day;
        if (!integer_argument(args[0],&year)||!integer_argument(args[1],&month)||!integer_argument(args[2],&day))
            fault(r,"integer calendar fields required");
        else result=bool_value(year>=1&&year<=9999&&month>=1&&month<=12&&day>=1&&day<=calendar_days((int)year,(int)month));
    } else if (!strcmp(name, "datetime_format")) {
        if (args[0].kind!=V_DATETIME||args[1].kind!=V_STRING) { fault(r,"datetime and pattern required"); goto done; }
        TextBuffer formatted={0};
        for (size_t i=0;i<args[1].string_length&&!r->error;) {
            const char *token=NULL,*replacement=NULL; size_t width=0; char value[16];
            const char *pattern=args[1].string+i; size_t remaining=args[1].string_length-i;
            if (remaining>=4&&!memcmp(pattern,"yyyy",4)){token="yyyy";width=4;snprintf(value,sizeof(value),"%04d",args[0].temporal[0]);replacement=value;}
            else if(remaining>=3&&!memcmp(pattern,"SSS",3)){token="SSS";width=3;snprintf(value,sizeof(value),"%03d",args[0].temporal[6]);replacement=value;}
            else if(remaining>=3&&!memcmp(pattern,"XXX",3)){token="XXX";width=3;if(!args[0].offset_minutes)strcpy(value,"Z");else snprintf(value,sizeof(value),"%c%02d:%02d",args[0].offset_minutes<0?'-':'+',abs(args[0].offset_minutes)/60,abs(args[0].offset_minutes)%60);replacement=value;}
            else {
                const char *names[]={"MM","dd","HH","mm","ss"}; int indexes[]={1,2,3,4,5};
                for(size_t k=0;k<5;k++)if(remaining>=2&&!memcmp(pattern,names[k],2)){token=names[k];width=2;snprintf(value,sizeof(value),"%02d",args[0].temporal[indexes[k]]);replacement=value;break;}
            }
            if(token){if(!buffer_append(&formatted,replacement,strlen(replacement)))fault(r,"out of memory");i+=width;}
            else if(isalpha((unsigned char)args[1].string[i])) fault(r,"invalid datetime format");
            else {if(!buffer_append(&formatted,args[1].string+i,1))fault(r,"out of memory");i++;}
        }
        if(!r->error)result=string_bytes(formatted.data?formatted.data:"",formatted.length);free(formatted.data);
    } else if (!strcmp(name, "datetime") || !strcmp(name, "datetime_parse")) {
        if (!strcmp(name,"datetime") && positional==6) {
            int values[7]={0}; long long field;
            for(size_t i=0;i<6;i++)if(!integer_argument(args[i],&field)||field<INT_MIN||field>INT_MAX){fault(r,"integer calendar fields required");break;}else values[i]=(int)field;
            Value *zone=named_argument(e,args,"timezone"); int offset=0;
            if(!r->error && (!zone || (zone->kind!=V_TIMEZONE &&
                !(zone->kind==V_STRING&&timezone_offset_text(zone->string,zone->string_length,&offset))))) fault(r,"named timezone required");
            if(!r->error&&zone->kind==V_TIMEZONE)offset=(int)zone->integer;
            if(!r->error&&(values[0]<1||values[0]>9999||values[1]<1||values[1]>12||values[2]<1||values[2]>calendar_days(values[0],values[1])||values[3]<0||values[3]>23||values[4]<0||values[4]>59||values[5]<0||values[5]>59))fault(r,"invalid datetime fields");
            if(!r->error)result=datetime_epoch_value(calendar_to_epoch(values,offset),offset);
        } else {
            if (named_argument(e,args,"timezone")) { fault(r,"text datetime does not accept timezone"); goto done; }
            if (args[0].kind != V_STRING || args[0].string_length < 20) { fault(r,"datetime text required"); goto done; }
            size_t zone_at = args[0].string[args[0].string_length-1] == 'Z' ? args[0].string_length-1 :
                             args[0].string_length >= 6 ? args[0].string_length-6 : 0;
            int offset; int values[7]; char canonical[32];
            if (!timezone_offset_text(args[0].string+zone_at,args[0].string_length-zone_at,&offset) ||
                !parse_calendar(args[0].string,zone_at,values,canonical)) { fault(r,"invalid datetime text"); goto done; }
            result = datetime_epoch_value(calendar_to_epoch(values,offset),offset);
        }
    } else if (!strcmp(name, "datetime_from_local")) {
        if (args[0].kind != V_LOCAL_DATETIME || args[1].kind != V_TIMEZONE) { fault(r,"local datetime and timezone required"); goto done; }
        result = datetime_epoch_value(calendar_to_epoch(args[0].temporal,(int)args[1].integer),(int)args[1].integer);
    } else if (!strcmp(name, "datetime_in_timezone")) {
        if (args[0].kind != V_DATETIME || args[1].kind != V_TIMEZONE) { fault(r,"datetime and timezone required"); goto done; }
        result = datetime_epoch_value(args[0].integer,(int)args[1].integer);
    } else if (!strcmp(name, "datetime_from_unix") || !strcmp(name, "datetime_from_unix_seconds") ||
               !strcmp(name, "datetime_from_unix_milliseconds")) {
        if (args[0].kind != V_NUMBER || !isfinite(args[0].number)) { fault(r,"number required"); goto done; }
        int zone_index = !strcmp(name,"datetime_from_unix") ? (e->argc == 2 ? 1 : -1) : 1;
        int offset = 0;
        if (zone_index >= 0) {
            if (args[zone_index].kind == V_TIMEZONE) offset=(int)args[zone_index].integer;
            else if (args[zone_index].kind == V_STRING && timezone_offset_text(args[zone_index].string,args[zone_index].string_length,&offset)) {}
            else { fault(r,"timezone required"); goto done; }
        }
        long double milliseconds = !strcmp(name,"datetime_from_unix_milliseconds") ? args[0].number : (long double)args[0].number*1000.0L;
        if (floorl(milliseconds)!=milliseconds || milliseconds<INT64_MIN || milliseconds>INT64_MAX) fault(r,"datetime precision or range error");
        else result=datetime_epoch_value((int64_t)milliseconds,offset);
    } else if (!strcmp(name, "unix_milliseconds_from_datetime") || !strcmp(name, "unix_seconds_from_datetime")) {
        if (args[0].kind != V_DATETIME) { fault(r,"datetime required"); goto done; }
        if (!strcmp(name,"unix_seconds_from_datetime"))
            result=args[0].integer%1000?floating_value((double)args[0].integer/1000.0):number_value((double)(args[0].integer/1000));
        else result=number_value((double)args[0].integer);
    } else if (!strcmp(name, "datetime_offset")) {
        if (args[0].kind != V_DATETIME) fault(r,"datetime required");
        else result=duration_value((int64_t)args[0].offset_minutes*60000);
    } else if (!strcmp(name, "datetime_timezone")) {
        if (args[0].kind != V_DATETIME) fault(r,"datetime required");
        else {
            char zone[8];
            if (!args[0].offset_minutes) strcpy(zone,"UTC");
            else snprintf(zone,sizeof(zone),"%c%02d:%02d",args[0].offset_minutes<0?'-':'+',abs(args[0].offset_minutes)/60,abs(args[0].offset_minutes)%60);
            result=string_value(zone); result.kind=V_TIMEZONE; result.integer=args[0].offset_minutes;
        }
    } else if (!strncmp(name, "datetime_", 9)) {
        if (args[0].kind != V_DATETIME) { fault(r,"datetime required"); goto done; }
        int index = !strcmp(name,"datetime_year")?0:!strcmp(name,"datetime_month")?1:!strcmp(name,"datetime_day")?2:
                    !strcmp(name,"datetime_hour")?3:!strcmp(name,"datetime_minute")?4:!strcmp(name,"datetime_second")?5:
                    !strcmp(name,"datetime_millisecond")?6:-1;
        if (index >= 0) result=number_value(args[0].temporal[index]);
        else if (!strcmp(name,"datetime_weekday")) {
            int64_t days=days_from_civil(args[0].temporal[0],(unsigned)args[0].temporal[1],(unsigned)args[0].temporal[2]);
            int weekday=(int)((days+3)%7); if (weekday<0) weekday+=7; result=number_value(weekday+1);
        } else fault(r,"unknown datetime operation");
    } else if (!strcmp(name, "duration")) {
        if (args[0].kind != V_STRING) { fault(r, "string required"); goto done; }
        if (!args[0].string_length) { fault(r, "invalid duration text"); goto done; }
        size_t at = 0; int negative = 0, previous = -1; int64_t total = 0;
        if (args[0].string[at] == '-') { negative = 1; at++; }
        if (at == args[0].string_length) { fault(r, "invalid duration text"); goto done; }
        while (at < args[0].string_length && !r->error) {
            uint64_t amount = 0; size_t digits = 0;
            while (at < args[0].string_length && isdigit((unsigned char)args[0].string[at])) {
                unsigned digit = (unsigned)(args[0].string[at++] - '0');
                if (amount > (UINT64_MAX - digit) / 10) { fault(r, "duration overflow"); break; }
                amount = amount * 10 + digit; digits++;
            }
            if (r->error) break;
            uint64_t factor; int order;
            if (!digits || at >= args[0].string_length) { fault(r, "invalid duration text"); break; }
            if (args[0].string[at] == 'd') { factor = 86400000; order = 0; at++; }
            else if (args[0].string[at] == 'h') { factor = 3600000; order = 1; at++; }
            else if (args[0].string[at] == 'm' && at + 1 < args[0].string_length && args[0].string[at + 1] == 's') {
                factor = 1; order = 4; at += 2;
            } else if (args[0].string[at] == 'm') { factor = 60000; order = 2; at++; }
            else if (args[0].string[at] == 's') { factor = 1000; order = 3; at++; }
            else { fault(r, "invalid duration text"); break; }
            if (order <= previous || amount > (uint64_t)(INT64_MAX - total) / factor) { fault(r, "duration overflow or unit order"); break; }
            previous = order; total += (int64_t)(amount * factor);
        }
        if (!r->error) result = duration_value(negative ? -total : total);
    } else if (!strcmp(name, "duration_milliseconds")) {
        if (args[0].kind != V_DURATION) fault(r, "duration required");
        else if (args[0].integer < -9007199254740991LL || args[0].integer > 9007199254740991LL) fault(r, "number range error");
        else result = number_value((double)args[0].integer);
    } else if (!strcmp(name, "unix_time")) {
        if (e->argc) {
            if (args[0].kind != V_DATETIME) fault(r, "datetime value required");
            else result=args[0].integer%1000?floating_value((double)args[0].integer/1000.0):number_value((double)(args[0].integer/1000));
        }
        else {
            time_t now = time(NULL);
            if (now == (time_t)-1) fault(r, "clock unavailable"); else result = number_value((double)now);
        }
    } else if (!strcmp(name, "env_get") || !strcmp(name, "env_exists") ||
        !strcmp(name, "env_set") || !strcmp(name, "env_remove")) {
        int writing = !strcmp(name, "env_set") || !strcmp(name, "env_remove");
        if ((writing && !r->write_environment) || (!writing && !r->read_environment)) {
            fault(r, "capability denied"); goto done;
        }
        if (args[0].kind != V_STRING || !args[0].string_length ||
            strlen(args[0].string) != args[0].string_length || strchr(args[0].string, '=')) {
            fault(r, "valid environment name required"); goto done;
        }
        if (!strcmp(name, "env_get")) {
            const char *value = getenv(args[0].string); if (value) result = string_value(value);
            else { Value *fallback=named_argument(e,args,"default"); if(fallback){if(fallback->kind!=V_STRING)fault(r,"string default required");else result=clone_value(*fallback);} }
        } else if (!strcmp(name, "env_exists")) result = bool_value(getenv(args[0].string) != NULL);
        else {
            if (!strcmp(name, "env_set") && (args[1].kind != V_STRING || strlen(args[1].string) != args[1].string_length)) {
                fault(r, "string environment value required"); goto done;
            }
#ifdef _WIN32
            int failed = _putenv_s(args[0].string, !strcmp(name, "env_set") ? args[1].string : "");
#else
            int failed = !strcmp(name, "env_set") ? setenv(args[0].string, args[1].string, 1) : unsetenv(args[0].string);
#endif
            if (failed) fault(r, "environment operation failed"); else result.kind = V_VOID;
        }
    } else if (!strcmp(name, "command_args")) {
        result.kind = V_LIST; result.count = r->command_argument_count;
        result.items = calloc(result.count ? result.count : 1, sizeof(*result.items));
        if (!result.items) fault(r, "out of memory");
        else for (size_t i = 0; i < result.count; i++) result.items[i] = string_value(r->command_arguments[i]);
    } else if (!strcmp(name, "script_path")) {
        if (r->script_path) result = string_value(r->script_path);
    } else if (!strcmp(name, "arg_exists") || !strcmp(name, "arg_value")) {
        for (size_t i = 0; i < positional; i++) if (args[i].kind != V_STRING) fault(r, "string option required");
        if (r->error) goto done;
        size_t boundary = r->command_argument_count;
        for (size_t i = 0; i < boundary; i++) if (!strcmp(r->command_arguments[i], "--")) { boundary = i; break; }
        if (!strcmp(name, "arg_exists")) {
            int found = 0;
            for (size_t a = 0; a < positional; a++) for (size_t i = 0; i < boundary; i++)
                if (strlen(r->command_arguments[i]) == args[a].string_length &&
                    !memcmp(r->command_arguments[i], args[a].string, args[a].string_length)) found = 1;
            result = bool_value(found);
        } else {
            size_t found_count = 0; const char *found = NULL;
            for (size_t i = 0; i < boundary; i++) {
                const char *argument = r->command_arguments[i];
                if (strlen(argument) == args[0].string_length && !memcmp(argument, args[0].string, args[0].string_length)) {
                    if (i + 1 >= boundary || r->command_arguments[i + 1][0] == '-') { fault(r, "missing option value"); break; }
                    found = r->command_arguments[++i]; found_count++;
                } else if (strlen(argument) > args[0].string_length &&
                           !memcmp(argument, args[0].string, args[0].string_length) && argument[args[0].string_length] == '=') {
                    found = argument + args[0].string_length + 1; found_count++;
                }
            }
            if (!r->error && found_count > 1) fault(r, "repeated option");
            else if (!r->error && found) result = string_value(found);
            else if(!r->error){Value *fallback=named_argument(e,args,"default");if(fallback){if(fallback->kind!=V_STRING)fault(r,"string default required");else result=clone_value(*fallback);}}
        }
    } else if (!strcmp(name, "input")) {
        if (e->argc && args[0].kind != V_STRING) { fault(r, "string prompt required"); goto done; }
        if (e->argc) { fwrite(args[0].string, 1, args[0].string_length, r->output); fflush(r->output); }
        TextBuffer line = {0}; int c;
        while ((c = fgetc(stdin)) != EOF && c != '\n') {
            char byte = (char)c; if (!buffer_append(&line, &byte, 1)) { fault(r, "out of memory"); break; }
        }
        if (!r->error && c == EOF && !line.length) fault(r, "input reached end-of-input");
        if (!r->error) {
            if (line.length && line.data[line.length - 1] == '\r') line.length--;
            result = string_bytes(line.data ? line.data : "", line.length);
        }
        free(line.data);
    } else if (!strcmp(name, "sha256_hash") || !strcmp(name, "sha256_hmac") || !strcmp(name, "hmac_sha256")) {
        if ((args[0].kind != V_STRING && args[0].kind != V_BYTES) ||
            (e->argc == 2 && args[1].kind != V_STRING && args[1].kind != V_BYTES)) {
            fault(r, "string or bytes required"); goto done;
        }
        result.kind = V_BYTES; result.string_length = 32; result.string = malloc(33);
        if (!result.string) { fault(r, "out of memory"); goto done; }
        int ok = e->argc == 1 ? sha256_digest((unsigned char *)args[0].string, args[0].string_length,
                                               (unsigned char *)result.string) :
                 sha256_hmac_digest((unsigned char *)args[0].string, args[0].string_length,
                                    (unsigned char *)args[1].string, args[1].string_length,
                                    (unsigned char *)result.string);
        if (!ok) fault(r, "hash operation failed"); else result.string[32] = 0;
    } else if (!strcmp(name, "sha512_hash") || !strcmp(name, "sha512_hmac") ||
               !strcmp(name, "sha3_256_hash") || !strcmp(name, "sha3_512_hash")) {
        if ((args[0].kind != V_STRING && args[0].kind != V_BYTES) ||
            (e->argc == 2 && args[1].kind != V_STRING && args[1].kind != V_BYTES)) {
            fault(r, "string or bytes required"); goto done;
        }
        size_t digest_length = !strcmp(name, "sha3_256_hash") ? 32 : 64;
        result.kind = V_BYTES; result.string_length = digest_length; result.string = malloc(digest_length + 1);
        if (!result.string) { fault(r, "out of memory"); goto done; }
        int ok = 1;
        if (!strcmp(name, "sha512_hash"))
            ok = sha512_digest((unsigned char *)args[0].string, args[0].string_length,
                               (unsigned char *)result.string);
        else if (!strcmp(name, "sha512_hmac"))
            ok = sha512_hmac_digest((unsigned char *)args[0].string, args[0].string_length,
                                    (unsigned char *)args[1].string, args[1].string_length,
                                    (unsigned char *)result.string);
        else sha3_digest((unsigned char *)args[0].string, args[0].string_length,
                         (unsigned char *)result.string, digest_length);
        if (!ok) fault(r, "hash operation failed"); else result.string[digest_length] = 0;
    } else if (!strcmp(name, "constant_time_equal")) {
        if ((args[0].kind != V_STRING && args[0].kind != V_BYTES) ||
            (args[1].kind != V_STRING && args[1].kind != V_BYTES)) {
            fault(r, "string or bytes required"); goto done;
        }
        size_t maximum = args[0].string_length > args[1].string_length ? args[0].string_length : args[1].string_length;
        unsigned difference = (unsigned)(args[0].string_length ^ args[1].string_length);
        for (size_t i = 0; i < maximum; i++) {
            unsigned char left = i < args[0].string_length ? (unsigned char)args[0].string[i] : 0;
            unsigned char right = i < args[1].string_length ? (unsigned char)args[1].string[i] : 0;
            difference |= left ^ right;
        }
        result = bool_value(difference == 0);
    } else if (!strcmp(name, "secure_random_bytes") || !strcmp(name, "secure_random_string")) {
        long long length;
        if(args[0].kind!=V_NUMBER||args[0].floating||!args[0].exact_integer){fault(r,"integer required");goto done;}
        if (!integer_argument(args[0], &length) || length < 0 || length > 1048576) {
            fault(r, "invalid secure random length"); goto done;
        }
        if (!strcmp(name, "secure_random_bytes")) {
            result.kind = V_BYTES; result.string_length = (size_t)length;
            result.string = malloc(result.string_length + 1);
            if (!result.string || !secure_fill((unsigned char *)result.string, result.string_length)) {
                fault(r, "secure random source unavailable"); goto done;
            }
            result.string[result.string_length] = 0;
        } else {
            static const char alphabet[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-";
            result.kind = V_STRING; result.string_length = (size_t)length;
            result.string = malloc(result.string_length + 1);
            if (!result.string) { fault(r, "out of memory"); goto done; }
            for (size_t i = 0; i < result.string_length; i++) {
                uint64_t selected;
                if (!secure_below(64, &selected)) { fault(r, "secure random source unavailable"); break; }
                result.string[i] = alphabet[selected];
            }
            result.string[result.string_length] = 0;
        }
    } else if (!strcmp(name, "secure_random_int") || !strcmp(name, "secure_random_number")) {
        long long minimum, maximum;
        if(args[0].kind!=V_NUMBER||args[1].kind!=V_NUMBER||!args[0].exact_integer||!args[1].exact_integer){fault(r,"integer required");goto done;}
        if(args[0].kind==V_NUMBER&&args[1].kind==V_NUMBER&&args[0].exact_integer&&args[1].exact_integer&&
           number_compare(args[0],args[1])==0) result=clone_value(args[0]);
        else if(args[0].kind==V_NUMBER&&args[1].kind==V_NUMBER&&args[0].exact_integer&&args[1].exact_integer&&number_compare(args[0],args[1])>0) fault(r,"invalid secure random range");
        else {uint64_t span,selected;
            if(args[0].kind==V_NUMBER&&args[1].kind==V_NUMBER&&integer_span_u64(args[0],args[1],&span)){
                if(!secure_below(span,&selected))fault(r,"secure random source unavailable");
                else result=integer_offset(args[0],selected);
            } else if(args[0].kind==V_NUMBER&&args[1].kind==V_NUMBER&&args[0].exact_integer&&args[1].exact_integer){
                char *range=integer_span_text(args[0],args[1]);char *offset=range?random_big_below(r,range,1):NULL;free(range);
                if(!offset)fault(r,"secure random source unavailable");else{result=integer_offset_text(args[0],offset);free(offset);}
            } else if (!integer_argument(args[0], &minimum) || !integer_argument(args[1], &maximum) || minimum > maximum ||
            (double)maximum - (double)minimum + 1 > 9007199254740991.0) {
            fault(r, "invalid secure random range"); goto done;
        } else {uint64_t selected;
            if (!secure_below((uint64_t)(maximum - minimum) + 1, &selected)) fault(r, "secure random source unavailable");
            else result = number_value((double)minimum + (double)selected);}}
    } else if (!strcmp(name, "random_seed")) {
        long long seed;
        if (!integer_argument(args[0], &seed)) fault(r, "integer seed required");
        else { random_seed_runtime(r, (uint64_t)seed); result.kind = V_VOID; }
    } else if (!strcmp(name, "random_number") || !strcmp(name, "random_bool")) {
        result = !strcmp(name, "random_bool") ? bool_value((int)(random_next(r) & 1)) :
                 floating_value(random_number_value(r));
    } else if (!strcmp(name, "random_int") || !strcmp(name, "random_float")) {
        if (args[0].kind != V_NUMBER || args[1].kind != V_NUMBER) { fault(r, "number range required"); goto done; }
        if (!strcmp(name, "random_int")) {
            long long minimum, maximum;
            if(args[0].exact_integer&&args[1].exact_integer&&number_compare(args[0],args[1])==0) result=clone_value(args[0]);
            else if(args[0].exact_integer&&args[1].exact_integer&&number_compare(args[0],args[1])>0) fault(r,"invalid random integer range");
            else {uint64_t span;
                if(args[0].exact_integer&&args[1].exact_integer&&integer_span_u64(args[0],args[1],&span))
                    result=integer_offset(args[0],random_below(r,span));
                else if(args[0].exact_integer&&args[1].exact_integer){
                    char *range=integer_span_text(args[0],args[1]);char *offset=range?random_big_below(r,range,0):NULL;free(range);
                    if(!offset)fault(r,"out of memory");else{result=integer_offset_text(args[0],offset);free(offset);}
                }
                else if (!integer_argument(args[0], &minimum) || !integer_argument(args[1], &maximum) || minimum > maximum ||
                (double)maximum - (double)minimum + 1 > 9007199254740991.0) fault(r, "invalid random integer range");
                else result = number_value((double)minimum + (double)random_below(r, (uint64_t)(maximum - minimum) + 1));}
        } else if (!(args[0].number < args[1].number)) fault(r, "invalid random float range");
        else result = floating_value(args[0].number + (args[1].number - args[0].number) * random_number_value(r));
    } else if (!strcmp(name, "random_pick") || !strcmp(name, "random_shuffle") || !strcmp(name, "random_sample")) {
        if (args[0].kind != V_LIST || (!strcmp(name, "random_pick") && !args[0].count)) {
            fault(r, "non-empty list required"); goto done;
        }
        if (!strcmp(name, "random_pick")) result = clone_value(args[0].items[random_below(r, args[0].count)]);
        else {
            size_t count = args[0].count;
            if (!strcmp(name, "random_sample")) {
                long long requested;
                if (!integer_argument(args[1], &requested) || requested < 0 || (size_t)requested > count) {
                    fault(r, "invalid random sample size"); goto done;
                }
                count = (size_t)requested;
            }
            result = clone_value(args[0]);
            if (!strcmp(name, "random_shuffle")) {
                for (size_t i = result.count; i > 1; i--) {
                    size_t other = (size_t)random_below(r, i); Value swap = result.items[i - 1];
                    result.items[i - 1] = result.items[other]; result.items[other] = swap;
                }
            } else {
                for (size_t i = 0; i < count; i++) {
                    size_t other = i + (size_t)random_below(r, result.count - i); Value swap = result.items[i];
                    result.items[i] = result.items[other]; result.items[other] = swap;
                }
                for (size_t i = count; i < result.count; i++) free_value(result.items[i]);
                result.count = count;
            }
        }
    } else if (!strcmp(name, "len") || !strcmp(name, "length") || !strcmp(name, "is_empty")) {
        size_t length;
        if (args[0].kind == V_LIST) length = args[0].count;
        else if (args[0].kind == V_STRING) length = utf8_length(args[0].string, args[0].string_length);
        else if (args[0].kind == V_BYTES) length = args[0].string_length;
        else { fault(r, "length requires string, list, or bytes"); goto done; }
        result = !strcmp(name, "is_empty") ? bool_value(length == 0) : number_value((double)length);
    } else if (!strcmp(name, "size") || !strcmp(name, "first") || !strcmp(name, "last")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        if (!strcmp(name, "size")) result = number_value((double)args[0].count);
        else if (!args[0].count) fault(r, "empty list access");
        else result = clone_value(args[0].items[!strcmp(name, "first") ? 0 : args[0].count - 1]);
    } else if (!strcmp(name, "xml_escape_text") || !strcmp(name, "xml_escape_attribute")) {
        if (args[0].kind != V_STRING) { fault(r, "string required"); goto done; }
        int attribute = !strcmp(name, "xml_escape_attribute"); TextBuffer escaped = {0};
        for (size_t i = 0; i < args[0].string_length && !r->error; i++) {
            const char *replacement = NULL;
            if (args[0].string[i] == '&') replacement = "&amp;";
            else if (args[0].string[i] == '<') replacement = "&lt;";
            else if (args[0].string[i] == '>') replacement = "&gt;";
            else if (attribute && args[0].string[i] == '"') replacement = "&quot;";
            else if (attribute && args[0].string[i] == '\'') replacement = "&#x27;";
            if (replacement) { if (!buffer_append(&escaped, replacement, strlen(replacement))) fault(r, "out of memory"); }
            else if (!buffer_append(&escaped, args[0].string + i, 1)) fault(r, "out of memory");
        }
        if (!r->error) result = string_bytes(escaped.data ? escaped.data : "", escaped.length);
        free(escaped.data);
    } else if (!strcmp(name, "xml_unescape")) {
        if (args[0].kind != V_STRING) { fault(r, "string required"); goto done; }
        TextBuffer unescaped = {0};
        for (size_t i = 0; i < args[0].string_length && !r->error;) {
            if (args[0].string[i] != '&') {
                if (!buffer_append(&unescaped, args[0].string + i++, 1)) fault(r, "out of memory");
                continue;
            }
            size_t end = i + 1;
            while (end < args[0].string_length && args[0].string[end] != ';' && end - i <= 16) end++;
            if (end >= args[0].string_length || args[0].string[end] != ';') { fault(r, "invalid XML entity"); break; }
            size_t length = end - i + 1; const char *replacement = NULL; unsigned code = 0;
            if (length == 4 && !memcmp(args[0].string + i, "&lt;", 4)) replacement = "<";
            else if (length == 4 && !memcmp(args[0].string + i, "&gt;", 4)) replacement = ">";
            else if (length == 5 && !memcmp(args[0].string + i, "&amp;", 5)) replacement = "&";
            else if (length == 6 && !memcmp(args[0].string + i, "&quot;", 6)) replacement = "\"";
            else if (length == 6 && !memcmp(args[0].string + i, "&apos;", 6)) replacement = "'";
            else if (i + 3 < end && args[0].string[i + 1] == '#') {
                size_t at = i + 2; int base = 10;
                if (args[0].string[at] == 'x') { base = 16; at++; }
                if (at == end) { fault(r, "invalid XML entity"); break; }
                for (; at < end; at++) {
                    int digit = args[0].string[at] >= '0' && args[0].string[at] <= '9' ? args[0].string[at] - '0' :
                                base == 16 && args[0].string[at] >= 'a' && args[0].string[at] <= 'f' ? args[0].string[at] - 'a' + 10 :
                                base == 16 && args[0].string[at] >= 'A' && args[0].string[at] <= 'F' ? args[0].string[at] - 'A' + 10 : -1;
                    if (digit < 0 || code > (0x10FFFFu - (unsigned)digit) / (unsigned)base) { fault(r, "invalid XML entity"); break; }
                    code = code * (unsigned)base + (unsigned)digit;
                }
                if (r->error) break;
                if (code > 0x10FFFF || (code >= 0xD800 && code <= 0xDFFF) || (code < 0x20 && code != 9 && code != 10 && code != 13)) {
                    fault(r, "invalid XML character"); break;
                }
                char encoded[4]; size_t width = append_utf8(encoded, code);
                if (!buffer_append(&unescaped, encoded, width)) fault(r, "out of memory");
            } else { fault(r, "invalid XML entity"); break; }
            if (replacement && !buffer_append(&unescaped, replacement, 1)) fault(r, "out of memory");
            i = end + 1;
        }
        if (!r->error) result = string_bytes(unescaped.data ? unescaped.data : "", unescaped.length);
        free(unescaped.data);
    } else if (!strcmp(name, "clip_utf8")) {
        long long maximum;
        if (args[0].kind != V_STRING || !integer_argument(args[1], &maximum) || maximum < 0) {
            fault(r, "string and non-negative byte limit required"); goto done;
        }
        size_t length = args[0].string_length < (size_t)maximum ? args[0].string_length : (size_t)maximum;
        if (length < args[0].string_length)
            while (length && ((unsigned char)args[0].string[length] & 0xC0) == 0x80) length--;
        result = string_bytes(args[0].string, length);
    } else if (!strcmp(name, "substring")) {
        long long start, end;
        size_t characters = args[0].kind == V_STRING ? utf8_length(args[0].string, args[0].string_length) : 0;
        if (args[0].kind != V_STRING || !integer_argument(args[1], &start) || start < 0 ||
            (e->argc == 3 && (!integer_argument(args[2], &end) || end < 0))) {
            fault(r, "string and non-negative indexes required"); goto done;
        }
        if (e->argc == 2) end = (long long)characters;
        if (start > end || (size_t)end > characters) { fault(r, "invalid string range"); goto done; }
        size_t byte_start = utf8_offset(args[0].string, args[0].string_length, (size_t)start);
        size_t byte_end = utf8_offset(args[0].string, args[0].string_length, (size_t)end);
        result = string_bytes(args[0].string + byte_start, byte_end - byte_start);
    } else if (!strcmp(name, "find_all")) {
        if (args[0].kind != V_STRING || args[1].kind != V_STRING) { fault(r, "string arguments required"); goto done; }
        if (!args[1].string_length) { fault(r, "empty search string"); goto done; }
        result.kind = V_LIST;
        for (size_t i = 0; i + args[1].string_length <= args[0].string_length;) {
            if (!memcmp(args[0].string + i, args[1].string, args[1].string_length)) {
                Value *items = realloc(result.items, (result.count + 1) * sizeof(*items));
                if (!items) { fault(r, "out of memory"); break; }
                result.items = items;
                result.items[result.count++] = number_value((double)utf8_length(args[0].string, i));
                i += args[1].string_length;
            } else i++;
        }
    } else if (!strcmp(name, "substring_before") || !strcmp(name, "substring_after")) {
        if (args[0].kind != V_STRING || args[1].kind != V_STRING) { fault(r, "string arguments required"); goto done; }
        if (!args[1].string_length) { fault(r, "empty search string"); goto done; }
        size_t found = args[0].string_length;
        for (size_t i = 0; i + args[1].string_length <= args[0].string_length; i++)
            if (!memcmp(args[0].string + i, args[1].string, args[1].string_length)) { found = i; break; }
        if (found < args[0].string_length) {
            size_t start = !strcmp(name, "substring_after") ? found + args[1].string_length : 0;
            size_t length = !strcmp(name, "substring_after") ? args[0].string_length - start : found;
            result = string_bytes(args[0].string + start, length);
        }
    } else if (!strcmp(name, "char_at")) {
        long long index;
        if (args[0].kind != V_STRING || !integer_argument(args[1], &index) || index < 0) {
            fault(r, "string and non-negative index required"); goto done;
        }
        size_t start = 0, character = 0;
        while (start < args[0].string_length && character < (size_t)index) {
            start++; while (start < args[0].string_length && ((unsigned char)args[0].string[start] & 0xC0) == 0x80) start++;
            character++;
        }
        if (start >= args[0].string_length) { fault(r, "string index out of range"); goto done; }
        size_t end = start + 1;
        while (end < args[0].string_length && ((unsigned char)args[0].string[end] & 0xC0) == 0x80) end++;
        result = string_bytes(args[0].string + start, end - start);
    } else if (!strcmp(name, "compare") || !strcmp(name, "compare_ignore_case")) {
        if (args[0].kind != V_STRING || args[1].kind != V_STRING) { fault(r, "string arguments required"); goto done; }
        int comparison = ordered_compare(args[0], args[1], !strcmp(name, "compare_ignore_case"));
        result = number_value(comparison < 0 ? -1 : comparison > 0 ? 1 : 0);
    } else if (!strcmp(name, "count_occurrences")) {
        if (args[0].kind != V_STRING || args[1].kind != V_STRING) { fault(r, "string arguments required"); goto done; }
        if (!args[1].string_length) { fault(r, "empty search string"); goto done; }
        size_t count = 0;
        for (size_t i = 0; i + args[1].string_length <= args[0].string_length;) {
            if (!memcmp(args[0].string + i, args[1].string, args[1].string_length)) {
                count++; i += args[1].string_length;
            } else i++;
        }
        result = number_value((double)count);
    } else if (!strcmp(name, "split")) {
        if (args[0].kind != V_STRING || args[1].kind != V_STRING) { fault(r, "strings required"); goto done; }
        if (!args[1].string_length) { fault(r, "empty delimiter"); goto done; }
        result.kind = V_LIST; size_t start = 0;
        for (size_t i = 0; i + args[1].string_length <= args[0].string_length;) {
            if (!memcmp(args[0].string + i, args[1].string, args[1].string_length)) {
                Value *items = realloc(result.items, (result.count + 1) * sizeof(*items));
                if (!items) { fault(r, "out of memory"); break; }
                result.items = items; result.items[result.count++] = string_bytes(args[0].string + start, i - start);
                i += args[1].string_length; start = i;
            } else i++;
        }
        if (!r->error) {
            Value *items = realloc(result.items, (result.count + 1) * sizeof(*items));
            if (!items) fault(r, "out of memory");
            else { result.items = items; result.items[result.count++] = string_bytes(args[0].string + start, args[0].string_length - start); }
        }
    } else if (!strcmp(name, "join")) {
        if (args[0].kind != V_LIST || args[1].kind != V_STRING) { fault(r, "string list and separator required"); goto done; }
        TextBuffer joined = {0};
        for (size_t i = 0; i < args[0].count && !r->error; i++) {
            if (args[0].items[i].kind != V_STRING) { fault(r, "string list required"); break; }
            if (i && !buffer_append(&joined, args[1].string, args[1].string_length)) fault(r, "out of memory");
            if (!r->error && !buffer_append(&joined, args[0].items[i].string, args[0].items[i].string_length)) fault(r, "out of memory");
        }
        if (!r->error) result = string_bytes(joined.data ? joined.data : "", joined.length);
        free(joined.data);
    } else if (!strcmp(name, "replace")) {
        if (args[0].kind != V_STRING || args[1].kind != V_STRING || args[2].kind != V_STRING) { fault(r, "string arguments required"); goto done; }
        if (!args[1].string_length) { fault(r, "empty search string"); goto done; }
        TextBuffer replaced = {0};
        for (size_t i = 0; i < args[0].string_length && !r->error;) {
            if (i + args[1].string_length <= args[0].string_length &&
                !memcmp(args[0].string + i, args[1].string, args[1].string_length)) {
                if (!buffer_append(&replaced, args[2].string, args[2].string_length)) fault(r, "out of memory");
                i += args[1].string_length;
            } else if (!buffer_append(&replaced, args[0].string + i++, 1)) fault(r, "out of memory");
        }
        if (!r->error) result = string_bytes(replaced.data ? replaced.data : "", replaced.length);
        free(replaced.data);
    } else if (!strcmp(name, "format")) {
        if (args[0].kind != V_STRING) { fault(r, "format string template required"); goto done; }
        TextBuffer formatted = {0}; size_t value_index = 1;
        for (size_t i = 0; i < args[0].string_length && !r->error;) {
            char c = args[0].string[i];
            if (i + 1 < args[0].string_length && c == '{' && args[0].string[i + 1] == '{') {
                if (!buffer_append(&formatted, "{", 1)) fault(r, "out of memory"); i += 2;
            } else if (i + 1 < args[0].string_length && c == '}' && args[0].string[i + 1] == '}') {
                if (!buffer_append(&formatted, "}", 1)) fault(r, "out of memory"); i += 2;
            } else if (i + 1 < args[0].string_length && c == '{' && args[0].string[i + 1] == '}') {
                if (value_index >= e->argc) fault(r, "format argument mismatch");
                else if (!buffer_display(&formatted, args[value_index++])) fault(r, "out of memory");
                i += 2;
            } else if (c == '{' || c == '}') fault(r, "invalid format template");
            else { if (!buffer_append(&formatted, args[0].string + i, 1)) fault(r, "out of memory"); i++; }
        }
        if (!r->error && value_index != e->argc) fault(r, "format argument mismatch");
        if (!r->error) result = string_bytes(formatted.data ? formatted.data : "", formatted.length);
        free(formatted.data);
    } else if (!strcmp(name, "repeat") || !strcmp(name, "pad_left") || !strcmp(name, "pad_right")) {
        long long target;
        if(args[0].kind!=V_STRING||args[1].kind!=V_NUMBER||args[1].floating||!args[1].exact_integer){fault(r,"string and integer required");goto done;}
        if (!integer_argument(args[1], &target) || target < 0) {
            fault(r, "string and non-negative integer required"); goto done;
        }
        Value fill = e->argc == 3 ? args[2] : string_value(" ");
        if (strcmp(name, "repeat") && (fill.kind != V_STRING || utf8_length(fill.string, fill.string_length) != 1))
            fault(r, "one character fill required");
        size_t characters = utf8_length(args[0].string, args[0].string_length);
        size_t copies = !strcmp(name, "repeat") ? (size_t)target : (target > (long long)characters ? (size_t)target - characters : 0);
        TextBuffer padded = {0};
        if (!r->error && !strcmp(name, "pad_right") && !buffer_append(&padded, args[0].string, args[0].string_length)) fault(r, "out of memory");
        for (size_t i = 0; i < copies && !r->error; i++) {
            const Value *piece = !strcmp(name, "repeat") ? &args[0] : &fill;
            if (!buffer_append(&padded, piece->string, piece->string_length)) fault(r, "out of memory");
        }
        if (!r->error && strcmp(name, "pad_right") && strcmp(name, "repeat") &&
            !buffer_append(&padded, args[0].string, args[0].string_length)) fault(r, "out of memory");
        if (!r->error) result = string_bytes(padded.data ? padded.data : "", padded.length);
        free(padded.data); if (e->argc != 3) free_value(fill);
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
        if (args[0].kind == V_STRING) {
            if (args[1].kind != V_STRING) { fault(r, "string search required"); goto done; }
            if (!args[1].string_length) { fault(r, "empty search string"); goto done; }
            size_t found = args[0].string_length;
            for (size_t i = 0; i + args[1].string_length <= args[0].string_length; i++) {
                if (!memcmp(args[0].string + i, args[1].string, args[1].string_length)) {
                    found = i; if (!strcmp(name, "index_of")) break;
                }
            }
            if (found < args[0].string_length) result = number_value((double)utf8_length(args[0].string, found));
            goto done;
        }
        if (args[0].kind != V_LIST) { fault(r, "string or list required"); goto done; }
        if (args[0].count && args[0].items[0].kind != args[1].kind) { fault(r, "incompatible search value"); goto done; }
        for (size_t i = 0; i < args[0].count; i++) {
            size_t index = !strcmp(name, "index_of") ? i : args[0].count - i - 1;
            if (same_value(args[0].items[index], args[1])) { result = number_value((double)index); break; }
        }
    } else if (!strcmp(name, "count")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        if (args[0].count && args[0].items[0].kind != args[1].kind) {
            fault(r, "incompatible search value"); goto done;
        }
        size_t count = 0;
        for (size_t i = 0; i < args[0].count; i++) if (same_value(args[0].items[i], args[1])) count++;
        result = number_value((double)count);
    } else if (!strcmp(name, "unique")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        result.kind = V_LIST;
        result.items = calloc(args[0].count ? args[0].count : 1, sizeof(*result.items));
        if (!result.items) { fault(r, "out of memory"); goto done; }
        for (size_t i = 0; i < args[0].count; i++) {
            int found = 0;
            for (size_t j = 0; j < result.count; j++)
                if (same_value(result.items[j], args[0].items[i])) { found = 1; break; }
            if (!found) result.items[result.count++] = clone_value(args[0].items[i]);
        }
    } else if (!strcmp(name, "remove_at")) {
        if(args[0].kind!=V_LIST||args[1].kind!=V_NUMBER||args[1].floating||floor(args[1].number)!=args[1].number){fault(r,"list index type invalid");goto done;}
        if (args[1].number < 0 || args[1].number >= (double)args[0].count) {
            fault(r, "list index out of range or invalid"); goto done;
        }
        size_t removed = (size_t)args[1].number;
        result.kind = V_LIST; result.count = args[0].count - 1;
        result.items = calloc(result.count ? result.count : 1, sizeof(*result.items));
        if (!result.items) { fault(r, "out of memory"); goto done; }
        for (size_t i = 0, j = 0; i < args[0].count; i++)
            if (i != removed) result.items[j++] = clone_value(args[0].items[i]);
    } else if (!strcmp(name, "map") || !strcmp(name, "filter") || !strcmp(name, "reduce")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        const char *callback = callback_name;
        if (!strcmp(name, "reduce")) {
            result = clone_value(args[2]);
            for (size_t i = 0; i < args[0].count && !r->error; i++) {
                Value callback_args[2] = {result, args[0].items[i]};
                Value next = invoke_named(callback_runtime, callback, callback_args, 2);
                if (!r->error && next.kind != result.kind) fault(r, "callback returned inconsistent type");
                if (!r->error) { free_value(result); result = next; }
                else free_value(next);
            }
        } else {
            result.kind = V_LIST;
            result.items = calloc(args[0].count ? args[0].count : 1, sizeof(*result.items));
            if (!result.items) { fault(r, "out of memory"); goto done; }
            for (size_t i = 0; i < args[0].count && !r->error; i++) {
                Value callback_args[1] = {args[0].items[i]};
                Value value = invoke_named(callback_runtime, callback, callback_args, 1);
                if (!strcmp(name, "filter")) {
                    if (!r->error && value.kind != V_BOOL) fault(r, "filter predicate must return boolean");
                    if (!r->error && value.boolean) result.items[result.count++] = clone_value(args[0].items[i]);
                    free_value(value);
                } else {
                    if (result.count && value.kind != result.items[0].kind) fault(r, "callback returned inconsistent type");
                    if (!r->error) result.items[result.count++] = value; else free_value(value);
                }
            }
        }
    } else if (!strcmp(name, "list_remove") || !strcmp(name, "remove")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        if (args[0].count && args[0].items[0].kind != args[1].kind) { fault(r, "incompatible search value"); goto done; }
        size_t removed = args[0].count;
        for (size_t i = 0; i < args[0].count; i++) if (same_value(args[0].items[i], args[1])) { removed = i; break; }
        if (removed == args[0].count) { fault(r, "list value not found"); goto done; }
        result.kind = V_LIST; result.count = args[0].count - 1;
        result.items = calloc(result.count ? result.count : 1, sizeof(*result.items));
        if (!result.items) { fault(r, "out of memory"); goto done; }
        for (size_t i = 0, j = 0; i < args[0].count; i++)
            if (i != removed) result.items[j++] = clone_value(args[0].items[i]);
    } else if (!strcmp(name, "flatten")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        result.kind = V_LIST;
        for (size_t i = 0; i < args[0].count; i++) {
            if (args[0].items[i].kind != V_LIST) { fault(r, "nested list required"); break; }
            Value *next = realloc(result.items, (result.count + args[0].items[i].count) * sizeof(*next));
            if (!next && args[0].items[i].count) { fault(r, "out of memory"); break; }
            result.items = next;
            for (size_t j = 0; j < args[0].items[i].count; j++) {
                if (result.count && result.items[0].kind != args[0].items[i].items[j].kind) {
                    fault(r, "list elements must have the same type"); break;
                }
                result.items[result.count++] = clone_value(args[0].items[i].items[j]);
            }
            if (r->error) break;
        }
    } else if (!strcmp(name, "reverse")) {
        if (args[0].kind == V_STRING) {
            size_t characters = utf8_length(args[0].string, args[0].string_length);
            TextBuffer reversed = {0};
            for (size_t i = characters; i; i--) {
                size_t start = utf8_offset(args[0].string, args[0].string_length, i - 1);
                size_t end = utf8_offset(args[0].string, args[0].string_length, i);
                if (!buffer_append(&reversed, args[0].string + start, end - start)) { fault(r, "out of memory"); break; }
            }
            if (!r->error) result = string_bytes(reversed.data ? reversed.data : "", reversed.length);
            free(reversed.data); goto done;
        }
        if (args[0].kind != V_LIST) { fault(r, "string or list required"); goto done; }
        result.kind = V_LIST; result.count = args[0].count;
        result.items = calloc(result.count ? result.count : 1, sizeof(*result.items));
        if (!result.items) { fault(r, "out of memory"); result = empty_value(); goto done; }
        for (size_t i = 0; i < result.count; i++)
            result.items[i] = clone_value(args[0].items[result.count - 1 - i]);
    } else if (!strcmp(name, "sort") || !strcmp(name, "sort_descending") ||
               !strcmp(name, "sort_ignore_case") || !strcmp(name, "sort_ignore_case_descending") ||
               !strcmp(name, "sort_natural") || !strcmp(name, "sort_natural_descending") ||
               !strcmp(name, "sort_natural_ignore_case") || !strcmp(name, "sort_natural_ignore_case_descending")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        for(size_t i=0;i<args[0].count;i++)if(args[0].items[i].kind==V_EMPTY){fault(r,"EMPTY value cannot be used");goto done;}
        if (args[0].count && args[0].items[0].kind != V_NUMBER && args[0].items[0].kind != V_STRING &&
            args[0].items[0].kind != V_DURATION && args[0].items[0].kind != V_LOCAL_DATETIME &&
            args[0].items[0].kind != V_DATETIME) {
            fault(r, "ordered scalar list required"); goto done;
        }
        int ignore_case = strstr(name, "ignore_case") != NULL;
        int natural = strstr(name, "natural") != NULL;
        int descending = strstr(name, "descending") != NULL;
        if ((ignore_case || natural) && args[0].count && args[0].items[0].kind != V_STRING) {
            fault(r, "string list required"); goto done;
        }
        result = clone_value(args[0]);
        for (size_t i = 1; i < result.count; i++) for (size_t j = i; j; j--) {
            int comparison = natural ? natural_string_compare(result.items[j - 1], result.items[j], ignore_case) :
                                       ordered_compare(result.items[j - 1], result.items[j], ignore_case);
            if ((!descending && comparison <= 0) || (descending && comparison >= 0)) break;
            Value swap = result.items[j - 1]; result.items[j - 1] = result.items[j]; result.items[j] = swap;
        }
    } else if (!strcmp(name, "sort_by") || !strcmp(name, "sort_by_descending")) {
        if (args[0].kind != V_LIST || args[1].kind != V_STRING || !args[1].string_length) {
            fault(r, "object list and field required"); goto done;
        }
        int descending = !strcmp(name, "sort_by_descending");
        result = clone_value(args[0]);
        for (size_t i = 0; i < result.count && !r->error; i++) {
            if (result.items[i].kind != V_OBJECT) { fault(r, "object list required"); break; }
            size_t field = result.items[i].count;
            for (size_t k = 0; k < result.items[i].count; k++)
                if (strlen(result.items[i].keys[k]) == args[1].string_length &&
                    !memcmp(result.items[i].keys[k], args[1].string, args[1].string_length)) { field = k; break; }
            if (field == result.items[i].count ||
                (result.items[i].items[field].kind != V_NUMBER && result.items[i].items[field].kind != V_STRING))
                fault(r, "missing or unordered object field");
        }
        for (size_t i = 1; i < result.count && !r->error; i++) for (size_t j = i; j; j--) {
            Value *left = &result.items[j - 1], *right = &result.items[j];
            size_t lf = 0, rf = 0;
            while (lf < left->count && strcmp(left->keys[lf], args[1].string)) lf++;
            while (rf < right->count && strcmp(right->keys[rf], args[1].string)) rf++;
            if (lf == left->count || rf == right->count || left->items[lf].kind != right->items[rf].kind) {
                fault(r, "inconsistent object field type"); break;
            }
            int comparison = ordered_compare(left->items[lf], right->items[rf], 0);
            if ((!descending && comparison <= 0) || (descending && comparison >= 0)) break;
            Value swap = *left; *left = *right; *right = swap;
        }
    } else if (!strcmp(name, "slice")) {
        if(args[0].kind!=V_LIST||args[1].kind!=V_NUMBER||args[2].kind!=V_NUMBER||args[1].floating||args[2].floating){fault(r,"list index type invalid");goto done;}
        if(args[1].number<0||args[2].number<args[1].number||args[2].number>(double)args[0].count){fault(r,"list index out of range or invalid");goto done;}
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
    } else if (!strcmp(name, "abs") || !strcmp(name, "absolute")) {
        if (args[0].kind != V_NUMBER) fault(r, "number required");
        else if(args[0].exact_integer){char text[32];const char *value=integer_text(args[0],text);result=integer_text_value(big_abs(value));}
        else { result = number_value(fabs(args[0].number)); result.floating = args[0].floating; }
    } else if (!strcmp(name, "pow") || !strcmp(name, "power")) {
        if (args[0].kind != V_NUMBER || args[1].kind != V_NUMBER) fault(r, "number required");
        else if(args[0].exact_integer&&args[1].exact_integer){char a[32],b[32];const char *exponent=integer_text(args[1],b);
            if(*exponent=='-')result=floating_value(pow(args[0].number,args[1].number));
            else if(args[1].big_integer)fault(r,"math domain error");
            else if(!big_power_within_limit(integer_text(args[0],a),(uint64_t)args[1].integer))fault(r,"exact power size limit");
            else result=big_result(big_power(integer_text(args[0],a),(uint64_t)args[1].integer));
        } else {
            double value = pow(args[0].number, args[1].number);
            if (!isfinite(value)) fault(r, "math domain error");
            else result = (args[0].floating || args[1].floating || args[1].number < 0) ?
                floating_value(value) : number_value(value);
        }
    } else if (!strcmp(name, "min") || !strcmp(name, "max") ||
               !strcmp(name, "minimum") || !strcmp(name, "maximum")) {
        Value *values = args;
        size_t count = e->argc;
        if (!count) { fault(r, "empty collection"); goto done; }
        if (values[0].kind != V_NUMBER) { fault(r, "number required"); goto done; }
        result = clone_value(values[0]);
        for (size_t i = 1; i < count; i++) {
            if (values[i].kind != V_NUMBER) { fault(r, "number required"); break; }
            int choose_minimum = !strcmp(name, "min") || !strcmp(name, "minimum");
            int compared=number_compare(values[i],result);
            if ((choose_minimum && compared < 0) || (!choose_minimum && compared > 0)) {
                free_value(result); result = clone_value(values[i]);
            }
        }
    } else if (!strcmp(name, "average")) {
        if (args[0].kind != V_LIST || !args[0].count) { fault(r, "non-empty number list required"); goto done; }
        double total = 0;
        for (size_t i = 0; i < args[0].count; i++) {
            if (args[0].items[i].kind != V_NUMBER) { fault(r, "number list required"); break; }
            total += args[0].items[i].number;
        }
        if (!r->error) result = floating_value(total / (double)args[0].count);
    } else if (!strcmp(name, "range") || !strcmp(name, "number_range")) {
        Value start=e->argc==1?integer_value(0):clone_value(args[0]);
        Value stop=clone_value(e->argc==1?args[0]:args[1]);
        Value step=e->argc==3?clone_value(args[2]):integer_value(1),zero=integer_value(0);
        if(!start.exact_integer||!stop.exact_integer||!step.exact_integer)fault(r,"integer required");
        int direction=!r->error?number_compare(step,zero):0;
        if(!r->error&&!direction)fault(r,"invalid range step");
        if(!r->error){size_t capacity=0;Value current=clone_value(start);result.kind=V_LIST;
            while((direction>0&&number_compare(current,stop)<0)||(direction<0&&number_compare(current,stop)>0)){
                if(result.count>=1000000){fault(r,"range too large");break;}
                if(result.count==capacity){size_t next=capacity?capacity*2:8;Value *items=realloc(result.items,next*sizeof(*items));if(!items){fault(r,"out of memory");break;}result.items=items;capacity=next;}
                result.items[result.count++]=clone_value(current);char current_text[32],step_text[32];char *next=big_add(integer_text(current,current_text),integer_text(step,step_text));free_value(current);
                current=big_result(next);if(current.kind==V_EMPTY){fault(r,"out of memory");break;}
            }free_value(current);
        }
        free_value(start);free_value(stop);free_value(step);
    } else if (!strcmp(name, "clamp")) {
        if (args[0].kind != V_NUMBER || args[1].kind != V_NUMBER || args[2].kind != V_NUMBER)
            fault(r, "number required");
        else if (number_compare(args[1],args[2]) > 0) fault(r, "math range error");
        else {
            Value selected=number_compare(args[0],args[1])<0?args[1]:number_compare(args[0],args[2])>0?args[2]:args[0];
            result=clone_value(selected);
        }
    } else if (!strcmp(name, "hypotenuse") || !strcmp(name, "arc_tan2") || !strcmp(name, "is_close")) {
        if (args[0].kind != V_NUMBER || args[1].kind != V_NUMBER) { fault(r, "number required"); goto done; }
        if (!strcmp(name, "hypotenuse")) result = floating_value(hypot(args[0].number, args[1].number));
        else if (!strcmp(name, "arc_tan2")) result = floating_value(atan2(args[0].number, args[1].number));
        else {
            double difference = fabs(args[0].number - args[1].number);
            double scale = fmax(fabs(args[0].number), fabs(args[1].number));
            result = bool_value(difference <= 1e-9 * scale);
        }
    } else if (!strcmp(name, "ceil") || !strcmp(name, "floor") || !strcmp(name, "sqrt") ||
               !strcmp(name, "square_root") || !strcmp(name, "cube_root") ||
               !strcmp(name, "sin") || !strcmp(name, "cos") || !strcmp(name, "tan") ||
               !strcmp(name, "round") || !strcmp(name, "truncate") || !strcmp(name, "sign") ||
               !strcmp(name, "exponential") || !strcmp(name, "exp") || !strcmp(name, "exponential_base2") ||
               !strcmp(name, "natural_log") || !strcmp(name, "log") || !strcmp(name, "log_base2") ||
               !strcmp(name, "log2") || !strcmp(name, "log_base10") || !strcmp(name, "log10") ||
               !strcmp(name, "log_one_plus") || !strcmp(name, "arc_sin") || !strcmp(name, "arc_cos") ||
               !strcmp(name, "arc_tan") || !strcmp(name, "sinh") || !strcmp(name, "cosh") ||
               !strcmp(name, "tanh") || !strcmp(name, "arc_sinh") || !strcmp(name, "arc_cosh") ||
               !strcmp(name, "arc_tanh") || !strcmp(name, "to_radians") || !strcmp(name, "to_degrees") ||
               !strcmp(name, "is_finite") || !strcmp(name, "is_infinite") || !strcmp(name, "is_nan") ||
               !strcmp(name, "is_integer_value")) {
        if (args[0].kind != V_NUMBER || (!args[0].big_integer&&!isfinite(args[0].number))) { fault(r, "finite number required"); goto done; }
        double n = args[0].number;
        if(!strcmp(name,"round")) {
            long long digits=0;
            if(e->argc==2&&!integer_argument(args[1],&digits))fault(r,"integer required");
            else if(digits < -100 || digits > 100)fault(r,"math range error");
            else if(args[0].exact_integer)result=clone_value(args[0]);
            else {char text[64]={0};for(int precision=1;precision<=17;precision++){snprintf(text,sizeof(text),"%.*g",precision,n);if(strtod(text,NULL)==n)break;}long double value=strtold(text,NULL),factor=powl(10.0L,fabsl((long double)digits));
                long double scaled=digits>0?value*factor:value/factor,rounded=scaled>=0?floorl(scaled+0.5L):ceill(scaled-0.5L);
                long double output=digits>0?rounded/factor:rounded*factor;
                if(!isfinite((double)output))fault(r,"math domain error");
                else if(digits>0)result=floating_value((double)output);else result=number_value((double)output);
            }
        }
        else if (args[0].exact_integer&&(!strcmp(name,"ceil")||!strcmp(name,"floor")||!strcmp(name,"truncate"))) result=clone_value(args[0]);
        else if (!strcmp(name, "ceil")) result = number_value(ceil(n));
        else if (!strcmp(name, "floor")) result = number_value(floor(n));
        else if (!strcmp(name, "sqrt") || !strcmp(name, "square_root")) {
            if (n < 0) fault(r, "math domain error"); else result = floating_value(sqrt(n));
        } else if (!strcmp(name, "cube_root")) result = floating_value(cbrt(n));
        else if (!strcmp(name, "truncate")) result = number_value(trunc(n));
        else if (!strcmp(name, "sign")) {if(args[0].exact_integer){char text[32];const char *value=integer_text(args[0],text);result=integer_value(*value=='-'?-1:strcmp(value,"0")?1:0);}else result=number_value(n < 0 ? -1 : n > 0 ? 1 : 0);}
        else if (!strcmp(name, "exponential") || !strcmp(name, "exp")) result = floating_value(exp(n));
        else if (!strcmp(name, "exponential_base2")) result = floating_value(exp2(n));
        else if (!strcmp(name, "natural_log") || !strcmp(name, "log")) { if (n <= 0) fault(r, "math domain error"); else result = floating_value(log(n)); }
        else if (!strcmp(name, "log_base2") || !strcmp(name, "log2")) { if (n <= 0) fault(r, "math domain error"); else result = floating_value(log2(n)); }
        else if (!strcmp(name, "log_base10") || !strcmp(name, "log10")) { if (n <= 0) fault(r, "math domain error"); else result = floating_value(log10(n)); }
        else if (!strcmp(name, "log_one_plus")) { if (n <= -1) fault(r, "math domain error"); else result = floating_value(log1p(n)); }
        else if (!strcmp(name, "arc_sin")) { if (fabs(n) > 1) fault(r, "math domain error"); else result = floating_value(asin(n)); }
        else if (!strcmp(name, "arc_cos")) { if (fabs(n) > 1) fault(r, "math domain error"); else result = floating_value(acos(n)); }
        else if (!strcmp(name, "arc_tan")) result = floating_value(atan(n));
        else if (!strcmp(name, "sinh")) result = floating_value(sinh(n));
        else if (!strcmp(name, "cosh")) result = floating_value(cosh(n));
        else if (!strcmp(name, "tanh")) result = floating_value(tanh(n));
        else if (!strcmp(name, "arc_sinh")) result = floating_value(asinh(n));
        else if (!strcmp(name, "arc_cosh")) { if (n < 1) fault(r, "math domain error"); else result = floating_value(acosh(n)); }
        else if (!strcmp(name, "arc_tanh")) { if (fabs(n) >= 1) fault(r, "math domain error"); else result = floating_value(atanh(n)); }
        else if (!strcmp(name, "to_radians")) result = floating_value(n * 3.14159265358979323846 / 180.0);
        else if (!strcmp(name, "to_degrees")) result = floating_value(n * 180.0 / 3.14159265358979323846);
        else if (!strcmp(name, "is_finite")) result = bool_value(isfinite(n));
        else if (!strcmp(name, "is_infinite")) result = bool_value(isinf(n));
        else if (!strcmp(name, "is_nan")) result = bool_value(isnan(n));
        else if (!strcmp(name, "is_integer_value")) result = bool_value(args[0].exact_integer||floor(n) == n);
        else if (!strcmp(name, "sin")) result = floating_value(sin(n));
        else if (!strcmp(name, "cos")) result = floating_value(cos(n));
        else if (!strcmp(name, "tan")) result = floating_value(tan(n));
        else result = number_value(n >= 0 ? floor(n + 0.5) : ceil(n - 0.5));
        if (!r->error && result.kind == V_NUMBER && !result.big_integer && !isfinite(result.number))
            fault(r, "math domain error");
    } else if (!strcmp(name, "greatest_common_divisor") || !strcmp(name, "least_common_multiple")) {
        if(args[0].kind==V_NUMBER&&args[1].kind==V_NUMBER&&args[0].exact_integer&&args[1].exact_integer){char a[32],b[32];const char *left=integer_text(args[0],a),*right=integer_text(args[1],b);char *gcd=big_gcd(left,right);
            if(!gcd)fault(r,"math range error");
            else if(!strcmp(name,"greatest_common_divisor"))result=big_result(gcd);
            else if(!strcmp(left,"0")||!strcmp(right,"0")){free(gcd);result=integer_value(0);}
            else {char *quotient=NULL,*remainder=NULL;if(!big_divmod_abs(big_abs(left),gcd,&quotient,&remainder)){free(gcd);fault(r,"math range error");}else{free(remainder);char *product=big_multiply(quotient,big_abs(right));free(quotient);free(gcd);result=big_result(product);}}
            goto done;
        }
        long long first, second;
        if (!integer_argument(args[0], &first) || !integer_argument(args[1], &second)) {
            fault(r, "integer required"); goto done;
        }
        long long gcd = integer_gcd(first, second);
        if (!strcmp(name, "greatest_common_divisor")) result = number_value((double)gcd);
        else {
            double lcm = (!first || !second) ? 0 : fabs((double)(first / gcd) * (double)second);
            if (lcm > 9007199254740991.0) fault(r, "math range error");
            else result = number_value(lcm);
        }
    } else if (!strcmp(name, "factorial")) {
        long long value;
        if(!integer_argument(args[0],&value)){fault(r,"integer required");goto done;}
        if(value<0||value>1000){fault(r,"math range error");goto done;}
        char *product=copy_text("1");
        for(long long i=2;i<=value&&product;i++){char factor[32];snprintf(factor,sizeof(factor),"%lld",i);char *next=big_multiply(product,factor);free(product);product=next;}
        result=big_result(product);if(result.kind==V_EMPTY)fault(r,"math range error");
    } else if (!strcmp(name, "number_to_binary") || !strcmp(name, "number_to_octal") ||
               !strcmp(name, "number_to_hexadecimal") || !strcmp(name, "number_to_base")) {
        int base = !strcmp(name, "number_to_binary") ? 2 : !strcmp(name, "number_to_octal") ? 8 :
                   !strcmp(name, "number_to_hexadecimal") ? 16 :
                   args[1].kind == V_NUMBER && floor(args[1].number) == args[1].number ? (int)args[1].number : 0;
        result = number_to_base_value(r, args[0], base);
    } else if (!strcmp(name, "binary_to_number") || !strcmp(name, "octal_to_number") ||
               !strcmp(name, "hexadecimal_to_number") || !strcmp(name, "base_to_number")) {
        int base = !strcmp(name, "binary_to_number") ? 2 : !strcmp(name, "octal_to_number") ? 8 :
                   !strcmp(name, "hexadecimal_to_number") ? 16 :
                   args[1].kind == V_NUMBER && floor(args[1].number) == args[1].number ? (int)args[1].number : 0;
        result = base_to_number_value(r, args[0], base);
    } else if (!strcmp(name, "median") || !strcmp(name, "variance") ||
               !strcmp(name, "sample_variance") || !strcmp(name, "standard_deviation") ||
               !strcmp(name, "sample_standard_deviation") || !strcmp(name, "percentile") ||
               !strcmp(name, "moving_average")) {
        if (args[0].kind != V_LIST || !args[0].count) { fault(r, "non-empty number list required"); goto done; }
        size_t count = args[0].count;
        double *values = malloc(count * sizeof(*values));
        if (!values) { fault(r, "out of memory"); goto done; }
        double total = 0;
        for (size_t i = 0; i < count; i++) {
            if (args[0].items[i].kind != V_NUMBER || !isfinite(args[0].items[i].number)) {
                fault(r, "number list required"); break;
            }
            values[i] = args[0].items[i].number; total += values[i];
        }
        if (!r->error && !strcmp(name, "moving_average")) {
            long long window;
            if (!integer_argument(args[1], &window) || window < 1 || (size_t)window > count) fault(r, "invalid moving average window");
            else {
                result.kind = V_LIST; result.count = count - (size_t)window + 1;
                result.items = calloc(result.count, sizeof(*result.items));
                if (!result.items) fault(r, "out of memory");
                else for (size_t i = 0; i < result.count; i++) {
                    double sum = 0; for (size_t j = 0; j < (size_t)window; j++) sum += values[i + j];
                    result.items[i] = floating_value(sum / (double)window);
                }
            }
        } else if (!r->error && (!strcmp(name, "median") || !strcmp(name, "percentile"))) {
            qsort(values, count, sizeof(*values), compare_doubles);
            if (!strcmp(name, "median")) result = count % 2 ? number_value(values[count / 2]) :
                floating_value((values[count / 2 - 1] + values[count / 2]) / 2.0);
            else if (args[1].kind != V_NUMBER || args[1].number < 0 || args[1].number > 100) fault(r, "percentile requires 0..100");
            else {
                double rank = (double)(count - 1) * args[1].number / 100.0;
                size_t lower = (size_t)floor(rank), upper = (size_t)ceil(rank);
                result = lower == upper ? number_value(values[lower]) : floating_value(
                    values[lower] + (values[upper] - values[lower]) * (rank - (double)lower));
            }
        } else if (!r->error) {
            int sample = !strcmp(name, "sample_variance") || !strcmp(name, "sample_standard_deviation");
            if (sample && count < 2) fault(r, "at least two values required");
            else {
                double mean = total / (double)count, squares = 0;
                for (size_t i = 0; i < count; i++) { double difference = values[i] - mean; squares += difference * difference; }
                double variance = squares / (double)(count - (size_t)sample);
                if (!strcmp(name, "standard_deviation") || !strcmp(name, "sample_standard_deviation"))
                    result = floating_value(sqrt(variance));
                else {
                    result = number_value(variance);
                    result.floating = floor(variance) != variance;
                }
            }
        }
        free(values);
    } else if (!strcmp(name, "sum")) {
        if (args[0].kind != V_LIST) { fault(r, "list required"); goto done; }
        double total = 0;int floating = 0,all_exact=1;char *exact_total=copy_text("0");
        for (size_t i = 0; i < args[0].count; i++) {
            if (args[0].items[i].kind != V_NUMBER) { fault(r, "number list required"); break; }
            total += args[0].items[i].number;
            floating |= args[0].items[i].floating;
            if(args[0].items[i].exact_integer&&all_exact){char text[32];char *next=big_add(exact_total,integer_text(args[0].items[i],text));free(exact_total);exact_total=next;if(!exact_total){fault(r,"out of memory");break;}}
            else all_exact=0;
        }
        if (!r->error&&all_exact)result=big_result(exact_total);else{free(exact_total);if(!r->error){result = number_value(total); result.floating = floating;}}
    } else if (!strcmp(name, "is_number") || !strcmp(name, "is_boolean") ||
               !strcmp(name, "is_string") || !strcmp(name, "is_list") ||
               !strcmp(name, "is_object") || !strcmp(name, "is_bytes") ||
               !strcmp(name, "is_datetime") || !strcmp(name, "is_duration") ||
               !strcmp(name, "is_secret")) {
        ValueKind expected = V_EMPTY;
        if (!strcmp(name, "is_number")) expected = V_NUMBER;
        else if (!strcmp(name, "is_boolean")) expected = V_BOOL;
        else if (!strcmp(name, "is_string")) expected = V_STRING;
        else if (!strcmp(name, "is_list")) expected = V_LIST;
        else if (!strcmp(name, "is_object")) expected = V_OBJECT;
        else if (!strcmp(name, "is_bytes")) expected = V_BYTES;
        else if (!strcmp(name, "is_duration")) expected = V_DURATION;
        else if (!strcmp(name, "is_datetime")) expected = V_DATETIME;
        result = bool_value(expected != V_EMPTY && args[0].kind == expected);
    } else if (!strcmp(name, "type") || !strcmp(name, "type_of")) {
        result = string_value(args[0].retained_type?args[0].retained_type:scalar_kind_type(args[0].kind));
    } else if (!strcmp(name, "object_get") || !strcmp(name, "object_has") ||
               !strcmp(name, "object_set") || !strcmp(name, "object_remove")) {
        if (args[0].kind != V_OBJECT || args[1].kind != V_STRING) { fault(r, "object and string key required"); goto done; }
        size_t found = args[0].count;
        for (size_t i = 0; i < args[0].count; i++)
            if (strlen(args[0].keys[i]) == args[1].string_length &&
                !memcmp(args[0].keys[i], args[1].string, args[1].string_length)) { found = i; break; }
        if (!strcmp(name, "object_has")) result = bool_value(found < args[0].count);
        else if (!strcmp(name, "object_get")) {
            if (found == args[0].count) fault(r, "missing object field");
            else result = clone_value(args[0].items[found]);
        } else if (!strcmp(name, "object_remove")) {
            if (found == args[0].count) { fault(r, "missing object field"); goto done; }
            result.kind = V_OBJECT; result.count = args[0].count - 1;
            result.items = calloc(result.count ? result.count : 1, sizeof(*result.items));
            result.keys = calloc(result.count ? result.count : 1, sizeof(*result.keys));
            if (!result.items || !result.keys) { fault(r, "out of memory"); goto done; }
            for (size_t i = 0, j = 0; i < args[0].count; i++) if (i != found) {
                result.keys[j] = copy_text(args[0].keys[i]); result.items[j++] = clone_value(args[0].items[i]);
            }
        } else {
            Value replacement=clone_value(args[2]);
            if(is_emptys_marker(replacement)){
                if(found==args[0].count||
                   (args[0].items[found].kind!=V_LIST&&args[0].items[found].kind!=V_OBJECT)){
                    free_value(replacement);fault(r,"EMPTYS requires container");goto done;}
                free_value(replacement);replacement=clone_value(args[0].items[found]);clear_effective_values(&replacement);
            }else if(replacement.kind==V_EMPTY){
                if(found==args[0].count){free_value(replacement);fault(r,"untyped EMPTY");goto done;}
                char *type=value_type_text(args[0].items[found]);
                if(!type){free_value(replacement);fault(r,"untyped EMPTY");goto done;}
                free(replacement.retained_type);replacement.retained_type=type;
            }else if(found<args[0].count&&args[0].items[found].kind==V_EMPTY&&args[0].items[found].retained_type){
                if(!value_matches_type(replacement,args[0].items[found].retained_type)){
                    free_value(replacement);fault(r,"object field type cannot change");goto done;}
            }else if(found<args[0].count&&args[0].items[found].kind==V_EMPTY){
                /* A JSON null field adopts its type at the first concrete update. */
            }else if (found < args[0].count && args[0].items[found].kind != replacement.kind) {
                free_value(replacement);fault(r, "object field type cannot change"); goto done;
            }
            result.kind = V_OBJECT; result.count = args[0].count + (found == args[0].count);
            result.items = calloc(result.count, sizeof(*result.items)); result.keys = calloc(result.count, sizeof(*result.keys));
            if (!result.items || !result.keys) { fault(r, "out of memory"); goto done; }
            for (size_t i = 0; i < args[0].count; i++) {
                result.keys[i] = copy_text(args[0].keys[i]);
                result.items[i] = clone_value(i == found ? replacement : args[0].items[i]);
            }
            if (found == args[0].count) {
                result.keys[found] = copy_text(args[1].string);
                result.items[found] = clone_value(replacement);
            }
            free_value(replacement);
        }
    } else if (!strcmp(name, "object_keys") || !strcmp(name, "object_values")) {
        if (args[0].kind != V_OBJECT) { fault(r, "object required"); goto done; }
        size_t *order = calloc(args[0].count ? args[0].count : 1, sizeof(*order));
        if (!order) { fault(r, "out of memory"); goto done; }
        for (size_t i = 0; i < args[0].count; i++) {
            order[i] = i;
            for (size_t j = i; j && strcmp(args[0].keys[order[j - 1]], args[0].keys[order[j]]) > 0; j--) {
                size_t swap = order[j - 1]; order[j - 1] = order[j]; order[j] = swap;
            }
        }
        result.kind = V_LIST; result.count = args[0].count;
        result.items = calloc(result.count ? result.count : 1, sizeof(*result.items));
        if (!result.items) fault(r, "out of memory");
        else for (size_t i = 0; i < result.count; i++)
            result.items[i] = !strcmp(name, "object_keys") ? string_value(args[0].keys[order[i]]) :
                              clone_value(args[0].items[order[i]]);
        free(order);
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
        const char *encoding=bytes_encoding(r,e,args);
        if(!encoding)goto done;
        if (!strcmp(name, "bytes_from_string")) {
            if (args[0].kind != V_STRING) fault(r, "string required");
            else result=encode_bytes(r,args[0],encoding);
        } else {
            if (args[0].kind != V_BYTES) fault(r, "bytes required");
            else result=decode_bytes(r,args[0],encoding);
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
        if(args[0].kind!=V_BYTES||args[1].kind!=V_NUMBER||args[1].floating||floor(args[1].number)!=args[1].number)fault(r,"bytes index type invalid");
        else if(args[1].number<0||args[1].number>=(double)args[0].string_length)fault(r,"invalid bytes index");
        else result = number_value((unsigned char)args[0].string[(size_t)args[1].number]);
    } else if (!strcmp(name, "slice_bytes")) {
        if(args[0].kind!=V_BYTES||args[1].kind!=V_NUMBER||args[2].kind!=V_NUMBER||args[1].floating||args[2].floating||floor(args[1].number)!=args[1].number||floor(args[2].number)!=args[2].number)fault(r,"bytes index type invalid");
        else if(args[1].number<0||args[2].number<args[1].number||args[2].number>(double)args[0].string_length)fault(r,"invalid bytes range");
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
    } else if (!strcmp(name, "glob")) {
        if (!r->discover_paths) { fault(r, "capability denied"); goto done; }
        if (args[0].kind != V_STRING || !args[0].string_length ||
            strlen(args[0].string) != args[0].string_length) { fault(r, "glob pattern must be a string"); goto done; }
        const char *pattern = args[0].string;
        if (pattern[0] == '/' || pattern[0] == '\\' || (pattern[0] && pattern[1] == ':')) {
            fault(r, "invalid glob pattern"); goto done;
        }
        for (const char *part=pattern; *part;) {
            const char *end=part; while(*end && *end!='/' && *end!='\\') end++;
            if (end-part==2 && part[0]=='.' && part[1]=='.') { fault(r,"invalid glob pattern"); break; }
            part=*end?end+1:end;
        }
        if (r->error) goto done;
        char *normalized=copy_text(pattern); if(!normalized){fault(r,"out of memory");goto done;}
        for(char *p=normalized;*p;p++)if(*p=='\\')*p='/';
        result.kind=V_LIST;
        if(!collect_glob(r,".",normalized,&result,0)) fault(r,"glob error");
        else qsort(result.items,result.count,sizeof(*result.items),compare_string_values);
        free(normalized);
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
        if(args[0].kind==V_EMPTY){fault(r,"EMPTY value cannot be used");goto done;}
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
            if(args[0].big_integer)result=string_value(args[0].big_integer);
            else {char text[64]; format_number(text, sizeof(text), args[0]); result = string_value(text);}
        } else fault(r, "cannot convert to string");
    } else if (!strcmp(name, "number")) {
        if (args[0].kind == V_NUMBER) result = clone_value(args[0]);
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
            else if(strchr(text,'.'))result=floating_value(strtod(text,NULL));
            else result=integer_text_value(text);
        } else fault(r, "cannot convert to number");
    } else if (!strcmp(name, "boolean")) {
        if (args[0].kind == V_BOOL) result = args[0];
        else if (args[0].kind == V_STRING && args[0].string_length == 4 && !memcmp(args[0].string, "true", 4)) result = bool_value(1);
        else if (args[0].kind == V_STRING && args[0].string_length == 5 && !memcmp(args[0].string, "false", 5)) result = bool_value(0);
        else fault(r, "cannot convert to boolean");
    }
done:
    free_value(callback_owner);
    for (size_t i = 0; i < e->argc; i++) free_value(args[i]);
    free(args);
    return result;
}
static Value call(Runtime *r, Frame *frame, Expr *e) {
    if (builtin_name(e->text)) return builtin_call(r, frame, e);
    for(size_t i=0;i<r->program.count;i++)if(r->program.items[i]->kind==14&&!strcmp(r->program.items[i]->name,e->text)){
        if(e->argc!=1||e->arg_names[0]){fault(r,"wrong argument count");return empty_value();}
        Value message=evaluate(r,frame,e->args[0]);if(message.kind!=V_STRING){free_value(message);fault(r,"error message must be string");return empty_value();}
        Value result=error_value(e->text,message);free_value(message);return result;
    }
    for(size_t i=0;i<e->argc;i++)if(e->arg_names[i]){fault(r,"wrong argument count");return empty_value();}
    Value *arguments = calloc(e->argc ? e->argc : 1, sizeof(*arguments));
    if (!arguments) { fault(r, "out of memory"); return empty_value(); }
    for (size_t i = 0; i < e->argc && !r->error; i++) {
        arguments[i] = evaluate(r, frame, e->args[i]);
    }
    Value result = r->error ? empty_value() : invoke_named(r, e->text, arguments, e->argc);
    for (size_t i = 0; i < e->argc; i++) free_value(arguments[i]);
    free(arguments); return result;
}
static int value_is_emptys(Value value) {
    if(value.kind!=V_LIST&&value.kind!=V_OBJECT&&value.kind!=V_EXEC_RESULT)return 0;
    for(size_t i=0;i<value.count;i++)
        if(value.items[i].kind!=V_EMPTY&&!value_is_emptys(value.items[i]))return 0;
    return 1;
}
static Value evaluate_inner(Runtime *r, Frame *frame, Expr *e) {
    if (!e || r->error) return empty_value();
    if (e->kind == 0) return clone_value(e->literal);
    if (e->kind == 1) {
        Binding *b = lookup(frame, e->text);
        if (!b) { fault(r, "undefined variable"); return empty_value(); }
        return clone_value(b->value);
    }
    if(e->kind==9){
        Value value=evaluate(r,frame,e->left);int state=!strcmp(e->text,"EMPTY")?value.kind==V_EMPTY:value_is_emptys(value);
        free_value(value);return bool_value(e->literal.boolean?!state:state);
    }
    if (e->kind == 5) {
        Value list = empty_value(); list.kind = V_LIST; list.count = e->argc;
        list.items = calloc(e->argc ? e->argc : 1, sizeof(*list.items));
        if (!list.items) { fault(r, "out of memory"); return empty_value(); }
        char *element_type=NULL;
        for (size_t i = 0; i < e->argc && !r->error; i++) {
            list.items[i] = evaluate(r, frame, e->args[i]);
            char *current=value_type_text(list.items[i]);
            if(current){
                if(element_type&&strcmp(element_type,current))fault(r,"list elements must have the same type");
                else if(!element_type)element_type=copy_text(current);
            }
            free(current);
        }
        if(!r->error&&element_type)for(size_t i=0;i<list.count;i++)
            if(list.items[i].kind==V_EMPTY&&!list.items[i].retained_type)list.items[i].retained_type=copy_text(element_type);
        free(element_type);
        if (r->error) { free_value(list); return empty_value(); }
        return list;
    }
    if (e->kind == 6) {
        Value target = evaluate(r, frame, e->left);
        Value index = evaluate(r, frame, e->right);
        Value result = empty_value();
        if(target.kind!=V_LIST)fault_at(r,"index target requires list",e->line,e->column);
        else if(index.kind!=V_NUMBER||index.floating||index.number<0)fault_at(r,"list index type invalid",e->right->line,e->right->column);
        else if(index.number >= (double)target.count)fault_at(r,"list index out of range or invalid",e->right->line,e->right->column);
        else result = clone_value(target.items[(size_t)index.number]);
        free_value(target); free_value(index); return result;
    }
    if (e->kind == 7) {
        Value object = evaluate(r, frame, e->left);
        Value result = empty_value();
        if(object.kind==V_NAMESPACE){ModuleResource *module=object.external;
            if(!module_exported(module,e->text,0)){fault(r,"private or missing export");}
            else {Binding *binding=lookup(&module->runtime.global,e->text);if(binding)result=clone_value(binding->value);else fault(r,"function value is not supported here");}
        }
        else if(object.kind==V_REGEX){
            if(strcmp(e->text,"text")&&strcmp(e->text,"start")&&strcmp(e->text,"end"))fault(r,"member access requires object");
            else {Value *member=object_field(&object,e->text);if(member)result=clone_value(*member);else fault(r,"member access requires object");}
        }
        else if (object.kind != V_OBJECT && object.kind != V_EXEC_RESULT) fault(r, "member access requires object");
        else {
            if(!fixed_object_member(&object,e->text)){fault(r,"missing object member");free_value(object);return result;}
            size_t i = 0;
            for (; i < object.count; i++) if (strcmp(object.keys[i], e->text) == 0) break;
            if (i == object.count) fault(r, "missing object member");
            else result = clone_value(object.items[i]);
        }
        free_value(object); return result;
    }
    if(e->kind==8){
        Value target=evaluate(r,frame,e->left),result=empty_value();
        if(target.kind==V_REGEX){
            Value *arguments=calloc(e->argc?e->argc:1,sizeof(*arguments));if(!arguments){fault(r,"out of memory");free_value(target);return result;}
            for(size_t i=0;i<e->argc&&!r->error;i++)arguments[i]=evaluate(r,frame,e->args[i]);
            if(!r->error&&strcmp(e->text,"group"))fault(r,"unknown regex member method");
            else if(!r->error&&(e->argc!=1||e->arg_names[0]))fault(r,"wrong argument count");
            else if(!r->error&&(arguments[0].kind!=V_NUMBER||!arguments[0].exact_integer||arguments[0].big_integer||arguments[0].integer<0))fault(r,"invalid unary operand");
            else if(!r->error){Value *text=object_field(&target,"text"),*groups=object_field(&target,"groups");size_t index=(size_t)arguments[0].integer;
                if(!text||!groups||index>groups->count)fault(r,"regex group out of range");else result=clone_value(index?groups->items[index-1]:*text);}
            for(size_t i=0;i<e->argc;i++)free_value(arguments[i]);free(arguments);free_value(target);return result;
        }
        if(target.kind!=V_NAMESPACE||!target.external){fault(r,"namespace required");free_value(target);return result;}
        ModuleResource *module=target.external;if(!module_exported(module,e->text,1)){fault(r,"private or missing export");free_value(target);return result;}
        Value *arguments=calloc(e->argc?e->argc:1,sizeof(*arguments));if(!arguments){fault(r,"out of memory");free_value(target);return result;}
        for(size_t i=0;i<e->argc&&!r->error;i++)arguments[i]=evaluate(r,frame,e->args[i]);
        Runtime *child=&module->runtime;child->output=r->output;child->errors=r->errors;child->handler_depth=r->handler_depth;
        Stmt *function=find_function(child,e->text);
        if(!r->error&&function)result=invoke_named(child,e->text,arguments,e->argc);
        else if(!r->error){if(e->argc!=1||arguments[0].kind!=V_STRING)fault(r,"wrong argument count");else result=error_value(e->text,arguments[0]);}
        if(child->error){r->error=1;r->message=child->message;snprintf(r->error_code,sizeof(r->error_code),"%s",child->error_code);child->error=0;}
        if(child->throwing){r->throwing=1;free_value(r->thrown);r->thrown=clone_value(child->thrown);snprintf(r->thrown_code,sizeof(r->thrown_code),"%s",child->thrown_code);r->thrown_line=child->thrown_line;r->thrown_column=child->thrown_column;child->throwing=0;free_value(child->thrown);child->thrown=empty_value();}
        for(size_t i=0;i<e->argc;i++)free_value(arguments[i]);free(arguments);free_value(target);return result;
    }
    if (e->kind == 4) return call(r, frame, e);
    if (e->kind == 2) {
        Value right = evaluate(r, frame, e->right);
        Value result = empty_value();
        if(right.kind==V_EMPTY)fault(r,"EMPTY value cannot be used");
        else if (!strcmp(e->text, "MINUS") && right.kind == V_NUMBER) {
            if(right.exact_integer){char buffer[32];result=big_result(big_negate(integer_text(right,buffer)));}
            else {result=number_value(-right.number);result.floating=right.floating;}
        }
        else if ((!strcmp(e->text, "NOT") || !strcmp(e->text, "BANG")) && right.kind == V_BOOL) result = bool_value(!right.boolean);
        else fault(r, "invalid unary operand");
        free_value(right); return result;
    }
    Value left = evaluate(r, frame, e->left);
    if (r->error) { free_value(left); return empty_value(); }
    if(!strcmp(e->text,"EMPTY_COALESCE")){
        if(left.kind!=V_EMPTY)return left;
        free_value(left);return evaluate(r,frame,e->right);
    }
    if(left.kind==V_EMPTY){fault(r,"EMPTY value cannot be used");free_value(left);return empty_value();}
    if(!strcmp(e->text,"AND")||!strcmp(e->text,"OR")){
        if(left.kind!=V_BOOL){fault_at(r,"incompatible operand types",e->left->line,e->left->column);free_value(left);return empty_value();}
        if(!strcmp(e->text,"AND")&&!left.boolean){free_value(left);return bool_value(0);}
        if(!strcmp(e->text,"OR")&&left.boolean){free_value(left);return bool_value(1);}
        free_value(left);Value logical_right=evaluate(r,frame,e->right);
        if(r->error){free_value(logical_right);return empty_value();}
        if(logical_right.kind==V_EMPTY)fault_at(r,"EMPTY value cannot be used",e->right->line,e->right->column);
        else if(logical_right.kind!=V_BOOL)fault_at(r,"incompatible operand types",e->right->line,e->right->column);
        Value logical_result=r->error?empty_value():bool_value(logical_right.boolean);free_value(logical_right);return logical_result;
    }
    Value right = evaluate(r, frame, e->right);
    if (r->error) { free_value(left); free_value(right); return empty_value(); }
    if(right.kind==V_EMPTY){fault(r,"EMPTY value cannot be used");free_value(left);free_value(right);return empty_value();}
    Value result = empty_value();
    const char *op = e->text;
    if(!strcmp(op,"IN")||!strcmp(op,"NOT_IN")){
        int found=0,valid=1;
        if(right.kind==V_STRING&&left.kind==V_STRING){
            if(!left.string_length)found=1;else for(size_t i=0;i+left.string_length<=right.string_length;i++)if(!memcmp(right.string+i,left.string,left.string_length)){found=1;break;}
        }else if(right.kind==V_LIST){
            for(size_t i=0;i<right.count;i++){if(right.items[i].kind!=left.kind){valid=0;break;}if(same_value(left,right.items[i])){found=1;break;}}
        }else if(right.kind==V_OBJECT&&left.kind==V_STRING){
            for(size_t i=0;i<right.count;i++)if(strlen(right.keys[i])==left.string_length&&!memcmp(right.keys[i],left.string,left.string_length)){found=1;break;}
        }else if(right.kind==V_BYTES&&left.kind==V_NUMBER&&!left.floating&&left.number>=0&&left.number<=255){
            found=memchr(right.string,(unsigned char)left.number,right.string_length)!=NULL;
        }else if(right.kind==V_BYTES&&left.kind==V_BYTES){
            if(!left.string_length)found=1;else for(size_t i=0;i+left.string_length<=right.string_length;i++)if(!memcmp(right.string+i,left.string,left.string_length)){found=1;break;}
        }else valid=0;
        if(!valid)fault(r,"incompatible operand types");else result=bool_value(!strcmp(op,"NOT_IN")?!found:found);
    }else if(!strcmp(op,"PLUS")&&left.kind==V_LIST&&right.kind==V_LIST){
        char *a=value_type_text(left),*b=value_type_text(right);
        if(a&&b&&strcmp(a,b))fault(r,"incompatible operand types");
        else{result.kind=V_LIST;result.count=left.count+right.count;result.items=calloc(result.count?result.count:1,sizeof(*result.items));
            if(!result.items)fault(r,"out of memory");else{for(size_t i=0;i<left.count;i++)result.items[i]=clone_value(left.items[i]);for(size_t i=0;i<right.count;i++)result.items[left.count+i]=clone_value(right.items[i]);}}
        free(a);free(b);
    } else if (!strcmp(op, "PLUS") && left.kind == V_STRING && right.kind == V_STRING) {
        result.kind = V_STRING; result.string_length = left.string_length + right.string_length;
        result.string = malloc(result.string_length + 1);
        if (result.string) {
            memcpy(result.string, left.string, left.string_length);
            memcpy(result.string + left.string_length, right.string, right.string_length);
            result.string[result.string_length] = 0;
        }
    } else if (left.kind == V_DATETIME && right.kind == V_DURATION &&
               (!strcmp(op,"PLUS") || !strcmp(op,"MINUS"))) {
        int64_t delta = !strcmp(op,"PLUS") ? right.integer : -right.integer;
        if ((delta>0 && left.integer>INT64_MAX-delta) || (delta<0 && left.integer<INT64_MIN-delta)) fault(r,"datetime overflow");
        else result=datetime_epoch_value(left.integer+delta,left.offset_minutes);
    } else if (left.kind == V_DURATION && right.kind == V_DATETIME && !strcmp(op,"PLUS")) {
        if ((left.integer>0 && right.integer>INT64_MAX-left.integer) || (left.integer<0 && right.integer<INT64_MIN-left.integer)) fault(r,"datetime overflow");
        else result=datetime_epoch_value(right.integer+left.integer,right.offset_minutes);
    } else if (left.kind == V_DATETIME && right.kind == V_DATETIME) {
        if (!strcmp(op,"MINUS")) result=duration_value(left.integer-right.integer);
        else if (!strcmp(op,"LESS")) result=bool_value(left.integer<right.integer);
        else if (!strcmp(op,"LESS_EQUAL")) result=bool_value(left.integer<=right.integer);
        else if (!strcmp(op,"GREATER")) result=bool_value(left.integer>right.integer);
        else if (!strcmp(op,"GREATER_EQUAL")) result=bool_value(left.integer>=right.integer);
        else if (!strcmp(op,"EQUAL_EQUAL")) result=bool_value(left.integer==right.integer);
        else if (!strcmp(op,"BANG_EQUAL")) result=bool_value(left.integer!=right.integer);
        else fault(r,"invalid datetime operation");
    } else if (left.kind == V_DURATION && right.kind == V_DURATION) {
        if (!strcmp(op, "PLUS") || !strcmp(op, "MINUS")) {
            int64_t b = !strcmp(op, "PLUS") ? right.integer : -right.integer;
            if ((b > 0 && left.integer > INT64_MAX - b) || (b < 0 && left.integer < INT64_MIN - b))
                fault(r, "duration overflow");
            else result = duration_value(left.integer + b);
        } else if (!strcmp(op, "SLASH") && right.integer != 0)
            result = floating_value((double)left.integer / (double)right.integer);
        else if (!strcmp(op, "LESS")) result = bool_value(left.integer < right.integer);
        else if (!strcmp(op, "LESS_EQUAL")) result = bool_value(left.integer <= right.integer);
        else if (!strcmp(op, "GREATER")) result = bool_value(left.integer > right.integer);
        else if (!strcmp(op, "GREATER_EQUAL")) result = bool_value(left.integer >= right.integer);
        else if (!strcmp(op, "EQUAL_EQUAL")) result = bool_value(left.integer == right.integer);
        else if (!strcmp(op, "BANG_EQUAL")) result = bool_value(left.integer != right.integer);
        else fault(r, "invalid duration operation");
    } else if ((left.kind == V_DURATION && right.kind == V_NUMBER) ||
               (left.kind == V_NUMBER && right.kind == V_DURATION && !strcmp(op, "STAR"))) {
        Value duration = left.kind == V_DURATION ? left : right;
        Value scalar = left.kind == V_NUMBER ? left : right;
        if (!strcmp(op, "SLASH") && scalar.number == 0){
            char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
            snprintf(description,sizeof(description),"Operator '/' cannot use zero as its right operand.");
            fault_detail_at(r,"division by zero","Division by zero",description,"0",e->line,e->column);
        }
        else {
            long double scaled = !strcmp(op, "SLASH") ? (long double)duration.integer / scalar.number :
                                 (long double)duration.integer * scalar.number;
            if (!isfinite((double)scaled) || floorl(scaled) != scaled || scaled < INT64_MIN || scaled > INT64_MAX)
                fault(r, "duration precision or range error");
            else result = duration_value((int64_t)scaled);
        }
    } else if (left.kind == V_NUMBER && right.kind == V_NUMBER) {
        double a = left.number, b = right.number;
        if(left.exact_integer&&right.exact_integer){char xb[32],yb[32];const char *x=integer_text(left,xb),*y=integer_text(right,yb);int comparison=big_compare(x,y);
            if((!strcmp(op,"SLASH")||!strcmp(op,"FLOOR_DIV")||!strcmp(op,"PERCENT"))&&!strcmp(y,"0")){
                char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                snprintf(description,sizeof(description),"Operator '%s' cannot use zero as its right operand.",!strcmp(op,"SLASH")?"/":!strcmp(op,"FLOOR_DIV")?"//":"%%");
                fault_detail_at(r,"division by zero","Division by zero",description,"0",e->line,e->column);
            }
            else if(!strcmp(op,"PLUS"))result=big_result(big_add(x,y));
            else if(!strcmp(op,"MINUS")){char *negative=big_negate(y),*sum=negative?big_add(x,negative):NULL;free(negative);result=big_result(sum);}
            else if(!strcmp(op,"STAR"))result=big_result(big_multiply(x,y));
            else if(!strcmp(op,"SLASH"))result=floating_value(strtod(x,NULL)/strtod(y,NULL));
            else if(!strcmp(op,"FLOOR_DIV")||!strcmp(op,"PERCENT")){char *quotient=NULL,*remainder=NULL;if(!big_divmod(x,y,&quotient,&remainder))fault(r,"numeric domain error");else if(!strcmp(op,"FLOOR_DIV")){result=big_result(quotient);free(remainder);}else{result=big_result(remainder);free(quotient);}}
            else if(!strcmp(op,"POWER")){if(*y=='-')result=floating_value(pow(strtod(x,NULL),strtod(y,NULL)));else if(right.big_integer)fault(r,"numeric domain error");else if(!big_power_within_limit(x,(uint64_t)right.integer))fault(r,"exact power size limit");else result=big_result(big_power(x,(uint64_t)right.integer));}
            else if(!strcmp(op,"LESS"))result=bool_value(comparison<0);else if(!strcmp(op,"LESS_EQUAL"))result=bool_value(comparison<=0);
            else if(!strcmp(op,"GREATER"))result=bool_value(comparison>0);else if(!strcmp(op,"GREATER_EQUAL"))result=bool_value(comparison>=0);
            else if(!strcmp(op,"EQUAL_EQUAL"))result=bool_value(comparison==0);else if(!strcmp(op,"BANG_EQUAL"))result=bool_value(comparison!=0);
            else fault(r,"invalid numeric operation");
            if(result.kind==V_EMPTY&&!r->error)fault(r,"numeric domain error");
        }
        else if ((!strcmp(op,"SLASH")||!strcmp(op,"FLOOR_DIV")||!strcmp(op,"PERCENT"))&&b==0){
            char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
            snprintf(description,sizeof(description),"Operator '%s' cannot use zero as its right operand.",!strcmp(op,"SLASH")?"/":!strcmp(op,"FLOOR_DIV")?"//":"%%");
            fault_detail_at(r,"division by zero","Division by zero",description,"0",e->line,e->column);
        }
        else if (!strcmp(op, "PLUS")) result = number_value(a + b);
        else if (!strcmp(op, "MINUS")) result = number_value(a - b);
        else if (!strcmp(op, "STAR")) result = number_value(a * b);
        else if (!strcmp(op, "SLASH") && b != 0) result = floating_value(a / b);
        else if (!strcmp(op, "FLOOR_DIV") && b != 0) {
            if(left.floating||right.floating)fault(r,"integer operands required");else result=number_value(floor(a/b));
        }
        else if (!strcmp(op, "PERCENT") && b != 0) {
            result = number_value(a - floor(a / b) * b); result.floating = left.floating || right.floating;
        }
        else if (!strcmp(op, "POWER")) {double powered=pow(a,b);if(!isfinite(powered))fault(r,"numeric domain error");else result=(left.floating||right.floating||b<0)?floating_value(powered):number_value(powered);}
        else if (!strcmp(op, "LESS")) result = bool_value(number_compare(left,right)<0);
        else if (!strcmp(op, "LESS_EQUAL")) result = bool_value(number_compare(left,right)<=0);
        else if (!strcmp(op, "GREATER")) result = bool_value(number_compare(left,right)>0);
        else if (!strcmp(op, "GREATER_EQUAL")) result = bool_value(number_compare(left,right)>=0);
        else if (!strcmp(op, "EQUAL_EQUAL")) result = bool_value(number_compare(left,right)==0);
        else if (!strcmp(op, "BANG_EQUAL")) result = bool_value(number_compare(left,right)!=0);
        else fault(r, "invalid numeric operation");
        if (!(left.exact_integer&&right.exact_integer)&&result.kind == V_NUMBER && (!strcmp(op, "PLUS") || !strcmp(op, "MINUS") || !strcmp(op, "STAR")))
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
    } else if (left.kind == right.kind && (!strcmp(op,"EQUAL_EQUAL")||!strcmp(op,"BANG_EQUAL"))) {
        int equal=same_value(left,right);result=bool_value(!strcmp(op,"EQUAL_EQUAL")?equal:!equal);
    } else fault(r, "incompatible operand types");
    free_value(left); free_value(right); return result;
}

static void print_value(FILE *out, Value v) {
    if (v.kind == V_NUMBER) { if(v.big_integer)fputs(v.big_integer,out);else{char text[64];format_number(text,sizeof(text),v);fputs(text,out);} }
    else if (v.kind == V_STRING && v.string) fwrite(v.string, 1, v.string_length, out);
    else if ((v.kind == V_TIMEZONE || v.kind == V_LOCAL_DATETIME || v.kind == V_DATETIME) && v.string)
        fwrite(v.string, 1, v.string_length, out);
    else if (v.kind == V_BOOL) fputs(v.boolean ? "true" : "false", out);
    else if (v.kind == V_DURATION) { char text[96]; format_duration_value(text, sizeof(text), v.integer); fputs(text, out); }
    else if (v.kind == V_BYTES) {
        if(v.retained_type&&!strcmp(v.retained_type,"secret"))fputs("[REDACTED]",out);
        else {fputs("0x", out);for (size_t i = 0; i < v.string_length; i++) fprintf(out, "%02x", (unsigned char)v.string[i]);}
    }
    else if (v.kind == V_DB) fputs("db_connection(database=[REDACTED])",out);
    else if(v.kind==V_NAMESPACE)fputs("namespace",out);
    else if (v.kind == V_LIST) {
        fputc('[', out);
        for (size_t i = 0; i < v.count; i++) {
            if (i) fputs(", ", out);
            print_value(out, v.items[i]);
        }
        fputc(']', out);
    }
    else if (v.kind == V_ERROR) {
        Value *category=object_field(&v,"category"),*message=object_field(&v,"message");
        if(category&&message){fwrite(category->string,1,category->string_length,out);fputs(": ",out);fwrite(message->string,1,message->string_length,out);}
        else fputs("error",out);
    }
    else if (v.kind == V_OBJECT || v.kind == V_EXEC_RESULT) {
        fputs("object:", out);
        for (size_t i = 0; i < v.count; i++) {
            if (i) fputs(", ", out);
            fputs(v.keys[i], out); fputc('=', out); print_value(out, v.items[i]);
        }
    }
    else fputs("EMPTY", out);
}
static int error_matches(const char *requested,const char *actual) {
    if(!strcmp(requested,actual)||!strcmp(requested,"any")||!strcmp(requested,"runtime_error"))return 1;
    static const char *pairs[][2]={
        {"oauth_error","auth_error"},{"secret_error","auth_error"},{"crypto_authentication_error","crypto_error"},
        {"mail_address_error","mail_error"},{"mail_attachment_error","mail_error"},{"mail_provider_error","mail_error"},
        {"mail_connection_error","mail_error"},{"mail_authentication_error","mail_error"},{"mail_send_error","mail_error"},
        {"yaml_parse_error","yaml_error"},{"yaml_encode_error","yaml_error"},{"yaml_type_error","yaml_error"},{"yaml_limit_error","yaml_error"},
        {"xml_parse_error","xml_error"},{"xml_model_error","xml_error"},{"xml_security_error","xml_error"},{"xml_limit_error","xml_error"},
        {"xml_path_error","xml_error"},{"xml_escape_error","xml_error"},{"network_dns_error","network_error"},
        {"network_interface_error","network_error"},{"network_connection_error","network_error"},{"network_timeout_error","network_error"},
        {"network_limit_error","network_error"},{"network_closed_error","network_error"},{"network_protocol_error","network_error"},
        {"network_operation_unavailable","network_error"},{"network_address_error","network_error"},
        {"network_service_error","network_error"},{"dhcp_server_error","network_service_error"},{"dns_server_error","network_service_error"},
        {"wifi_access_point_error","network_service_error"}
    };
    const char *current=actual;
    for(size_t depth=0;depth<4;depth++){const char *parent=NULL;for(size_t i=0;i<sizeof(pairs)/sizeof(*pairs);i++)if(!strcmp(current,pairs[i][0])){parent=pairs[i][1];break;}
        if(!parent)return 0;if(!strcmp(requested,parent))return 1;current=parent;}return 0;
}
static const char *runtime_error_category(const char *code,const char *message) {
    int number=code&&code[0]=='E'?atoi(code+1):0;
    if(number==201||number==203||number==208)return "type_error";
    if(number==301)return "value_error";if(number==302)return "index_error";
    if(number>=830&&number<=839)return "regex_error";if(number>=840&&number<=849)return "glob_error";
    if(number>=860&&number<=869)return "argument_error";if(number>=701&&number<=709)return "import_error";
    if(number==720||number==721||number==870||number==979)return "permission_error";
    if(number>=722&&number<=729)return "io_error";if(number>=740&&number<=749)return "parse_error";
    if(number==808)return "command_error";if(number==809)return "command_timeout_error";
    if(number>=800&&number<=819)return "process_error";
    if(number==900)return "db_driver_error";if(number==901)return "db_connection_error";
    if(number==902)return "db_auth_error";if(number==903)return "db_query_error";
    if(number==904)return "db_constraint_error";if(number==905)return "db_timeout_error";if(number==907)return "db_transaction_error";
    if(number>=920&&number<=929)return message&&strstr(message,"authentication")?"crypto_authentication_error":"crypto_error";
    if(number>=930&&number<=939)return "mail_error";if(number>=940&&number<=949)return "yaml_error";
    if(number>=950&&number<=959)return "xml_error";if((number>=970&&number<=978)||(number>=980&&number<=984))return "network_error";
    return "runtime_error";
}
static int module_exported(ModuleResource *module,const char *name,int callable) {
    for(size_t i=0;i<module->runtime.program.count;i++){Stmt *s=module->runtime.program.items[i];
        if(s->name&&!strcmp(s->name,name)&&(s->kind==5||s->kind==8||s->kind==14))
            return !callable||s->kind==5||s->kind==14;}
    return 0;
}
static ModuleResource *load_module(Runtime *parent,const char *relative) {
    size_t length=strlen(relative);if(length<5||strcmp(relative+length-4,".sep")||relative[0]=='/'||relative[0]=='\\'||
       strchr(relative,':')||strstr(relative,"../")||strstr(relative,"..\\")||!strcmp(relative,"..")){fault(parent,"invalid import path");return NULL;}
    const char *script=parent->script_path;const char *slash=script?strrchr(script,'/'):NULL,*back=script?strrchr(script,'\\'):NULL;
    if(back&&(!slash||back>slash))slash=back;size_t directory=slash?(size_t)(slash-script):0;
    char *path=malloc(directory+(directory?1:0)+length+1);if(!path){fault(parent,"out of memory");return NULL;}
    if(directory){memcpy(path,script,directory);path[directory]='/';memcpy(path+directory+1,relative,length+1);}else memcpy(path,relative,length+1);
    for(Runtime *ancestor=parent;ancestor;ancestor=ancestor->import_parent)if(ancestor->script_path&&!strcmp(ancestor->script_path,path)){
        free(path);fault(parent,"circular import");return NULL;}
    if(parent->module_cache)for(ModuleCache *entry=*parent->module_cache;entry;entry=entry->next)if(!strcmp(entry->path,path)){
        free(path);module_retain(entry->module);return entry->module;}
    FILE *file=fopen(path,"rb");if(!file){free(path);fault(parent,"import read error");return NULL;}
    if(fseek(file,0,SEEK_END)||ftell(file)<0){fclose(file);free(path);fault(parent,"import read error");return NULL;}long size=ftell(file);rewind(file);
    char *source=malloc((size_t)size+1);if(!source){fclose(file);free(path);fault(parent,"out of memory");return NULL;}
    size_t read=fread(source,1,(size_t)size,file);fclose(file);source[read]=0;
    ModuleResource *module=calloc(1,sizeof(*module));if(!module){free(source);free(path);fault(parent,"out of memory");return NULL;}
    module->references=1;module->path=path;Runtime *r=&module->runtime;r->output=parent->output;r->errors=parent->errors;
    r->read_files=parent->read_files;r->write_files=parent->write_files;r->discover_paths=parent->discover_paths;r->import_modules=parent->import_modules;
    r->read_environment=parent->read_environment;r->write_environment=parent->write_environment;r->script_path=module->path;
    r->command_arguments=parent->command_arguments;r->command_argument_count=parent->command_argument_count;
    r->database=parent->database;r->process=parent->process;r->host=parent->host;r->handler_depth=parent->handler_depth;r->import_parent=parent;r->module_cache=parent->module_cache;random_seed_runtime(r,0);
    if(separan_files_init(&r->files,parent->files.root)||separan_lex(source,&r->tokens)){free(source);module_release(module);fault(parent,"import parse error");return NULL;}
    free(source);r->program=parse_body(r,NULL,NULL);if(!r->error)execute_body(r,&r->global,r->program);
    if(r->throwing&&!r->error){
        free_value(parent->thrown);parent->thrown=clone_value(r->thrown);parent->throwing=1;
        snprintf(parent->thrown_code,sizeof(parent->thrown_code),"%s",r->thrown_code);
        parent->thrown_line=r->thrown_line;parent->thrown_column=r->thrown_column;
        module_release(module);return NULL;
    }
    if(r->error){module_release(module);fault(parent,"import execution error");return NULL;}
    if(parent->module_cache){ModuleCache *entry=calloc(1,sizeof(*entry));if(!entry){module_release(module);fault(parent,"out of memory");return NULL;}
        entry->path=copy_text(path);entry->module=module;module_retain(module);entry->next=*parent->module_cache;*parent->module_cache=entry;}
    return module;
}
static int database_transaction_call(Runtime *r,DatabaseResource *resource,const char *operation,int report) {
    char *response=NULL,*error_message=NULL;int status=resource->adapter.call(resource->adapter.context,resource->native,operation,"{}",&response,&error_message);
    database_release(&resource->adapter,response);database_release(&resource->adapter,error_message);
    if(status&&report)fault(r,database_status_message(status));return status==0;
}
static void assign_indexes(Runtime *r,Frame *frame,Expr *target,Value replacement) {
    size_t count=0;Expr *root=target;
    while(root&&root->kind==6){count++;root=root->left;}
    if(!root||root->kind!=1||!count){fault(r,"invalid indexed target");return;}
    Binding *binding=lookup(frame,root->text);
    if(!binding){fault(r,"undefined variable");return;}
    if(binding->constant){fault(r,"constant cannot be reassigned");return;}
    if(binding->value.kind==V_LIST&&binding->value.retained_type&&
       !strcmp(binding->value.retained_type,"__JSON_UNKNOWN_LIST__")&&replacement.kind!=V_EMPTY){
        char *element=value_type_text(replacement);
        if(element){size_t length=strlen(element)+7;char *list_type=malloc(length);
            if(list_type){snprintf(list_type,length,"list<%s>",element);retain_value_type(&binding->value,list_type);free(list_type);}
            free(element);free(binding->value.retained_type);binding->value.retained_type=NULL;}
    }
    Expr **indexes=calloc(count,sizeof(*indexes));
    if(!indexes){fault(r,"out of memory");return;}
    Expr *part=target;for(size_t i=count;i>0;i--){indexes[i-1]=part->right;part=part->left;}
    Value *slot=&binding->value;
    for(size_t i=0;i<count&&!r->error;i++){
        Value index=evaluate(r,frame,indexes[i]);
        if(slot->kind!=V_LIST||index.kind!=V_NUMBER||index.floating||index.number<0||index.number>=(double)slot->count)
            fault(r,"list index out of range or invalid");
        else slot=&slot->items[(size_t)index.number];
        free_value(index);
    }
    free(indexes);
    if(r->error)return;
    if(replacement.kind==V_VOID){fault(r,"VOID value cannot be used");return;}
    if(is_emptys_marker(replacement)){
        if(slot->kind!=V_LIST&&slot->kind!=V_OBJECT){fault(r,"EMPTYS requires container");return;}
        clear_effective_values(slot);return;
    }
    if(replacement.kind==V_EMPTY){
        Value copy=clone_value(replacement);copy.retained_type=copy_text(slot->kind==V_EMPTY&&slot->retained_type?slot->retained_type:scalar_kind_type(slot->kind));
        free_value(*slot);*slot=copy;return;
    }
    if(slot->kind==V_EMPTY&&slot->retained_type){
        if(!value_matches_type(replacement,slot->retained_type)){fault(r,"variable type cannot change");return;}
        Value copy=clone_value(replacement);free_value(*slot);*slot=copy;return;
    }
    if(slot->kind!=replacement.kind){fault(r,"variable type cannot change");return;}
    Value copy=clone_value(replacement);free_value(*slot);*slot=copy;
}
static Value evaluate(Runtime *r,Frame *frame,Expr *expression) {
    size_t old_line=r->fault_line,old_column=r->fault_column;
    if(expression&&expression->line){r->fault_line=expression->line;r->fault_column=expression->column;}
    Value result=evaluate_inner(r,frame,expression);
    r->fault_line=old_line;r->fault_column=old_column;return result;
}
static void execute_body(Runtime *r, Frame *frame, Body body) {
    int was_executing=r->executing;size_t old_line=r->fault_line,old_column=r->fault_column;r->executing=1;
    for (size_t i = 0; i < body.count && !r->error && !r->returning && !r->throwing && !r->http_returned; i++) {
        Stmt *s = body.items[i];
        if(s->line){r->fault_line=s->line;r->fault_column=s->column;}
        if (++r->steps > 1000000) { fault(r, "execution limit exceeded"); break; }
        if (s->kind == 5 || s->kind == 14 || s->kind == 20) continue;
        if(s->kind==17){
            Value connection=evaluate(r,frame,s->expr);if(r->error){free_value(connection);continue;}
            if(connection.kind!=V_DB||!connection.external){free_value(connection);fault(r,"database connection required");continue;}
            DatabaseResource *resource=connection.external;if(resource->closed){free_value(connection);fault(r,"database connection is closed");continue;}
            if(!database_transaction_call(r,resource,"db_begin",1)){free_value(connection);continue;}
            execute_body(r,frame,s->body);
            if(r->error||r->throwing)database_transaction_call(r,resource,"db_rollback",0);
            else database_transaction_call(r,resource,"db_commit",1);
            free_value(connection);continue;
        }
        if(s->kind==15){
            if(!r->import_modules){fault(r,"capability denied");continue;}
            if(!s->expr||s->expr->literal.kind!=V_STRING){fault(r,"invalid import path");continue;}
            ModuleResource *module=load_module(r,s->expr->literal.string);if(!module)continue;
            Value namespace_value=empty_value();namespace_value.kind=V_NAMESPACE;namespace_value.external=module;
            if(!bind(frame,s->name,namespace_value,1))fault(r,"cannot bind import");free_value(namespace_value);continue;
        }
        if(s->kind==12){
            r->handler_depth++;execute_body(r,frame,s->body);r->handler_depth--;
            if(r->error){const char *category=runtime_error_category(r->error_code,r->message);Value message=string_value(r->message?r->message:"runtime error");
                free_value(r->thrown);r->thrown=error_value(category,message);free_value(message);r->throwing=1;
                snprintf(r->thrown_code,sizeof(r->thrown_code),"%s",r->error_code);r->thrown_line=r->error_line;r->thrown_column=r->error_column;r->error=0;r->error_code[0]=0;}
            if(r->throwing){Value *category=object_field(&r->thrown,"category");Stmt *selected=NULL;
                for(size_t j=0;category&&j<s->other.count;j++)if(error_matches(s->other.items[j]->name,category->string)){selected=s->other.items[j];break;}
                if(selected){r->throwing=0;r->thrown_code[0]=0;free_value(r->thrown);r->thrown=empty_value();execute_body(r,frame,selected->body);}
            }
            if(s->final.count){int old_throwing=r->throwing,old_returning=r->returning;char old_code[8];size_t old_thrown_line=r->thrown_line,old_thrown_column=r->thrown_column;snprintf(old_code,sizeof(old_code),"%s",r->thrown_code);Value old_thrown=clone_value(r->thrown),old_returned=clone_value(r->returned);
                r->throwing=0;r->returning=0;free_value(r->thrown);r->thrown=empty_value();free_value(r->returned);r->returned=empty_value();
                execute_body(r,frame,s->final);
                if(!r->throwing&&!r->returning&&!r->error){r->throwing=old_throwing;r->returning=old_returning;snprintf(r->thrown_code,sizeof(r->thrown_code),"%s",old_code);r->thrown_line=old_thrown_line;r->thrown_column=old_thrown_column;r->thrown=old_thrown;r->returned=old_returned;old_thrown=empty_value();old_returned=empty_value();}
                free_value(old_thrown);free_value(old_returned);
            }continue;
        }
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
            if (values.kind != V_LIST) fault_at(r,"for requires a list",s->expr->line,s->expr->column);
            else for (size_t j = 0; j < values.count && !r->error && !r->returning; j++) {
                if (!bind(frame, s->parameters[0], values.items[j], 0)) { fault(r, "cannot assign loop variable"); break; }
                execute_body(r, frame, s->body);
            }
            free_value(values); continue;
        }
        if (s->kind == 3 || s->kind == 4) {
            do {
                Value condition = evaluate(r, frame, s->expr);
                if(condition.kind==V_EMPTY){fault(r,"EMPTY value cannot be used");free_value(condition);break;}
                if (condition.kind != V_BOOL) { fault_at(r,"condition must be boolean",s->expr->line,s->expr->column); free_value(condition); break; }
                int true_branch = condition.boolean; free_value(condition);
                if (true_branch) execute_body(r, frame, s->body);
                else if (s->kind == 3) execute_body(r, frame, s->other);
                if (!true_branch || s->kind == 3 || r->returning || r->error) break;
            } while (1);
            continue;
        }
        Value value = s->expr ? evaluate(r, frame, s->expr) : empty_value();
        if (r->error || r->throwing) { free_value(value); break; }
        if(value.kind==V_POSITION){fault(r,"position selector outside list operation");free_value(value);continue;}
        if(is_emptys_marker(value)){
            if(s->kind==19&&s->declared_type&&!strncmp(s->declared_type,"list<",5)){
                free_value(value);value=empty_value();value.kind=V_LIST;
            }else if(s->kind==0){
                Binding *binding=lookup_local(frame,s->name);
                if(!binding){fault(r,"EMPTYS requires container");free_value(value);continue;}
                if(binding->constant){fault(r,"constant cannot be reassigned");free_value(value);continue;}
                if(binding->value.kind!=V_LIST&&binding->value.kind!=V_OBJECT){fault(r,"EMPTYS requires container");free_value(value);continue;}
                clear_effective_values(&binding->value);free_value(value);continue;
            }else if(s->kind!=18){fault(r,"EMPTYS requires container");free_value(value);continue;}
        }
        if (value.kind == V_VOID && s->kind != 6) {
            const char *description=s->kind==1||s->kind==16?
                "VOID cannot be printed because it does not represent a value.":
                "VOID does not represent a value and cannot be assigned.";
            fault_detail_at(r,"VOID value cannot be used","VOID value use",description,"VOID",s->line,s->column);
            free_value(value); break;
        }
        if(value.kind==V_EMPTY&&s->kind==19&&s->constant){
            fault_detail_at(r,"EMPTY constant","EMPTY constant",
                "A constant must contain a value and cannot be initialized with EMPTY.","EMPTY",s->line,s->column);
            free_value(value);continue;
        }
        if(value.kind==V_EMPTY&&s->kind==8){
            fault_detail_at(r,"EMPTY constant","EMPTY constant",
                "A constant must contain a value and cannot be initialized with EMPTY.","EMPTY",s->line,s->column);
            free_value(value);continue;
        }
        if(s->kind==19){
            Binding *existing=lookup_local(frame,s->name);
            if(existing)fault(r,"duplicate typed declaration");
            else if(!value_matches_type(value,s->declared_type))fault(r,"variable type cannot change");
            else if(!bind_typed(frame,s->name,s->declared_type,value,s->constant))fault(r,"cannot declare or assign variable");
        } else if (s->kind == 0 || s->kind == 8) {
            Binding *existing = lookup_local(frame, s->name);
            if(value.kind==V_LIST&&value.count){
                char *inferred=value_type_text(value);
                if(!inferred&&value.retained_type&&!strcmp(value.retained_type,"__JSON_UNKNOWN_LIST__")){
                    /* External JSON may defer its element type until the first concrete slot assignment. */
                }else if(!inferred){
                    if(existing){char *expected=existing->declared_type?copy_text(existing->declared_type):value_type_text(existing->value);
                        if(expected){retain_value_type(&value,expected);free(expected);}else{fault(r,"list element type required");free_value(value);continue;}}
                    else{fault(r,"list element type required");free_value(value);continue;}
                }else free(inferred);
            }
            if(value.kind==V_EMPTY&&!existing){
                char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                snprintf(description,sizeof(description),"Variable '%s' cannot infer a type from EMPTY.",s->name?s->name:"");
                fault_detail_at(r,"untyped EMPTY","EMPTY type required",description,"EMPTY",s->line,s->column);
                free_value(value);continue;
            }
            if(value.kind==V_EMPTY&&existing&&!value.retained_type){
                value.retained_type=existing->declared_type?copy_text(existing->declared_type):value_type_text(existing->value);
                if(!value.retained_type){
                    char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                    snprintf(description,sizeof(description),"Variable '%s' cannot infer a type from EMPTY.",s->name?s->name:"");
                    fault_detail_at(r,"untyped EMPTY","EMPTY type required",description,"EMPTY",s->line,s->column);
                    free_value(value);continue;
                }
            }
            if(existing&&s->kind==8)fault(r,"duplicate typed declaration");
            else if (existing && existing->constant) fault(r, "constant cannot be reassigned");
            else if (existing && existing->declared_type && !value_matches_type(value,existing->declared_type)) fault(r,"variable type cannot change");
            else if(existing&&!existing->declared_type&&existing->value.kind==V_EMPTY&&existing->value.retained_type&&
                    !value_matches_type(value,existing->value.retained_type))fault(r,"variable type cannot change");
            else if (existing && !existing->declared_type && existing->value.kind!=V_EMPTY&&value.kind!=V_EMPTY&&existing->value.kind != value.kind) fault(r, "variable type cannot change");
            else if(existing&&!existing->declared_type&&existing->value.kind==V_LIST&&value.kind==V_LIST){char *old_type=value_type_text(existing->value),*new_type=value_type_text(value);
                if(old_type&&new_type&&strcmp(old_type,new_type))fault(r,"variable type cannot change");
                else if(!bind(frame,s->name,value,s->kind==8))fault(r,"cannot declare or assign variable");
                free(old_type);free(new_type);
            }
            else if (!bind(frame, s->name, value, s->kind == 8)) fault(r, "cannot declare or assign variable");
            else {Binding *updated=lookup_local(frame,s->name);if(updated&&updated->declared_type)retain_value_type(&updated->value,updated->declared_type);}
        } else if(s->kind==18) assign_indexes(r,frame,s->target,value);
        else if (s->kind == 1) {if(value.kind==V_EMPTY)fault(r,"EMPTY value cannot be used");else{print_value(r->output, value); fputc('\n', r->output);}}
        else if(s->kind==16){if(value.kind==V_EMPTY)fault(r,"EMPTY value cannot be used");else{print_value(r->errors,value);fputc('\n',r->errors);}}
        else if (s->kind == 2) { r->returning = 1; r->returned = clone_value(value); }
        else if(s->kind==11){if(value.kind!=V_ERROR)fault(r,"throw requires error value");else{r->throwing=1;r->thrown_line=s->line;r->thrown_column=s->column;snprintf(r->thrown_code,sizeof(r->thrown_code),"E760");free_value(r->thrown);r->thrown=clone_value(value);}}
        free_value(value);
    }
    r->executing=was_executing;r->fault_line=old_line;r->fault_column=old_column;
}

static void runtime_contents_destroy(separan_runtime *handle) {
    if(!handle)return;Runtime *r=&handle->runtime;
    free_value(r->thrown);free_value(r->returned);free_value(r->http_request);free_value(r->http_params);
    free_value(r->http_response);free_value(r->http_cookies);free_frame(&r->global);free_body(r->program);
    while(handle->module_cache){ModuleCache *next=handle->module_cache->next;free(handle->module_cache->path);
        module_release(handle->module_cache->module);free(handle->module_cache);handle->module_cache=next;}
    separan_tokens_free(&r->tokens);separan_files_free(&r->files);
}

static int valid_route_parameters(const char *path) {
    const char *segment=path;while(*segment=='/')segment++;
    while(*segment){const char *end=strchr(segment,'/');size_t length=end?(size_t)(end-segment):strlen(segment);
        if(*segment==':'){if(length==1)return 0;const char *other=path;while(other<segment){while(*other=='/')other++;const char *other_end=strchr(other,'/');size_t other_length=other_end?(size_t)(other_end-other):strlen(other);
                if(*other==':'&&other_length==length&&!memcmp(other+1,segment+1,length-1))return 0;other=other_end?other_end+1:segment;}}
        segment=end?end+1:segment+length;
    }return 1;
}
static void validate_program(Runtime *r) {
    for(size_t i=0;i<r->program.count&&!r->error;i++){Stmt *current=r->program.items[i];
    if(current->line){r->fault_line=current->line;r->fault_column=current->column;}
        if(current->kind==5){
            if(builtin_name(current->name)){
                char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                snprintf(description,sizeof(description),"Function '%s' is a built-in and cannot be redefined.",current->name);
                fault_detail_at(r,"reserved function name","Reserved function name",description,current->name,current->line,current->column);
            }else if(!strcmp(current->name,"main")&&current->parameter_count){
                char actual[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];actual[0]='\0';
                strcat(actual,"main(");
                for(size_t p=0;p<current->parameter_count;p++){if(p)strcat(actual,", ");strcat(actual,current->parameters[p]);}
                strcat(actual,")");
                snprintf(r->error_category,sizeof(r->error_category),"Invalid main function");
                snprintf(r->error_description,sizeof(r->error_description),"main must have zero parameters in v0.1.");
                snprintf(r->error_expected,sizeof(r->error_expected),"main()");
                snprintf(r->error_actual,sizeof(r->error_actual),"%s",actual);
                fault_at(r,"invalid main function",current->line,current->column);
            }
            for(size_t j=0;j<i&&!r->error;j++)if(r->program.items[j]->kind==5&&!strcmp(current->name,r->program.items[j]->name)){
                char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                snprintf(description,sizeof(description),"Function '%s' is already defined.",current->name);
                fault_detail_at(r,"duplicate function","Duplicate function",description,current->name,current->line,current->column);
            }
        }else if(current->kind==14){
            size_t name_length=strlen(current->name);if(name_length<7||strcmp(current->name+name_length-6,"_error")){
                if(!r->error){
                    snprintf(r->error_category,sizeof(r->error_category),"Invalid error name");
                    snprintf(r->error_description,sizeof(r->error_description),"Custom error names must end with '_error'.");
                    snprintf(r->error_actual,sizeof(r->error_actual),"%s",current->name?current->name:"");
                }
                fault_at(r,"invalid error name",current->name_line?current->name_line:current->line,current->name_column?current->name_column:current->column);
            }
            else if(builtin_name(current->name)||error_category_name(current->name)){
                char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                snprintf(description,sizeof(description),"Custom error name '%s' conflicts with an existing declaration or built-in.",current->name);
                fault_detail_at(r,"duplicate error name","Duplicate error name",description,current->name,
                                current->line,current->column);
            }
            for(size_t j=0;j<r->program.count&&!r->error;j++)if(r->program.items[j]->kind==5&&!strcmp(current->name,r->program.items[j]->name)){
                char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                snprintf(description,sizeof(description),"Custom error name '%s' conflicts with an existing declaration or built-in.",current->name);
                fault_detail_at(r,"error name conflicts with function","Duplicate error name",description,current->name,
                                current->line,current->column);
            }
            for(size_t j=0;j<i&&!r->error;j++)if(r->program.items[j]->kind==14&&!strcmp(current->name,r->program.items[j]->name)){
                char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                snprintf(description,sizeof(description),"Custom error name '%s' conflicts with an existing declaration or built-in.",current->name);
                fault_detail_at(r,"duplicate error name","Duplicate error name",description,current->name,
                                current->line,current->column);
            }
        }else if(current->kind==20){
            if(!valid_route_parameters(current->path))fault_at(r,"invalid route path",current->path_line?current->path_line:current->line,current->path_column?current->path_column:current->column);
            for(size_t j=0;j<i&&!r->error;j++)if(r->program.items[j]->kind==20&&!strcmp(current->method,r->program.items[j]->method)&&
                !strcmp(current->path,r->program.items[j]->path)){
                char actual[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
                snprintf(actual,sizeof(actual),"%s %s",current->method,current->path);
                fault_detail_at(r,"duplicate HTTP route","Duplicate HTTP route",
                    "HTTP method and path must be unique.",actual,current->line,current->column);
            }
        }
    }
}
static void validate_body_labels(Runtime *r,Body body,const char **labels,Stmt **openers,size_t depth) {
    for(size_t i=0;i<body.count&&!r->error;i++){Stmt *s=body.items[i];int labeled=s->kind==3||s->kind==4||s->kind==5||s->kind==7||s->kind==9||s->kind==10||s->kind==12||s->kind==17||s->kind==20;
    if(s->line){r->fault_line=s->line;r->fault_column=s->column;}
        if(labeled&&s->name){for(size_t j=0;j<depth;j++)if(!strcmp(labels[j],s->name)){
                snprintf(r->error_actual,sizeof(r->error_actual),"%s",s->name);
                if(openers[j]){r->error_related_line=openers[j]->name_line?openers[j]->name_line:openers[j]->line;r->error_related_column=openers[j]->name_column?openers[j]->name_column:openers[j]->column;}
                fault_at(r,"duplicate open label",s->name_line?s->name_line:s->line,s->name_column?s->name_column:s->column);return;}
            if(depth>=128){fault(r,"unclosed block");return;}labels[depth]=s->name;openers[depth]=s;depth++;}
        validate_body_labels(r,s->body,labels,openers,depth);
        if(s->kind==3&&s->other.count==1&&s->other.items[0]->kind==3)validate_body_labels(r,s->other.items[0]->body,labels,openers,depth);
        else validate_body_labels(r,s->other,labels,openers,depth);
        validate_body_labels(r,s->final,labels,openers,depth);
        if(labeled&&s->name)depth--;
    }
}

static int runtime_create_internal(const char *source,const separan_runtime_options *options,
                                   FILE *output,FILE *errors,int execute_top_level,
                                   separan_runtime **created,
                                   separan_runtime_diagnostic *diagnostic) {
    if(diagnostic)memset(diagnostic,0,sizeof(*diagnostic));
    if(!source||!options||!created)return 1;*created=NULL;
    separan_runtime *handle=calloc(1,sizeof(*handle));if(!handle)return 1;
    Runtime *r=&handle->runtime;r->output=output?output:stdout;r->errors=errors?errors:stderr;
    r->module_cache=&handle->module_cache;random_seed_runtime(r,0);
    r->read_files=options->read_files;r->write_files=options->write_files;
    r->discover_paths=options->discover_paths;r->import_modules=options->import_modules;
    r->read_environment=options->read_environment;r->write_environment=options->write_environment;
    r->script_path=options->script_path;r->command_arguments=options->command_arguments;
    r->command_argument_count=options->command_argument_count;r->database=options->database;
    r->process=options->process;r->host=options->host;
    if (separan_files_init(&r->files, options->root ? options->root : ".")) {
        fprintf(r->errors, "SEPARAN E721: invalid capability root\n");free(handle);return 1;
    }
    if (separan_lex(source, &r->tokens)) {
        fprintf(r->errors, "SEPARAN %s: lexer error at line %zu, column %zu\n",
                r->tokens.error_code, r->tokens.error_line, r->tokens.error_column);
        runtime_contents_destroy(handle);free(handle);return 1;
    }
    r->program=parse_body(r,NULL,NULL);if(!r->error){int old_executing=r->executing;r->executing=1;const char *labels[128];Stmt *openers[128];validate_body_labels(r,r->program,labels,openers,0);if(!r->error)validate_program(r);r->executing=old_executing;r->fault_line=0;r->fault_column=0;}
    if(!r->error&&execute_top_level)execute_body(r,&r->global,r->program);
    if(r->throwing&&!r->error){
        Value *category=object_field(&r->thrown,"category"),*message=object_field(&r->thrown,"message");
        fprintf(r->errors,"SEPARAN %s: %.*s: %.*s at line %zu, column %zu\n",
                r->thrown_code[0]?r->thrown_code:"E760",
                category?(int)category->string_length:13,category?category->string:"runtime_error",
                message?(int)message->string_length:12,message?message->string:"error thrown",
                r->thrown_line,r->thrown_column);
        runtime_contents_destroy(handle);free(handle);return 1;
    }
    if(r->error){
        if(diagnostic){
            diagnostic->line_number=r->error_line;
            diagnostic->column_number=r->error_column;
            diagnostic->related_line_number=r->error_related_line;
            diagnostic->related_column_number=r->error_related_column;
            snprintf(diagnostic->category,sizeof(diagnostic->category),"%s",r->error_category);
            snprintf(diagnostic->description,sizeof(diagnostic->description),"%s",r->error_description);
            snprintf(diagnostic->expected,sizeof(diagnostic->expected),"%s",r->error_expected);
            snprintf(diagnostic->actual,sizeof(diagnostic->actual),"%s",r->error_actual);
        }
        runtime_contents_destroy(handle);free(handle);return 1;
    }
    *created=handle;return 0;
}

typedef struct { TextBuffer json; size_t count, next_id; int failed; } StructureWriter;

static const char *structure_kind(const Stmt *statement) {
    switch(statement->kind){
        case 3:return "if";case 4:return "while";case 5:return "SEP";case 7:return "for";
        case 9:return "object";case 10:return "list";case 12:return "try";case 14:return "error";
        case 17:return "transaction";case 20:return "http_route";default:return NULL;
    }
}
static int inspect_body(StructureWriter *writer,Body body,const char *parent);
static int inspect_if_branches(StructureWriter *writer,Stmt *branch,const char *parent) {
    if(!inspect_body(writer,branch->body,parent))return 0;
    for(size_t index=0;index<branch->other.count;index++){
        Stmt *item=branch->other.items[index];
        if(item->kind==3&&item->name&&branch->name&&!strcmp(item->name,branch->name)){
            if(!inspect_if_branches(writer,item,parent))return 0;
        }else{
            Body remainder={branch->other.items+index,branch->other.count-index};
            return inspect_body(writer,remainder,parent);
        }
    }
    return 1;
}
static int inspect_named_block(StructureWriter *writer,Stmt *statement,const char *parent) {
    const char *kind=structure_kind(statement);
    if(!kind||!statement->name)return 1;
    char id[48];snprintf(id,sizeof(id),"block-%zu",++writer->next_id);
    if((writer->count++&&!buffer_char(&writer->json,','))||!buffer_append(&writer->json,"{\"id\":",6)||
       !json_string(&writer->json,id,strlen(id))||!buffer_append(&writer->json,",\"kind\":",8)||
       !json_string(&writer->json,kind,strlen(kind))||!buffer_append(&writer->json,",\"label\":",9)||
       !json_string(&writer->json,statement->name,strlen(statement->name))||!buffer_append(&writer->json,",\"parent\":",10)||
       !json_string(&writer->json,parent,strlen(parent))||
       !buffer_append(&writer->json,",\"line\":",8))return 0;
    char location[96];int written=snprintf(location,sizeof(location),"%zu,\"column\":%zu,\"tags\":[",
        statement->line,statement->column);
    if(written<0||(size_t)written>=sizeof(location)||!buffer_append(&writer->json,location,(size_t)written))return 0;
    for(size_t index=0;index<statement->tag_count;index++){
        if((index&&!buffer_char(&writer->json,','))||
           !json_string(&writer->json,statement->tags[index],strlen(statement->tags[index])))return 0;
    }
    if(!buffer_append(&writer->json,"]}",2))return 0;

    if(statement->kind==3)return inspect_if_branches(writer,statement,id);
    if(!inspect_body(writer,statement->body,id))return 0;
    if(statement->kind==12){
        for(size_t index=0;index<statement->other.count;index++)
            if(!inspect_body(writer,statement->other.items[index]->body,id))return 0;
        return inspect_body(writer,statement->final,id);
    }
    if(!inspect_body(writer,statement->other,id))return 0;
    return inspect_body(writer,statement->final,id);
}
static int inspect_body(StructureWriter *writer,Body body,const char *parent) {
    for(size_t index=0;index<body.count;index++){
        Stmt *statement=body.items[index];
        if(structure_kind(statement)){
            if(!inspect_named_block(writer,statement,parent))return 0;
        }else if(!inspect_body(writer,statement->body,parent)||
                 !inspect_body(writer,statement->other,parent)||
                 !inspect_body(writer,statement->final,parent))return 0;
    }
    return 1;
}
static char *read_source_path(const char *path) {
    FILE *file=fopen(path,"rb");if(!file)return NULL;
    if(fseek(file,0,SEEK_END)!=0){fclose(file);return NULL;}
    long size=ftell(file);if(size<0||fseek(file,0,SEEK_SET)!=0){fclose(file);return NULL;}
    char *source=malloc((size_t)size+1);if(!source){fclose(file);return NULL;}
    size_t count=fread(source,1,(size_t)size,file);fclose(file);
    if(count!=(size_t)size){free(source);return NULL;}source[count]=0;return source;
}
int separan_inspect_path_json(const char *path,char **result_json,FILE *errors) {
    if(!path||!result_json)return 1;*result_json=NULL;
    char *source=read_source_path(path);if(!source){fprintf(errors?errors:stderr,"Cannot read %s\n",path);return 1;}
    separan_runtime_options options={.root="."};separan_runtime *handle=NULL;
    int status=runtime_create_internal(source,&options,NULL,errors,0,&handle,NULL);free(source);
    if(status)return status;
    StructureWriter writer={0};int ok=buffer_char(&writer.json,'[')&&inspect_body(&writer,handle->runtime.program,"root")&&buffer_char(&writer.json,']');
    runtime_contents_destroy(handle);free(handle);
    if(!ok){free(writer.json.data);fprintf(errors?errors:stderr,"SEPARAN E741: structure JSON encoding failed\n");return 1;}
    *result_json=writer.json.data;return 0;
}
static int tag_path_matches(const Stmt *function,const char *query) {
    size_t query_length=strlen(query);
    for(size_t index=0;index<function->tag_count;index++){
        const char *tag=function->tags[index];
        if(!strncmp(tag,query,query_length)&&(tag[query_length]=='\0'||tag[query_length]==':'))return 1;
    }
    return 0;
}
int separan_inspect_tag_path_json(const char *path,const char *tag,char **result_json,FILE *errors) {
    if(!path||!tag||!result_json)return 1;*result_json=NULL;
    const char *query=tag[0]=='@'?tag+1:tag;
    if(!*query){fprintf(errors?errors:stderr,"SEPARAN S404: empty semantic tag\n");return 1;}
    char *source=read_source_path(path);if(!source){fprintf(errors?errors:stderr,"Cannot read %s\n",path);return 1;}
    separan_runtime_options options={.root="."};separan_runtime *handle=NULL;
    int status=runtime_create_internal(source,&options,NULL,errors,0,&handle,NULL);free(source);if(status)return status;
    TextBuffer json={0};int matches=0,ok=buffer_append(&json,"{\"tag\":",7)&&json_string(&json,query,strlen(query))&&buffer_append(&json,",\"functions\":[",14);
    for(size_t index=0;ok&&index<handle->runtime.program.count;index++){
        Stmt *function=handle->runtime.program.items[index];if(function->kind!=5||!tag_path_matches(function,query))continue;
        if((matches++&&!buffer_char(&json,','))||!buffer_append(&json,"{\"name\":",8)||
           !json_string(&json,function->name,strlen(function->name))||!buffer_append(&json,",\"line\":",8)) {ok=0;break;}
        char location[48];int written=snprintf(location,sizeof(location),"%zu,\"column\":%zu,\"tags\":[",function->line,function->column);
        if(written<0||(size_t)written>=sizeof(location)||!buffer_append(&json,location,(size_t)written)){ok=0;break;}
        for(size_t tag_index=0;tag_index<function->tag_count;tag_index++){
            if((tag_index&&!buffer_char(&json,','))||!json_string(&json,function->tags[tag_index],strlen(function->tags[tag_index]))){ok=0;break;}
        }
        if(ok&&!buffer_append(&json,"]}",2))ok=0;
    }
    runtime_contents_destroy(handle);free(handle);
    if(!ok){free(json.data);fprintf(errors?errors:stderr,"SEPARAN E741: tag JSON encoding failed\n");return 1;}
    if(!matches){free(json.data);fprintf(errors?errors:stderr,"SEPARAN S404: unknown semantic tag '@%s'\n",query);return 1;}
    if(!buffer_append(&json,"]}",2)){free(json.data);return 1;}
    *result_json=json.data;return 0;
}
static int token_inside_tag_scope(const separan_token *token,Stmt **functions,size_t count) {
    for(size_t index=0;index<count;index++)
        if(token->line>=functions[index]->line&&token->line<=functions[index]->end_line)return 1;
    return 0;
}
int separan_verify_tag_scope_json(const char *before_path,const char *after_path,const char *tag,
                                  char **result_json,int *passed,FILE *errors) {
    if(!before_path||!after_path||!tag||!result_json||!passed)return 1;
    *result_json=NULL;*passed=0;const char *query=tag[0]=='@'?tag+1:tag;
    if(!*query){fprintf(errors?errors:stderr,"SEPARAN S404: empty semantic tag\n");return 1;}
    char *before_source=read_source_path(before_path),*after_source=read_source_path(after_path);
    if(!before_source||!after_source){fprintf(errors?errors:stderr,"Cannot read semantic scope input\n");free(before_source);free(after_source);return 1;}
    separan_runtime_options options={.root="."};separan_runtime *before=NULL,*after=NULL;
    int status=runtime_create_internal(before_source,&options,NULL,errors,0,&before,NULL);
    if(!status)status=runtime_create_internal(after_source,&options,NULL,errors,0,&after,NULL);
    free(before_source);free(after_source);
    if(status){if(before){runtime_contents_destroy(before);free(before);}if(after){runtime_contents_destroy(after);free(after);}return status;}

    size_t before_count=0,after_count=0;
    for(size_t index=0;index<before->runtime.program.count;index++){
        Stmt *item=before->runtime.program.items[index];if(item->kind==5&&tag_path_matches(item,query))before_count++;
    }
    for(size_t index=0;index<after->runtime.program.count;index++){
        Stmt *item=after->runtime.program.items[index];if(item->kind==5&&tag_path_matches(item,query))after_count++;
    }
    if(!before_count){runtime_contents_destroy(before);free(before);runtime_contents_destroy(after);free(after);fprintf(errors?errors:stderr,"SEPARAN S404: unknown semantic tag '@%s'\n",query);return 1;}
    Stmt **before_functions=calloc(before_count,sizeof(*before_functions));
    Stmt **after_functions=calloc(after_count?after_count:1,sizeof(*after_functions));
    if(!before_functions||!after_functions){free(before_functions);free(after_functions);runtime_contents_destroy(before);free(before);runtime_contents_destroy(after);free(after);return 1;}
    size_t at=0;for(size_t index=0;index<before->runtime.program.count;index++){Stmt *item=before->runtime.program.items[index];if(item->kind==5&&tag_path_matches(item,query))before_functions[at++]=item;}
    at=0;for(size_t index=0;index<after->runtime.program.count;index++){Stmt *item=after->runtime.program.items[index];if(item->kind==5&&tag_path_matches(item,query))after_functions[at++]=item;}

    int boundary_ok=before_count==after_count;
    if(boundary_ok)for(size_t index=0;index<before_count;index++)
        if(strcmp(before_functions[index]->name,after_functions[index]->name)||!tag_path_matches(after_functions[index],query)){boundary_ok=0;break;}
    int outside_ok=boundary_ok;size_t left=0,right=0;
    while(outside_ok){
        while(left<before->runtime.tokens.count&&token_inside_tag_scope(&before->runtime.tokens.tokens[left],before_functions,before_count))left++;
        while(right<after->runtime.tokens.count&&token_inside_tag_scope(&after->runtime.tokens.tokens[right],after_functions,after_count))right++;
        if(left==before->runtime.tokens.count||right==after->runtime.tokens.count){outside_ok=left==before->runtime.tokens.count&&right==after->runtime.tokens.count;break;}
        separan_token *a=&before->runtime.tokens.tokens[left++],*b=&after->runtime.tokens.tokens[right++];
        if(strcmp(a->type,b->type)||strcmp(a->lexeme,b->lexeme))outside_ok=0;
    }
    *passed=boundary_ok&&outside_ok;

    TextBuffer json={0};const char *prefix="{\"schema\":\"separan.semantic-scope-verification.v1\",\"tag\":";
    const char *middle=*passed?",\"passed\":true,\"functions\":[":",\"passed\":false,\"functions\":[";
    int ok=buffer_append(&json,prefix,strlen(prefix))&&json_string(&json,query,strlen(query))&&
        buffer_append(&json,middle,strlen(middle));
    for(size_t index=0;ok&&index<before_count;index++)
        if((index&&!buffer_char(&json,','))||!json_string(&json,before_functions[index]->name,strlen(before_functions[index]->name)))ok=0;
    const char *suffix=*passed?"],\"violations\":[]}":"],\"violations\":[";
    if(ok)ok=buffer_append(&json,suffix,strlen(suffix));
    if(ok&&!*passed){
        const char *reason=!boundary_ok?"boundary_removed":"outside_scope_changed";
        ok=buffer_append(&json,"{\"reason\":",10)&&json_string(&json,reason,strlen(reason))&&buffer_append(&json,"}]}",3);
    }
    free(before_functions);free(after_functions);runtime_contents_destroy(before);free(before);runtime_contents_destroy(after);free(after);
    if(!ok){free(json.data);fprintf(errors?errors:stderr,"SEPARAN E741: semantic scope JSON encoding failed\n");return 1;}
    *result_json=json.data;return 0;
}

int separan_runtime_create(const char *source,const separan_runtime_options *options,
                           FILE *output,FILE *errors,separan_runtime **created) {
    return runtime_create_internal(source,options,output,errors,1,created,NULL);
}

int separan_runtime_invoke_json(separan_runtime *handle,const char *function_name,
                                const char *arguments_json,char **result_json) {
    if(!handle||!function_name||!arguments_json||!result_json)return 1;*result_json=NULL;
    Runtime *r=&handle->runtime;if(r->error||r->throwing||r->returning)return 1;
    r->steps=0;
    JsonCursor cursor={arguments_json,strlen(arguments_json),0,0};Value arguments=json_parse_value(&cursor,0);json_space(&cursor);
    if(cursor.error||cursor.at!=cursor.length||arguments.kind!=V_LIST){free_value(arguments);
        fprintf(r->errors,"SEPARAN E100: invoke arguments must be a JSON array\n");return 1;}
    Value result=invoke_named(r,function_name,arguments.items,arguments.count);free_value(arguments);
    if(r->throwing&&!r->error){Value *category=object_field(&r->thrown,"category"),*message=object_field(&r->thrown,"message");
        fprintf(r->errors,"SEPARAN %s: %.*s: %.*s at line %zu, column %zu\n",r->thrown_code[0]?r->thrown_code:"E760",category?(int)category->string_length:13,category?category->string:"runtime_error",
            message?(int)message->string_length:12,message?message->string:"error thrown",r->thrown_line,r->thrown_column);r->error=1;}
    if(!r->error){if(result.kind==V_VOID)*result_json=copy_text("null");else if(!database_json(result,result_json))fault(r,"result JSON encode error");}
    free_value(result);return r->error?1:0;
}

static int route_match(const char *pattern,const char *path,Value *params) {
    *params=object_value(0);const char *a=pattern,*b=path;
    while(*a=='/')a++;while(*b=='/')b++;
    while(*a||*b){const char *ae=strchr(a,'/'),*be=strchr(b,'/');size_t an=ae?(size_t)(ae-a):strlen(a),bn=be?(size_t)(be-b):strlen(b);
        if(!an||!bn){free_value(*params);*params=empty_value();return 0;}
        if(*a==':'){int duplicate=0;for(size_t i=0;i<params->count;i++)if(strlen(params->keys[i])==an-1&&!memcmp(params->keys[i],a+1,an-1))duplicate=1;
            if(an==1||duplicate){free_value(*params);*params=empty_value();return 0;}
            char *key=malloc(an);if(!key){free_value(*params);*params=empty_value();return 0;}memcpy(key,a+1,an-1);key[an-1]=0;
            char **keys=calloc(params->count+1,sizeof(*keys));Value *items=calloc(params->count+1,sizeof(*items));
            if(!keys||!items){free(key);free(keys);free(items);free_value(*params);*params=empty_value();return 0;}
            if(params->count){memcpy(keys,params->keys,params->count*sizeof(*keys));memcpy(items,params->items,params->count*sizeof(*items));}
            free(params->keys);free(params->items);params->keys=keys;params->items=items;
            params->keys[params->count]=key;params->items[params->count]=string_bytes(b,bn);params->count++;
        }else if(an!=bn||memcmp(a,b,an)){free_value(*params);*params=empty_value();return 0;}
        a=ae?ae+1:a+an;b=be?be+1:b+bn;
    }return 1;
}

int separan_runtime_dispatch_http_json(separan_runtime *handle,const char *request_json,char **response_json) {
    if(!handle||!request_json||!response_json)return 1;*response_json=NULL;Runtime *r=&handle->runtime;if(r->error||r->http_active)return 1;
    r->steps=0;
    JsonCursor cursor={request_json,strlen(request_json),0,0};Value request=json_parse_value(&cursor,0);json_space(&cursor);
    Value *method=object_field(&request,"method"),*path=object_field(&request,"path");
    if(cursor.error||cursor.at!=cursor.length||request.kind!=V_OBJECT||!method||method->kind!=V_STRING||!path||path->kind!=V_STRING){
        free_value(request);fprintf(r->errors,"SEPARAN E100: invalid HTTP request JSON\n");return 1;}
    Stmt *route=NULL;Value params=empty_value();
    for(size_t pass=0;pass<2&&!route;pass++)for(size_t i=0;i<r->program.count;i++){Stmt *candidate=r->program.items[i];if(candidate->kind!=20)continue;
        const char *wanted=pass==0?method->string:(!strcmp(method->string,"HEAD")?"GET":"");if(!*wanted||strcmp(candidate->method,wanted))continue;
        Value found=empty_value();if(route_match(candidate->path,path->string,&found)){route=candidate;params=found;break;}}
    if(!route){Value response=http_default_response(404,"Not Found");int ok=database_json(response,response_json);free_value(response);free_value(request);return ok?0:1;}
    r->http_active=1;r->http_returned=0;r->http_request=request;r->http_params=params;r->http_cookies.kind=V_LIST;
    Frame request_frame={0};request_frame.parent=&r->global;execute_body(r,&request_frame,route->body);free_frame(&request_frame);
    if(!r->error&&!r->http_returned)r->http_response=http_default_response(204,"");
    if(!r->error&&!database_json(r->http_response,response_json))fault(r,"result JSON encode error");
    free_value(r->http_request);r->http_request=empty_value();free_value(r->http_params);r->http_params=empty_value();
    free_value(r->http_response);r->http_response=empty_value();free_value(r->http_cookies);r->http_cookies=empty_value();r->http_active=0;r->http_returned=0;
    return r->error?1:0;
}

void separan_runtime_get_diagnostic(const separan_runtime *handle,
                                   separan_runtime_diagnostic *diagnostic) {
    if(!diagnostic)return;
    memset(diagnostic,0,sizeof(*diagnostic));
    if(!handle)return;
    const Runtime *r=&handle->runtime;
    diagnostic->line_number=r->error_line;
    diagnostic->column_number=r->error_column;
    diagnostic->related_line_number=r->error_related_line;
    diagnostic->related_column_number=r->error_related_column;
    snprintf(diagnostic->category,sizeof(diagnostic->category),"%s",r->error_category);
    snprintf(diagnostic->description,sizeof(diagnostic->description),"%s",r->error_description);
    snprintf(diagnostic->expected,sizeof(diagnostic->expected),"%s",r->error_expected);
    snprintf(diagnostic->actual,sizeof(diagnostic->actual),"%s",r->error_actual);
}

void separan_runtime_release_string(char *value){free(value);}
void separan_runtime_destroy(separan_runtime *runtime){if(!runtime)return;runtime_contents_destroy(runtime);free(runtime);}

int separan_check_source_detailed(const char *source, FILE *errors,
                                  separan_runtime_diagnostic *diagnostic) {
    separan_runtime_options options={.root="."};separan_runtime *handle=NULL;
    int status=runtime_create_internal(source,&options,NULL,errors,0,&handle,diagnostic);
    separan_runtime_destroy(handle);return status;
}

int separan_check_source(const char *source, FILE *errors) {
    return separan_check_source_detailed(source,errors,NULL);
}

int separan_check_path_detailed(const char *path, FILE *errors,
                                separan_runtime_diagnostic *diagnostic) {
    if(diagnostic)memset(diagnostic,0,sizeof(*diagnostic));
    FILE *file=fopen(path,"rb");if(!file){fprintf(errors?errors:stderr,"Cannot open %s\n",path);return 1;}
    if(fseek(file,0,SEEK_END)!=0){fclose(file);return 1;}long size=ftell(file);
    if(size<0||fseek(file,0,SEEK_SET)!=0){fclose(file);return 1;}
    char *source=malloc((size_t)size+1);if(!source){fclose(file);return 1;}
    size_t count=fread(source,1,(size_t)size,file);fclose(file);source[count]=0;
    int status=separan_check_source_detailed(source,errors,diagnostic);free(source);return status;
}

int separan_check_path(const char *path, FILE *errors) {
    return separan_check_path_detailed(path,errors,NULL);
}

static int separan_run_source_at(const char *source, const separan_runtime_options *options,
                                 FILE *output, FILE *errors) {
    separan_runtime *handle=NULL;if(separan_runtime_create(source,options,output,errors,&handle))return 1;
    Runtime *r=&handle->runtime;
    if(find_function(r,"main")){
        char *result=NULL;if(separan_runtime_invoke_json(handle,"main","[]",&result)){separan_runtime_destroy(handle);return 1;}
        separan_runtime_release_string(result);
    }
    separan_runtime_destroy(handle);return 0;
}

int separan_run_source(const char *source, FILE *output, FILE *errors) {
    separan_runtime_options options = {.root = ".", .read_files = 1, .write_files = 1, .discover_paths = 1,
        .import_modules = 1, .read_environment = 1, .write_environment = 1};
    return separan_run_source_at(source, &options, output, errors);
}

int separan_run_source_with_options(const char *source, const separan_runtime_options *options,
                                    FILE *output, FILE *errors) {
    if (!options) return 1;
    return separan_run_source_at(source, options, output, errors);
}

int separan_run_path_with_arguments(const char *path, const char *const *arguments,
                                    size_t argument_count, FILE *output, FILE *errors) {
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
    separan_runtime_options options = {.root = root && *root ? root : ".", .read_files = 1,
        .write_files = 1, .discover_paths = 1, .import_modules = 1, .read_environment = 1, .write_environment = 1, .script_path = path,
        .command_arguments = arguments, .command_argument_count = argument_count};
    int status = separan_run_source_at(source, &options, output, errors);
    free(root);
    free(source); return status;
}

int separan_run_path(const char *path, FILE *output, FILE *errors) {
    return separan_run_path_with_arguments(path, NULL, 0, output, errors);
}
