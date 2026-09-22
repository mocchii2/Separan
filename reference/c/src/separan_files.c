#define _XOPEN_SOURCE 700
#include "separan_files.h"

#include <stdio.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#ifdef _WIN32
#include <windows.h>
#include <direct.h>
#include <io.h>
#else
#include <dirent.h>
#include <unistd.h>
#endif

static int separator(char c) { return c == '/' || c == '\\'; }

static int valid_utf8(const char *data, size_t length) {
    for (size_t i = 0; i < length;) {
        unsigned char lead = (unsigned char)data[i];
        if (lead < 0x80) { i++; continue; }
        size_t width = lead >= 0xF0 && lead <= 0xF4 ? 4 :
                       lead >= 0xE0 && lead <= 0xEF ? 3 :
                       lead >= 0xC2 && lead <= 0xDF ? 2 : 0;
        if (!width || i + width > length) return 0;
        unsigned codepoint = lead & ((1u << (7 - width)) - 1u);
        for (size_t j = 1; j < width; j++) {
            unsigned char part = (unsigned char)data[i + j];
            if ((part & 0xC0) != 0x80) return 0;
            codepoint = (codepoint << 6) | (part & 0x3F);
        }
        if ((width == 2 && codepoint < 0x80) || (width == 3 && codepoint < 0x800) ||
            (width == 4 && codepoint < 0x10000) || codepoint > 0x10FFFF ||
            (codepoint >= 0xD800 && codepoint <= 0xDFFF)) return 0;
        i += width;
    }
    return 1;
}

int separan_files_init(separan_files *files, const char *root) {
    if (!files || !root) return 1;
    files->root = NULL;
#ifdef _WIN32
    files->root = _fullpath(NULL, root, 0);
#else
    files->root = realpath(root, NULL);
#endif
    return files->root ? 0 : 1;
}

void separan_files_free(separan_files *files) {
    if (!files) return;
    free(files->root); files->root = NULL;
}

static int valid_relative(const char *path) {
    if (!path || !*path || separator(path[0])) return 0;
    if (path[0] && path[1] == ':') return 0;
    const char *segment = path;
    for (const char *p = path;; p++) {
        if (*p == '\0' || separator(*p)) {
            if (p - segment == 2 && segment[0] == '.' && segment[1] == '.') return 0;
            if (*p == '\0') break;
            segment = p + 1;
        }
    }
    return 1;
}

static int reparse_component(const char *path) {
#ifdef _WIN32
    DWORD attributes = GetFileAttributesA(path);
    return attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0;
#else
    struct stat info;
    return lstat(path, &info) == 0 && S_ISLNK(info.st_mode);
#endif
}

int separan_files_path(const separan_files *files, const char *relative, char **absolute) {
    if (!files || !files->root || !absolute || !valid_relative(relative)) return 1;
    *absolute = NULL;
    size_t root_length = strlen(files->root), path_length = strlen(relative);
    if (root_length > SIZE_MAX - path_length - 2) return 1;
    char *path = malloc(root_length + path_length + 2);
    if (!path) return 1;
    memcpy(path, files->root, root_length);
    path[root_length] = '/';
    memcpy(path + root_length + 1, relative, path_length + 1);
    for (size_t i = root_length + 1; i <= root_length + path_length; i++) {
        if (path[i] == '\\') path[i] = '/';
        if (path[i] == '/' || path[i] == '\0') {
            char saved = path[i]; path[i] = '\0';
            if (reparse_component(path)) { free(path); return 1; }
            path[i] = saved;
        }
    }
    *absolute = path; return 0;
}

