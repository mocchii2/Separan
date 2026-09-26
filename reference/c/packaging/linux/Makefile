PREFIX ?= /usr/local
BINDIR ?= $(PREFIX)/bin
DESTDIR ?=
INSTALL ?= install
PROGRAMS = $(wildcard separan separan-gw)
CORE_SOURCES := src/separan_core.c src/separan_lexer.c src/separan_files.c src/separan_runtime.c
GW_SOURCES := src/separan_gw.c src/separan_gw_fastcgi.c src/separan_gw_supervisor.c
CFLAGS ?= -O1 -std=c11 -Wall -Wextra

ifneq ($(wildcard src/separan_core.c),)
.PHONY: all
all: separan separan-gw

separan: src/main.c $(CORE_SOURCES)
	$(CC) $(CFLAGS) -I include $^ -lm -o $@

separan-gw: $(GW_SOURCES) $(CORE_SOURCES)
	$(CC) $(CFLAGS) -I include $^ -lm -o $@
else
.PHONY: all
all:
	@test -n "$(PROGRAMS)" || { echo "No Separan binaries or source tree found." >&2; exit 1; }
endif

.PHONY: install clean

install: all
	@test -n "$(PROGRAMS)" || { echo "No Separan binaries found in this directory." >&2; exit 1; }
	$(INSTALL) -d "$(DESTDIR)$(BINDIR)"
	@for binary in $(PROGRAMS); do $(INSTALL) -m 0755 "$$binary" "$(DESTDIR)$(BINDIR)/$$binary"; done

clean:
	rm -f separan separan-gw