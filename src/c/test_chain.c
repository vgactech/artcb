#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "libartcb_chain.h"

int main(void) {
    char hash[ARTCB_HASH_HEX_LEN];
    char canonical[ARTCB_MAX_BODY];

    assert(artcb_sha256_hex("ARTCB", 5, hash) == 0);
    assert(strlen(hash) == 64);
    printf("sha256 ok: %s\n", hash);

    assert(
        artcb_build_canonical(0, "2026-07-04T23:00:00Z", "", "graph", "merkle", 0.81, canonical, sizeof(canonical))
        == 0
    );
    assert(artcb_hash_canonical(canonical, hash) == 0);
    printf("block hash ok: %s\n", hash);

    assert(artcb_hash_abi_version() == 2);

    {
        char v1[ARTCB_MAX_BODY];
        char v2empty[ARTCB_MAX_BODY];
        char v2root[ARTCB_MAX_BODY];
        char hash_v1[ARTCB_HASH_HEX_LEN];
        char hash_empty[ARTCB_HASH_HEX_LEN];
        char hash_root[ARTCB_HASH_HEX_LEN];
        char hash_tamper[ARTCB_HASH_HEX_LEN];
        const char *root = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        const char *tamper = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        assert(artcb_build_canonical(1, "ts", "p", "g", "m", 0.7, v1, sizeof(v1)) == 0);
        assert(artcb_build_canonical_v2(1, "ts", "p", "g", "m", 0.7, "", v2empty, sizeof(v2empty)) == 0);
        assert(artcb_build_canonical_v2(1, "ts", "p", "g", "m", 0.7, NULL, v2empty, sizeof(v2empty)) == 0);
        assert(strcmp(v1, v2empty) == 0);
        assert(artcb_build_canonical_v2(1, "ts", "p", "g", "m", 0.7, root, v2root, sizeof(v2root)) == 0);
        assert(strcmp(v1, v2root) != 0);
        assert(artcb_hash_canonical(v1, hash_v1) == 0);
        assert(artcb_hash_canonical(v2empty, hash_empty) == 0);
        assert(artcb_hash_canonical(v2root, hash_root) == 0);
        assert(strcmp(hash_v1, hash_empty) == 0);
        assert(strcmp(hash_v1, hash_root) != 0);
        assert(artcb_build_canonical_v2(1, "ts", "p", "g", "m", 0.7, tamper, v2root, sizeof(v2root)) == 0);
        assert(artcb_hash_canonical(v2root, hash_tamper) == 0);
        assert(strcmp(hash_root, hash_tamper) != 0);
        printf("economic_root v2 ok: empty==v1, tamper changes hash\n");
    }

    printf("all C tests passed\n");
    return 0;
}