int separan_files_read_bytes(const separan_files *files, const char *relative, char **text, size_t *length) {
    if (!text || !length) return 1;
    *text = NULL; *length = 0;
    char *path;
    if (separan_files_path(files, relative, &path)) return 1;
    FILE *file = fopen(path, "rb"); free(path);
    if (!file) return 2;
    if (fseek(file, 0, SEEK_END) || ftell(file) < 0) { fclose(file); return 2; }
    long size = ftell(file);
    if (fseek(file, 0, SEEK_SET)) { fclose(file); return 2; }
    char *data = malloc((size_t)size + 1);
    if (!data) { fclose(file); return 2; }
    size_t count = fread(data, 1, (size_t)size, file);
    if (count != (size_t)size || ferror(file)) { free(data); fclose(file); return 2; }
    fclose(file); data[count] = 0;
    *text = data; *length = count; return 0;
}

int separan_files_read_text(const separan_files *files, const char *relative, char **text, size_t *length) {
    char *data; size_t count;
    int status = separan_files_read_bytes(files, relative, &data, &count);
    if (status) return status;
    size_t written = 0;
    for (size_t i = 0; i < count; i++) {
        if (data[i] == '\r') {
            if (i + 1 < count && data[i + 1] == '\n') i++;
            data[written++] = '\n';
        } else data[written++] = data[i];
    }
    data[written] = 0;
    if (!valid_utf8(data, written)) { free(data); return 2; }
    *text = data; *length = written; return 0;
}

static int make_parents(char *path, size_t root_length) {
    size_t length = strlen(path);
    for (size_t i = root_length + 1; i < length; i++) {
        if (path[i] != '/') continue;
        path[i] = 0;
#ifdef _WIN32
        int status = _mkdir(path);
#else
        int status = mkdir(path, 0777);
#endif
        if (status && errno != EEXIST) { path[i] = '/'; return 1; }
        struct stat info;
        if (stat(path, &info) || (info.st_mode & S_IFMT) != S_IFDIR || reparse_component(path)) {
            path[i] = '/'; return 1;
        }
        path[i] = '/';
    }
    return 0;
}

