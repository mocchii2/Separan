CC = gcc
AR = ar
CFLAGS = -std=c11 -Wall -Wextra -Iinclude
BIN = separan.exe
LIB = libseparan.a
OBJ = src\main.o src\separan_core.o src\separan_lexer.o src\separan_files.o src\separan_runtime.o
ZIP = dist\separan-portable.zip
TARBALL = dist\separan-linux-x86_64.tar.gz
PORTABLE_DIR = dist\separan-portable
LINUX_DIR = dist\separan-linux-x86_64

ifeq ($(OS),Windows_NT)
	RM = cmd /C del /Q /F
else
	RM = rm -f
endif

all: $(BIN) $(LIB)

$(LIB): src\separan_core.o src\separan_lexer.o src\separan_files.o src\separan_runtime.o
	$(AR) rcs $@ src\separan_core.o src\separan_lexer.o src\separan_files.o src\separan_runtime.o

$(BIN): $(OBJ)
	$(CC) $(CFLAGS) -o $@ src\main.o $(LIB) -lm

$(ZIP): $(BIN) separan.cmd README.md build_portable_zip.py
	python build_portable_zip.py

$(TARBALL): $(BIN) README.md build_linux_tarball.py
	python build_linux_tarball.py

src/%.o: src/%.c include/separan_core.h include/separan_lexer.h include/separan_files.h include/separan_runtime.h
	$(CC) $(CFLAGS) -c $< -o $@

test: $(BIN)
	./$(BIN) testdata/hello.sep
	./$(BIN) --check testdata/hello.sep

library-test: $(LIB)
	$(CC) $(CFLAGS) -Iinclude -o test_library_api.exe test_library_api.c $(LIB)
	./test_library_api.exe
	$(CC) $(CFLAGS) -Iinclude -o test_lexer_api.exe test_lexer_api.c $(LIB)
	./test_lexer_api.exe
	$(CC) $(CFLAGS) -Iinclude -o test_runtime_api.exe test_runtime_api.c $(LIB) -lm
	./test_runtime_api.exe

zip: $(ZIP)
linux-tarball: $(TARBALL)

clean:
	$(RM) $(BIN) $(LIB) test_library_api.exe test_lexer_api.exe test_runtime_api.exe $(OBJ)
	python -c "import pathlib, shutil; root = pathlib.Path('dist'); portable = root / 'separan-portable'; linux = root / 'separan-linux-x86_64'; zip_archive = root / 'separan-portable.zip'; tgz = root / 'separan-linux-x86_64.tar.gz'; shutil.rmtree(portable, ignore_errors=True) if portable.exists() else None; shutil.rmtree(linux, ignore_errors=True) if linux.exists() else None; zip_archive.unlink() if zip_archive.exists() else None; tgz.unlink() if tgz.exists() else None"
