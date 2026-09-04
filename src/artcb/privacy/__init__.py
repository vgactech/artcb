"""Module privacy ARTCB — Confidentialité homomorphe pour apprentissage et minage partagés.

Principe :
    Chaque participant peut contribuer à l'apprentissage/minage partagé
    SANS jamais révéler ses données brutes. Les vecteurs IR PoL sont
    chiffrés avec le schéma CKKS (TenSEAL) avant d'être envoyés au pool.
    L'orchestrateur agrège les chiffrés homomorphiquement (addition vectorielle)
    et le résultat agrégé est gravé dans ARTCB.

Activation :
    ARTCB_HOMOMORPHIC_MODE=true   → chiffrement actif
    ARTCB_HOMOMORPHIC_MODE=false  → mode classique (défaut)

Schéma HE utilisé :
    CKKS (Cheon-Kim-Kim-Song) — adapté aux vecteurs de flottants
    Compatible avec les vecteurs de graphes IR PoL d'ARTCB

Fallback :
    Si TenSEAL n'est pas installé, le module fonctionne en mode
    simulé (chiffrement XOR + bruit gaussien) pour les tests.
    Pour la production : pip install tenseal

Deuxième couche (rapport 211, distincte de HE) :
    `egress` — politique déterministe sur les octets sortants d'un nœud
    (webhooks, prompts connecteurs LLM). Redact par défaut, block si PEM.
    Ne remplace pas HE ; ne touche pas au consensus ni aux mémos gravés.
"""

from .homomorphic import HEContext, HomomorphicProcessor, HECipherVector
from .federated import FederatedAggregator, FederatedRound

__all__ = [
    "HEContext",
    "HomomorphicProcessor",
    "HECipherVector",
    "FederatedAggregator",
    "FederatedRound",
]
