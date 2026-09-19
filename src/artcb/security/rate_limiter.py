"""
Rate Limiter — Protection contre spam et abus API

Implémente :
1. Token bucket algorithm (requêtes/seconde)
2. Sliding window (requêtes/minute)
3. IP-based limiting
4. Address-based limiting (wallet)
"""

MODULE_VERSION = '1.0.0'  # R390 — auto-versioning
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    """Token bucket pour rate limiting"""
    capacity: int
    refill_rate: float  # tokens par seconde
    tokens: float
    last_refill: float

    def consume(self, tokens: int = 1) -> bool:
        """
        Consomme des tokens

        Args:
            tokens: Nombre de tokens à consommer

        Returns:
            True si tokens disponibles, False sinon
        """
        now = time.time()
        elapsed = now - self.last_refill

        # Refill tokens
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate
        )
        self.last_refill = now

        # Consommer
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimiter:
    """
    Rate limiter multi-niveaux pour API ARTCB

    Limites par défaut :
    - Global : 1000 req/min
    - Par IP : 100 req/min
    - Par adresse wallet : 10 blocs/min
    - Encodage : 5 req/min par IP
    """

    def __init__(
        self,
        global_limit: int = 1000,
        ip_limit: int = 100,
        address_limit: int = 10,
        encode_limit: int = 5,
        window_seconds: int = 60
    ):
        self.global_limit = global_limit
        self.ip_limit = ip_limit
        self.address_limit = address_limit
        self.encode_limit = encode_limit
        self.window_seconds = window_seconds

        # Token buckets
        self.global_bucket = TokenBucket(
            capacity=global_limit,
            refill_rate=global_limit / window_seconds,
            tokens=global_limit,
            last_refill=time.time()
        )

        # Sliding windows par IP
        self.ip_windows: dict[str, deque] = defaultdict(lambda: deque())

        # Sliding windows par adresse
        self.address_windows: dict[str, deque] = defaultdict(lambda: deque())

        # Sliding windows encodage par IP
        self.encode_windows: dict[str, deque] = defaultdict(lambda: deque())

        logger.info(
            f"RateLimiter initialized: global={global_limit}/min, "
            f"ip={ip_limit}/min, address={address_limit}/min, "
            f"encode={encode_limit}/min"
        )

    def check_global(self) -> tuple[bool, str | None]:
        """
        Vérifie limite globale

        Returns:
            (allowed, reason) — True si autorisé, sinon (False, raison)
        """
        if not self.global_bucket.consume():
            reason = f"Global rate limit exceeded: {self.global_limit} req/min"
            logger.warning(reason)
            return False, reason
        return True, None

    def check_ip(self, ip: str) -> tuple[bool, str | None]:
        """
        Vérifie limite par IP

        Args:
            ip: Adresse IP

        Returns:
            (allowed, reason) — True si autorisé, sinon (False, raison)
        """
        now = time.time()
        window = self.ip_windows[ip]

        # Nettoyer fenêtre (supprimer requêtes > window_seconds)
        while window and now - window[0] > self.window_seconds:
            window.popleft()

        # Vérifier limite
        if len(window) >= self.ip_limit:
            reason = f"IP rate limit exceeded for {ip}: {self.ip_limit} req/min"
            logger.warning(reason)
            return False, reason

        # Ajouter requête
        window.append(now)
        return True, None

    def check_address(self, address: str) -> tuple[bool, str | None]:
        """
        Vérifie limite par adresse wallet

        Args:
            address: Adresse wallet ARTCB

        Returns:
            (allowed, reason) — True si autorisé, sinon (False, raison)
        """
        now = time.time()
        window = self.address_windows[address]

        # Nettoyer fenêtre
        while window and now - window[0] > self.window_seconds:
            window.popleft()

        # Vérifier limite
        if len(window) >= self.address_limit:
            reason = f"Address rate limit exceeded for {address[:12]}...: {self.address_limit} blocks/min"
            logger.warning(reason)
            return False, reason

        # Ajouter requête
        window.append(now)
        return True, None

    def check_encode(self, ip: str) -> tuple[bool, str | None]:
        """
        Vérifie limite encodage par IP (opération coûteuse)

        Args:
            ip: Adresse IP

        Returns:
            (allowed, reason) — True si autorisé, sinon (False, raison)
        """
        now = time.time()
        window = self.encode_windows[ip]

        # Nettoyer fenêtre
        while window and now - window[0] > self.window_seconds:
            window.popleft()

        # Vérifier limite
        if len(window) >= self.encode_limit:
            reason = f"Encode rate limit exceeded for {ip}: {self.encode_limit} req/min"
            logger.warning(reason)
            return False, reason

        # Ajouter requête
        window.append(now)
        return True, None

    def check_all(
        self,
        ip: str | None = None,
        address: str | None = None,
        is_encode: bool = False
    ) -> tuple[bool, str | None]:
        """
        Vérifie toutes les limites applicables

        Args:
            ip: Adresse IP (optionnel)
            address: Adresse wallet (optionnel)
            is_encode: True si opération encodage

        Returns:
            (allowed, reason) — True si autorisé, sinon (False, raison)
        """
        # Global
        allowed, reason = self.check_global()
        if not allowed:
            return False, reason

        # IP
        if ip:
            allowed, reason = self.check_ip(ip)
            if not allowed:
                return False, reason

            # Encodage
            if is_encode:
                allowed, reason = self.check_encode(ip)
                if not allowed:
                    return False, reason

        # Adresse
        if address:
            allowed, reason = self.check_address(address)
            if not allowed:
                return False, reason

        return True, None

    def reset_ip(self, ip: str):
        """Reset compteurs pour une IP"""
        if ip in self.ip_windows:
            del self.ip_windows[ip]
        if ip in self.encode_windows:
            del self.encode_windows[ip]
        logger.info(f"Rate limits reset for IP {ip}")

    def reset_address(self, address: str):
        """Reset compteurs pour une adresse"""
        if address in self.address_windows:
            del self.address_windows[address]
        logger.info(f"Rate limits reset for address {address[:12]}...")

    def get_stats(self) -> dict:
        """Retourne statistiques rate limiting"""
        return {
            "global_tokens": self.global_bucket.tokens,
            "global_capacity": self.global_bucket.capacity,
            "tracked_ips": len(self.ip_windows),
            "tracked_addresses": len(self.address_windows),
            "tracked_encode_ips": len(self.encode_windows)
        }

