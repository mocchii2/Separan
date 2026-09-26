#include "separan_runtime.h"
#include "separan_lexer.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void print_help(const char *program_name) {
    printf("Separan native core\n");
    printf("Usage: %s <source.sep> [arguments...]\n", program_name);
    printf("       %s --check <source.sep>\n", program_name);
    printf("       %s --tokens <source.sep>\n", program_name);
    printf("       %s --structure <source.sep>\n", program_name);
    printf("       %s --tag <source.sep> <semantic-tag>\n", program_name);
    printf("       %s --verify-tag-scope <before.sep> <after.sep> <semantic-tag>\n", program_name);
    printf("       %s --format <source.sep>\n", program_name);
    printf("       %s -help\n", program_name);
    printf("\n");
    printf("Run a Separan source file, check syntax and declarations, or inspect lexer tokens.\n");
}

static int print_json_string(const char *text) {
    static const char hex[] = "0123456789abcdef";
    if (putchar('"') == EOF) return 0;
    for (const unsigned char *at = (const unsigned char *)text; *at; at++) {
        if (*at == '"' || *at == '\\') {
            if (putchar('\\') == EOF || putchar(*at) == EOF) return 0;
        } else if (*at < 0x20) {
            if (printf("\\u00%c%c", hex[*at >> 4], hex[*at & 15]) < 0) return 0;
        } else if (putchar(*at) == EOF) {
            return 0;
        }
    }
    return putchar('"') != EOF;
}

static int print_tokens(const char *path) {
    FILE *source_file = fopen(path, "rb");
    if (!source_file) {
        fprintf(stderr, "Cannot open %s\n", path);
        return 1;
    }
    if (fseek(source_file, 0, SEEK_END) != 0) { fclose(source_file); return 1; }
    long source_size = ftell(source_file);
    if (source_size < 0 || fseek(source_file, 0, SEEK_SET) != 0) { fclose(source_file); return 1; }
    char *source = malloc((size_t)source_size + 1);
    if (!source) { fclose(source_file); return 1; }
    size_t bytes_read = fread(source, 1, (size_t)source_size, source_file);
    fclose(source_file);
    if (bytes_read != (size_t)source_size) { free(source); return 1; }
    source[bytes_read] = '\0';

    separan_tokens tokens = {0};
    int lex_status = separan_lex(source, &tokens);
    free(source);
    if (lex_status) {
        fprintf(stderr, "SEPARAN %s: lexer error at line %zu, column %zu\n",
                tokens.error_code, tokens.error_line, tokens.error_column);
        separan_tokens_free(&tokens);
        return 1;
    }

    if (putchar('[') == EOF) { separan_tokens_free(&tokens); return 1; }
    for (size_t index = 0; index < tokens.count; index++) {
        separan_token *token = &tokens.tokens[index];
        if ((index && putchar(',') == EOF) ||
                printf("{\"type\":") < 0 || !print_json_string(token->type) ||
                printf(",\"lexeme\":") < 0 || !print_json_string(token->lexeme) ||
                printf(",\"line\":%zu,\"column\":%zu}", token->line, token->column) < 0) {
            separan_tokens_free(&tokens);
            return 1;
        }
    }
    int status = puts("]") == EOF ? 1 : 0;
    separan_tokens_free(&tokens);
    return status;
}

