#ifndef SEPARAN_FILES_H
#define SEPARAN_FILES_H

#include <stddef.h>

typedef struct { char *root; } separan_files;

int separan_files_init(separan_files *files, const char *root);
void separan_files_free(separan_files *files);
/* Return 0 on success. Paths are relative to root and may not traverse it. */
int separan_files_path(const separan_files *files, const char *relative, char **absolute);
int separan_files_read_text(const separan_files *files, const char *relative, char **text, size_t *length);
int separan_files_read_bytes(const separan_files *files, const char *relative, char **data, size_t *length);
int separan_files_write_text(const separan_files *files, const char *relative, const char *text, size_t length);
int separan_files_write_bytes(const separan_files *files, const char *relative, const char *data, size_t length);
int separan_files_append_text(const separan_files *files, const char *relative, const char *text, size_t length);
int separan_files_exists(const separan_files *files, const char *relative, int *exists);
int separan_files_directory_exists(const separan_files *files, const char *relative, int *exists);
int separan_files_size(const separan_files *files, const char *relative, size_t *size);
int separan_files_list_directory(const separan_files *files, const char *relative, char ***names, size_t *count);
void separan_files_list_free(char **names, size_t count);
int separan_files_create_directory(const separan_files *files, const char *relative);
int separan_files_delete_directory(const separan_files *files, const char *relative);
int separan_files_delete_file(const separan_files *files, const char *relative);
/* Return 3 when the destination already exists. */
int separan_files_copy_file(const separan_files *files, const char *source, const char *destination);
int separan_files_move_file(const separan_files *files, const char *source, const char *destination);

#endif
