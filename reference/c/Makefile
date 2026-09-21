CC = gcc
CFLAGS = -std=c11 -Wall -Wextra -Iinclude
BIN = separan.exe
OBJ = src\main.o src\separan_core.o
ZIP = dist\separan-portable.zip
TARBALL = dist\separan-linux-x86_64.tar.gz
PORTABLE_DIR = dist\separan-portable
LINUX_DIR = dist\separan-linux-x86_64

ifeq ($(OS),Windows_NT)
	RM = cmd /C del /Q /F
else
	RM = rm -f
endif

all: $(BIN)

$(BIN): $(OBJ)
	$(CC) $(CFLAGS) -o $@ $(OBJ)

$(ZIP): $(BIN) separan.cmd README.md build_portable_zip.py
	python build_portable_zip.py

$(TARBALL): $(BIN) README.md build_linux_tarball.py
	python build_linux_tarball.py

src/%.o: src/%.c include/separan_core.h
	$(CC) $(CFLAGS) -c $< -o $@

test: $(BIN)
	./$(BIN) testdata/hello.sep

zip: $(ZIP)
linux-tarball: $(TARBALL)

clean:
	$(RM) $(BIN) $(OBJ)
	python -c "import pathlib, shutil; root = pathlib.Path('dist'); portable = root / 'separan-portable'; linux = root / 'separan-linux-x86_64'; zip_archive = root / 'separan-portable.zip'; tgz = root / 'separan-linux-x86_64.tar.gz'; shutil.rmtree(portable, ignore_errors=True) if portable.exists() else None; shutil.rmtree(linux, ignore_errors=True) if linux.exists() else None; zip_archive.unlink() if zip_archive.exists() else None; tgz.unlink() if tgz.exists() else None"