static size_t code_before_comment_length(const char *line) {
    int quoted=0,escaped=0;
    size_t length=strlen(line);
    for(size_t index=0;index<length;index++){
        char character=line[index];
        if(quoted){
            if(escaped)escaped=0;
            else if(character=='\\')escaped=1;
            else if(character=='"')quoted=0;
        }else if(character=='"')quoted=1;
        else if(character=='#'){
            while(index&&(line[index-1]==' '||line[index-1]=='\t'))index--;
            return index;
        }
    }
    while(length&&(line[length-1]==' '||line[length-1]=='\t'))length--;
    return length;
}
static const char *line_word(const char *line,size_t *length) {
    while(*line==' '||*line=='\t')line++;
    const char *start=line;
    while(isalpha((unsigned char)*line)||*line=='_')line++;
    *length=(size_t)(line-start);return start;
}
static int word_is(const char *word,size_t length,const char *candidate) {
    return strlen(candidate)==length&&!memcmp(word,candidate,length);
}
static char *copy_label(const char *text,size_t length) {
    char *copy=malloc(length+1);if(!copy)return NULL;
    memcpy(copy,text,length);copy[length]='\0';return copy;
}
static int format_line_is_close(const char *word,size_t length) {
    static const char *const closers[]={"END_SEP","end_sep","endif","endwhile","endfor","end_object","end_list","endtry","end_error","end_http_route","end_transaction"};
    for(size_t index=0;index<sizeof(closers)/sizeof(*closers);index++)if(word_is(word,length,closers[index]))return 1;
    return 0;
}
static int format_line_is_branch(const char *word,size_t length,const char *code) {
    if(!strchr(code,':'))return 0;
    return word_is(word,length,"elseif")||word_is(word,length,"else")||
           word_is(word,length,"catch")||word_is(word,length,"finally");
}
static int format_line_is_open(const char *word,size_t length) {
    static const char *const openers[]={"SEP","sep","if","while","for","object","list","try","error","http_route","transaction"};
    for(size_t index=0;index<sizeof(openers)/sizeof(*openers);index++)if(word_is(word,length,openers[index]))return 1;
    return 0;
}
static char *multiline_comment_delimiter(const char *line) {
    while(*line==' '||*line=='\t')line++;
    if(line[0]!='#'||line[1]!='#')return NULL;
    const char *label=line+2;
    const char *end=label+strlen(label);while(end>label&&(end[-1]==' '||end[-1]=='\t'))end--;
    if(label==end)return copy_label("",0);
    char *delimiter=copy_label(label,(size_t)(end-label));
    if(!delimiter||!separan_is_identifier(delimiter)){free(delimiter);return NULL;}
    return delimiter;
}
static int print_formatted_source(const char *path) {
    FILE *file=fopen(path,"rb");if(!file){fprintf(stderr,"Cannot open %s\n",path);return 1;}
    if(fseek(file,0,SEEK_END)!=0){fclose(file);return 1;}
    long size=ftell(file);if(size<0||fseek(file,0,SEEK_SET)!=0){fclose(file);return 1;}
    char *source=malloc((size_t)size+1);if(!source){fclose(file);return 1;}
    size_t length=fread(source,1,(size_t)size,file);fclose(file);
    if(length!=(size_t)size){free(source);return 1;}source[length]='\0';
    if(separan_check_source(source,stderr)){free(source);return 1;}

    size_t depth=0;char *comment_label=NULL;const char *cursor=source;
    while(*cursor){
        const char *end=cursor;while(*end&&*end!='\r'&&*end!='\n')end++;
        size_t line_length=(size_t)(end-cursor);char *line=malloc(line_length+1);
        if(!line){free(comment_label);free(source);return 1;}
        memcpy(line,cursor,line_length);line[line_length]='\0';
        char *stripped=line;while(*stripped==' '||*stripped=='\t')stripped++;
        size_t content_length=strlen(stripped);while(content_length&&(stripped[content_length-1]==' '||stripped[content_length-1]=='\t'))stripped[--content_length]='\0';
        if(content_length){
            char *delimiter=multiline_comment_delimiter(stripped);
            if(comment_label){
                for(size_t index=0;index<depth;index++)if(fputs("    ",stdout)==EOF){free(delimiter);free(line);free(comment_label);free(source);return 1;}
                if(fputs(stripped,stdout)==EOF){free(delimiter);free(line);free(comment_label);free(source);return 1;}
                if(delimiter&&strcmp(delimiter,comment_label)==0){free(comment_label);comment_label=NULL;}
            }else{
                size_t code_length=code_before_comment_length(stripped);
                char *code=copy_label(stripped,code_length);if(!code){free(delimiter);free(line);free(source);return 1;}
                size_t word_length=0;const char *word=line_word(code,&word_length);
                int branch=format_line_is_branch(word,word_length,code);
                int closing=format_line_is_close(word,word_length);
                int opening=format_line_is_open(word,word_length);
                if((closing||branch)&&depth)depth--;
                for(size_t index=0;index<depth;index++)if(fputs("    ",stdout)==EOF){free(code);free(delimiter);free(line);free(source);return 1;}
                if(fputs(stripped,stdout)==EOF){free(code);free(delimiter);free(line);free(source);return 1;}
                free(code);
                if(delimiter)comment_label=delimiter,delimiter=NULL;
                else{
                    if(branch)depth++;
                    else if(opening)depth++;
                }
            }
            free(delimiter);
        }
        free(line);if(*end&&putchar('\n')==EOF){free(comment_label);free(source);return 1;}
        if(*end=='\r'&&end[1]=='\n')cursor=end+2;else if(*end)cursor=end+1;else cursor=end;
    }
    free(comment_label);free(source);return ferror(stdout)?1:0;
}

int main(int argc, char **argv) {
    if (argc == 2 && (strcmp(argv[1], "-help") == 0 || strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "/?") == 0)) {
        print_help(argv[0]);
        return 0;
    }

    if (argc == 3 && strcmp(argv[1], "--check") == 0) {
        int result = separan_check_path(argv[2], stderr);
        if (result == 0) printf("Separan native core: OK\n");
        return result;
    }

    if (argc == 3 && strcmp(argv[1], "--format") == 0) {
        return print_formatted_source(argv[2]);
    }

    if (argc == 3 && strcmp(argv[1], "--tokens") == 0) {
        return print_tokens(argv[2]);
    }

    if (argc == 3 && strcmp(argv[1], "--structure") == 0) {
        char *result_json = NULL;
        if (separan_inspect_path_json(argv[2], &result_json, stderr) != 0) return 1;
        puts(result_json);
        separan_runtime_release_string(result_json);
        return 0;
    }

    if (argc == 4 && strcmp(argv[1], "--tag") == 0) {
        char *result_json = NULL;
        if (separan_inspect_tag_path_json(argv[2], argv[3], &result_json, stderr) != 0) return 1;
        puts(result_json);
        separan_runtime_release_string(result_json);
        return 0;
    }

    if (argc == 5 && strcmp(argv[1], "--verify-tag-scope") == 0) {
        char *result_json = NULL;
        int passed = 0;
        if (separan_verify_tag_scope_json(argv[2], argv[3], argv[4], &result_json,
                                          &passed, stderr) != 0) return 1;
        puts(result_json);
        separan_runtime_release_string(result_json);
        return passed ? 0 : 1;
    }

    if (argc < 2) {
        fprintf(stderr, "Usage: %s <source.sep> [arguments...]\n", argv[0]);
        return 2;
    }

    return separan_run_path_with_arguments(argv[1], (const char *const *)(argv + 2),
                                           (size_t)(argc - 2), stdout, stderr);
}
