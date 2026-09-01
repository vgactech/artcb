CC ?= cc
CFLAGS ?=
CFLAGS += -Wall -Wextra -O2 -fPIC
LDFLAGS ?=
LDLIBS ?= -lcrypto

TARGET = libartcb_chain.so
SRC = libartcb_chain.c

.PHONY: all clean test replit ci

all: $(TARGET)

$(TARGET): $(SRC) libartcb_chain.h
	$(CC) $(CFLAGS) $(LDFLAGS) -shared $(SRC) -o $(TARGET) $(LDLIBS)

# ── Replit / NixOS : utiliser le compilateur système avec chemins explicites
# Le linker Nix (binutils) est incompatible avec certains .so du store.
# On passe OpenSSL système en chemin absolu.
replit:
	@echo "Compilation libartcb_chain.so (Replit/NixOS)..."
	@CC_BIN=$$(command -v cc || command -v gcc || echo ""); \
	if [ -z "$$CC_BIN" ]; then echo "Compilateur C non trouvé"; exit 1; fi; \
	OPENSSL_LIB=$$(ls /lib/x86_64-linux-gnu/libcrypto.so.3 2>/dev/null || \
	               find /nix/store -name 'libcrypto.so' 2>/dev/null | head -1); \
	OPENSSL_INC=$$(ls -d /usr/include/openssl 2>/dev/null | head -1 | xargs dirname); \
	if [ -z "$$OPENSSL_LIB" ]; then echo "OpenSSL non trouvé"; exit 1; fi; \
	$$CC_BIN -Wall -O2 -fPIC -I"$$OPENSSL_INC" \
	  $(SRC) -o $(TARGET) -shared "$$OPENSSL_LIB" \
	  && echo "✅ $(TARGET) compilé" || (echo "❌ Compilation échouée"; exit 1)

# ── CI : même que all mais avec liboqs optionnel
ci:
	$(CC) $(CFLAGS) $(LDFLAGS) -shared $(SRC) -o $(TARGET) $(LDLIBS) 2>/dev/null || \
	$(CC) $(CFLAGS) $(SRC) -o $(TARGET) -shared 2>/dev/null || \
	echo "WARN: libartcb_chain.so non compilé (mode fallback Python)"

clean:
	rm -f $(TARGET)

test: $(TARGET)
	$(CC) $(CFLAGS) test_chain.c $(SRC) -o test_chain -lcrypto
	./test_chain