int separan_files_write_bytes(const separan_files *files, const char *relative, const char *text, size_t length) {
    char *path;
    if (!text || separan_files_path(files, relative, &path)) return 1;
    if (make_parents(path, strlen(files->root))) { free(path); return 2; }
    size_t path_length = strlen(path);
    char *temporary = malloc(path_length + 24);
    if (!temporary) { free(path); return 2; }
    const char *slash = strrchr(path, '/');
    size_t directory_length = slash ? (size_t)(slash - path) : path_length;
    memcpy(temporary, path, directory_length);
    temporary[directory_length] = 0;
    strcat(temporary, "/.separan-XXXXXX");
#ifdef _WIN32
    if (_mktemp_s(temporary, path_length + 24) != 0) { free(path); free(temporary); return 2; }
    HANDLE handle = CreateFileA(temporary, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (handle == INVALID_HANDLE_VALUE) { free(path); free(temporary); return 2; }
    DWORD written = 0;
    int ok = length <= 0xFFFFFFFFu && WriteFile(handle, text, (DWORD)length, &written, NULL) && written == length;
    ok = CloseHandle(handle) && ok;
    if (ok) ok = MoveFileExA(temporary, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
    if (!ok) DeleteFileA(temporary);
#else
    int descriptor = mkstemp(temporary);
    if (descriptor < 0) { free(path); free(temporary); return 2; }
    FILE *stream = fdopen(descriptor, "wb");
    if (!stream) { close(descriptor); unlink(temporary); free(path); free(temporary); return 2; }
    int ok = fwrite(text, 1, length, stream) == length && fflush(stream) == 0;
    if (fclose(stream)) ok = 0;
    if (ok) ok = rename(temporary, path) == 0;
    if (!ok) unlink(temporary);
#endif
    free(path); free(temporary);
    return ok ? 0 : 2;
}

int separan_files_write_text(const separan_files *files, const char *relative, const char *text, size_t length) {
    if (!text || !valid_utf8(text, length)) return 1;
    return separan_files_write_bytes(files, relative, text, length);
}

int separan_files_append_text(const separan_files *files, const char *relative, const char *text, size_t length) {
    char *path;
    if (!text || !valid_utf8(text, length) || separan_files_path(files, relative, &path)) return 1;
    FILE *file = fopen(path, "rb");
    free(path);
    size_t old_length = 0;
    char *old = NULL;
    if (file) {
        if (fseek(file, 0, SEEK_END)) { fclose(file); return 2; }
        long size = ftell(file);
        if (size < 0 || fseek(file, 0, SEEK_SET)) { fclose(file); return 2; }
        old_length = (size_t)size;
        old = malloc(old_length ? old_length : 1);
        if (!old) { fclose(file); return 2; }
        if (fread(old, 1, old_length, file) != old_length || ferror(file)) {
            free(old); fclose(file); return 2;
        }
        fclose(file);
        if (!valid_utf8(old, old_length)) { free(old); return 2; }
    } else if (errno != ENOENT) return 2;
    if (old_length > SIZE_MAX - length) { free(old); return 2; }
    char *joined = malloc(old_length + length + 1);
    if (!joined) { free(old); return 2; }
    if (old_length) memcpy(joined, old, old_length);
    memcpy(joined + old_length, text, length);
    joined[old_length + length] = 0;
    free(old);
    int status = separan_files_write_text(files, relative, joined, old_length + length);
    free(joined); return status;
}

int separan_files_exists(const separan_files *files, const char *relative, int *exists) {
    if (!exists) return 1;
    *exists = 0;
    char *path;
    if (separan_files_path(files, relative, &path)) return 1;
    struct stat info;
    if (stat(path, &info) == 0 && (info.st_mode & S_IFMT) == S_IFREG) *exists = 1;
    free(path); return 0;
}

int separan_files_directory_exists(const separan_files *files, const char *relative, int *exists) {
    if (!exists) return 1;
    *exists = 0;
    char *path;
    if (separan_files_path(files, relative, &path)) return 1;
    struct stat info;
    if (stat(path, &info) == 0 && (info.st_mode & S_IFMT) == S_IFDIR) *exists = 1;
    free(path); return 0;
}

int separan_files_create_directory(const separan_files *files, const char *relative) {
    char *path;
    if (separan_files_path(files, relative, &path)) return 1;
    if (make_parents(path, strlen(files->root))) { free(path); return 2; }
#ifdef _WIN32
    int status = _mkdir(path);
#else
    int status = mkdir(path, 0777);
#endif
    free(path); return status ? 2 : 0;
}

int separan_files_delete_directory(const separan_files *files, const char *relative) {
    char *path;
    if (separan_files_path(files, relative, &path)) return 1;
#ifdef _WIN32
    int status = _rmdir(path);
#else
    int status = rmdir(path);
#endif
    free(path); return status ? 2 : 0;
}

int separan_files_delete_file(const separan_files *files, const char *relative) {
    char *path;
    if (separan_files_path(files, relative, &path)) return 1;
    struct stat info;
    int status = stat(path, &info);
    if (status || (info.st_mode & S_IFMT) != S_IFREG) { free(path); return 2; }
#ifdef _WIN32
    status = _unlink(path);
#else
    status = unlink(path);
#endif
    free(path); return status ? 2 : 0;
}

int separan_files_copy_file(const separan_files *files, const char *source, const char *destination) {
    char *from = NULL, *to = NULL;
    if (separan_files_path(files, source, &from)) return 1;
    if (separan_files_path(files, destination, &to)) { free(from); return 1; }
    struct stat info;
    if (stat(from, &info) || (info.st_mode & S_IFMT) != S_IFREG) { free(from); free(to); return 2; }
    if (stat(to, &info) == 0) { free(from); free(to); return 3; }
    if (make_parents(to, strlen(files->root))) { free(from); free(to); return 2; }
    FILE *input = fopen(from, "rb");
    FILE *output = input ? fopen(to, "wbx") : NULL;
    if (!input || !output) {
        if (input) fclose(input);
        free(from); free(to); return 2;
    }
    int ok = 1;
    char buffer[65536];
    size_t count;
    while ((count = fread(buffer, 1, sizeof(buffer), input)) != 0)
        if (fwrite(buffer, 1, count, output) != count) { ok = 0; break; }
    if (ferror(input)) ok = 0;
    if (fclose(input)) ok = 0;
    if (fclose(output)) ok = 0;
    if (!ok) remove(to);
    free(from); free(to); return ok ? 0 : 2;
}

int separan_files_move_file(const separan_files *files, const char *source, const char *destination) {
    char *from = NULL, *to = NULL;
    if (separan_files_path(files, source, &from)) return 1;
    if (separan_files_path(files, destination, &to)) { free(from); return 1; }
    struct stat info;
    if (stat(from, &info) || (info.st_mode & S_IFMT) != S_IFREG) { free(from); free(to); return 2; }
    if (stat(to, &info) == 0) { free(from); free(to); return 3; }
    if (make_parents(to, strlen(files->root))) { free(from); free(to); return 2; }
    int moved = rename(from, to) == 0;
    free(from); free(to);
    if (moved) return 0;
    int copied = separan_files_copy_file(files, source, destination);
    if (copied) return copied;
    return separan_files_delete_file(files, source);
}

int separan_files_size(const separan_files *files, const char *relative, size_t *size) {
    if (!size) return 1;
    char *path;
    if (separan_files_path(files, relative, &path)) return 1;
    struct stat info;
    int status = stat(path, &info);
    free(path);
    if (status || (info.st_mode & S_IFMT) != S_IFREG || info.st_size < 0) return 2;
    *size = (size_t)info.st_size; return 0;
}

static int compare_names(const void *left, const void *right) {
    const char *a = *(const char *const *)left;
    const char *b = *(const char *const *)right;
    return strcmp(a, b);
}

void separan_files_list_free(char **names, size_t count) {
    if (!names) return;
    for (size_t i = 0; i < count; i++) free(names[i]);
    free(names);
}

static int add_name(char ***names, size_t *count, const char *name) {
    if (strcmp(name, ".") == 0 || strcmp(name, "..") == 0) return 0;
    char **next = realloc(*names, (*count + 1) * sizeof(*next));
    if (!next) return 1;
    *names = next;
    size_t length = strlen(name);
    next[*count] = malloc(length + 1);
    if (!next[*count]) return 1;
    memcpy(next[*count], name, length + 1);
    (*count)++; return 0;
}

int separan_files_list_directory(const separan_files *files, const char *relative, char ***names, size_t *count) {
    if (!names || !count) return 1;
    *names = NULL; *count = 0;
    char *path;
    if (separan_files_path(files, relative, &path)) return 1;
    struct stat info;
    if (stat(path, &info) || (info.st_mode & S_IFMT) != S_IFDIR) { free(path); return 2; }
    int status = 0;
#ifdef _WIN32
    size_t length = strlen(path);
    char *pattern = malloc(length + 3);
    if (!pattern) { free(path); return 2; }
    memcpy(pattern, path, length); memcpy(pattern + length, "/*", 3);
    WIN32_FIND_DATAA entry;
    HANDLE search = FindFirstFileA(pattern, &entry);
    free(pattern);
    if (search == INVALID_HANDLE_VALUE) status = 2;
    else {
        do { if (add_name(names, count, entry.cFileName)) { status = 2; break; } }
        while (FindNextFileA(search, &entry));
        FindClose(search);
    }
#else
    DIR *directory = opendir(path);
    if (!directory) status = 2;
    else {
        struct dirent *entry;
        while ((entry = readdir(directory))) if (add_name(names, count, entry->d_name)) { status = 2; break; }
        closedir(directory);
    }
#endif
    free(path);
    if (status) { separan_files_list_free(*names, *count); *names = NULL; *count = 0; return status; }
    qsort(*names, *count, sizeof(**names), compare_names);
    return 0;
}
