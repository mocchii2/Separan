CC = gcc
AR = ar
CFLAGS = -O1 -std=c11 -Wall -Wextra -Iinclude
BIN = separan.exe
GW_BIN = separan-gw.exe
LIB = libseparan.a
OBJ = src\main.o src\separan_core.o src\separan_lexer.o src\separan_files.o src\separan_runtime.o
EXTRA_BINS = separan_bigint.exe separan_check.exe separan_diff.exe separan_diff2.exe separan_diff3.exe separan_int.exe \
	test_lexer_unicode.exe test_runtime_asan.exe test_runtime_bigint.exe test_runtime_bigint_asan.exe \
	test_runtime_check.exe test_runtime_check_new.exe test_runtime_regex.exe test_runtime_regex_asan.exe \
	test_runtime_shapes.exe test_runtime_shapes_asan.exe test_runtime_shapes_asan_new.exe test_runtime_unicode.exe
EXTRA_OBJ = src\separan_core.check.o src\separan_files.check.o src\separan_lexer.check.o \
	src\separan_lexer_unicode.o src\separan_runtime.check.o src\separan_runtime_bigint.o
ZIP = dist\separan-portable.zip
TARBALL = dist\separan-linux-x86_64.tar.gz
PORTABLE_DIR = dist\separan-portable
LINUX_DIR = dist\separan-linux-x86_64
LINUX_BIN = separan

ifeq ($(OS),Windows_NT)
	RM = cmd /C del /Q /F
	GW_SOCKET_LIBS = -lws2_32 -lpsapi -ladvapi32
else
	RM = rm -f
	GW_SOCKET_LIBS =
endif

all: $(BIN) $(GW_BIN) $(LIB)

$(LIB): src\separan_core.o src\separan_lexer.o src\separan_files.o src\separan_runtime.o
	$(AR) rcs $@ src\separan_core.o src\separan_lexer.o src\separan_files.o src\separan_runtime.o

$(BIN): $(OBJ) $(LIB)
	$(CC) $(CFLAGS) -o $@ src\main.o $(LIB) -lm

$(GW_BIN): $(LIB) src\separan_gw.c src\separan_gw_fastcgi.c src\separan_gw_supervisor.c include\separan_gw_transport.h
	$(CC) $(CFLAGS) -o $@ src\separan_gw.c src\separan_gw_fastcgi.c src\separan_gw_supervisor.c $(LIB) -lm $(GW_SOCKET_LIBS)

gateway: $(GW_BIN)

$(ZIP): $(BIN) separan.cmd README.md build_portable_zip.py
	python build_portable_zip.py

src/%.o: src/%.c include/separan_core.h include/separan_lexer.h include/separan_files.h include/separan_runtime.h
	$(CC) $(CFLAGS) -c $< -o $@

src/separan_lexer.o: src/separan_unicode_tables.inc

test: $(BIN)
	./$(BIN) testdata/hello.sep
	./$(BIN) --check testdata/hello.sep

library-test: $(LIB)
	python generate_unicode_tables.py --check
	$(CC) $(CFLAGS) -Iinclude -o test_library_api.exe test_library_api.c $(LIB)
	./test_library_api.exe
	$(CC) $(CFLAGS) -Iinclude -o test_lexer_api.exe test_lexer_api.c $(LIB)
	./test_lexer_api.exe
	$(CC) $(CFLAGS) -Iinclude -o test_runtime_api.exe test_runtime_api.c $(LIB) -lm
	./test_runtime_api.exe

zip: $(ZIP)

ifeq ($(OS),Windows_NT)
linux-tarball:
	@echo Native Linux tarballs must be built on Linux. 1>&2
	@exit /b 1
else
linux-tarball:
	$(CC) -O1 -std=c11 -Wall -Wextra -Iinclude src/main.c src/separan_core.c src/separan_lexer.c src/separan_files.c src/separan_runtime.c -lm -o $(LINUX_BIN)
	python build_linux_tarball.py --binary $(LINUX_BIN)
endif

clean:
	$(RM) $(BIN) $(GW_BIN) $(LINUX_BIN) $(LIB) test_library_api.exe test_lexer_api.exe test_runtime_api.exe $(OBJ) $(EXTRA_BINS) $(EXTRA_OBJ)
	python -c "import pathlib, shutil; root = pathlib.Path('dist'); portable = root / 'separan-portable'; linux = root / 'separan-linux-x86_64'; zip_archive = root / 'separan-portable.zip'; tgz = root / 'separan-linux-x86_64.tar.gz'; shutil.rmtree(portable, ignore_errors=True) if portable.exists() else None; shutil.rmtree(linux, ignore_errors=True) if linux.exists() else None; zip_archive.unlink() if zip_archive.exists() else None; tgz.unlink() if tgz.exists() else None"
