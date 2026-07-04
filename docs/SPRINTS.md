# Roadmap de 10 sprints — tor-session-manager

*Actualizado: 2026-07-04*

Este documento es la **fuente única de verdad** del roadmap y reemplaza a los archivos previos
(`/ROADMAP.md`, `/docs/ROADMAP.md`, `/FODA.md`, `/docs/FODA.md`), que quedaron duplicados y
contradictorios entre sí (llegaban a discrepar en algo tan básico como si el paquete estaba
publicado en PyPI).

## Foco

Dos ejes entrelazados:

1. **Saltar cualquier bloqueo** 🛡️
   - *Llegar a Tor bajo censura*: bridges y pluggable transports (obfs4, snowflake, meek).
   - *Esquivar bloqueos del destino*: exit nodes en listas negras, Cloudflare/CAPTCHA, selección de
     país de salida.
2. **Mejor calidad de conexión** ⚡
   - Medir y elegir circuitos rápidos.
   - Robustez / reintentos.
   - Concurrencia (async).

El orden es **fundación-primero**: cada sprint deja código utilizable con tests y construye sobre el
anterior. Primero *ver* y *medir* los circuitos para poder *elegirlos*; luego esquivar bloqueos del
destino; después la concurrencia; y como bloque autocontenido, la censura para llegar a Tor.

---

## Sprints

Leyenda: 🛡️ = saltar bloqueo · ⚡ = calidad de conexión.

### Sprint 1 — Robustez de base ⚡🛡️ ✅ (v1.1.0)
IP checkers con fallback, rotación verificable y reintentos.
- `ip_checkers.py`: varios endpoints (ipify, ifconfig.me, icanhazip, httpbin) con
  `fetch_ip_with_fallback()`.
- `get_ip()` usa el fallback en lugar de un único endpoint.
- `TorClient.wait_for_new_ip()`: rota hasta que la IP realmente cambie.
- Helper `_retry_with_backoff()` (backoff exponencial) reutilizable.
- Excepción `AllIPCheckersFailedError`.

### Sprint 2 — Introspección de circuitos ⚡🛡️ ✅ (v1.2.0)
- `get_circuit_info()` → circuito activo, fingerprints de los relays, nickname/IP del exit.
- `get_exit_country()` (GeoIP de stem).
- `list_circuits()`. Dataclasses `CircuitInfo` y `RelayInfo` en `circuits.py`.

### Sprint 3 — Medición de calidad de circuito ⚡ ✅ (v1.3.0)
- `measure_latency()` (mediana de N muestras) y `measure_throughput()` (KB/s) por el circuito.
- Dataclass `CircuitHealth` (latencia, throughput, samples, timestamp, `.ok`) en `quality.py`.
- `benchmark()` que combina ambas mediciones de forma tolerante a fallos.

### Sprint 4 — Selección de nodo de salida por país / a demanda 🛡️⚡ ✅ (v1.4.0)
- `new_circuit(exit_country=None, exit_fingerprint=None, verify=True)` vía `ExitNodes`/`StrictNodes`.
- `set_exit_country("us")`, `set_exit_nodes()`, `reset_exit_nodes()`, contextmanager `pinned_exit()`.
- Helpers puros en `exits.py`. Manejo de `StrictNodes` (país sin exits → `TorSessionError` claro).

### Sprint 5 — Pool de circuitos + "best circuit" ⚡ ✅ (v1.5.0)
- `CircuitPool` en `pool.py`: mantiene N lanes aislados por credencial SOCKS; `build()`,
  `benchmark()`, `ranked()`, `fastest()`, `pin_fastest()` (+ `pinned_proxies`).
- `drop(circuit)` y `prune(keep)` para descartar lentos/bloqueados. `TorClient.circuit_pool()`.

### Sprint 6 — Detección de bloqueo del destino + auto-rotación 🛡️
- Detección de respuesta bloqueada: 403/429, challenge de Cloudflare/CAPTCHA → `BlockedResponseError`.
- `is_exit_blocklisted()` (lista de exits Tor / DNSBL).
- `request_with_retry()` que rota a un exit nuevo cuando detecta bloqueo.

### Sprint 7 — Soporte async (`TorClientAsync`) ⚡
- `TorClientAsync` con `aiohttp` + SOCKS async; rotate/get_ip/benchmark async.
- Pool de circuitos concurrente para scraping paralelo.
- Dependencia opcional `[async]` en `pyproject.toml`.

### Sprint 8 — Censura: bridges + pluggable transports 🛡️
- Configuración de bridges y transports: obfs4, snowflake, meek.
- Lanzar un Tor propio con `stem.process.launch_tor_with_config` (Bridge + ClientTransportPlugin),
  además de configurar un Tor existente.
- `BridgeConfig` / validación de disponibilidad del binario del transport.

### Sprint 9 — Fingerprint de request + pacing adaptativo 🛡️⚡
- Rotación de User-Agent / perfiles de headers coherentes.
- Consideraciones de TLS/JA3 (documentar límites; ofrecer perfiles de headers).
- Rate limiting adaptativo (backoff ante 429, ritmo por host).

### Sprint 10 — CLI, observabilidad, integraciones y release ⚡🛡️
- CLI `tor-session` (rotate, ip, benchmark, circuit-info).
- Export de métricas/health (JSON / Prometheus-friendly).
- Integraciones: middleware Scrapy, fixture pytest.
- Docs (Sphinx), workflow de publicación a PyPI, `py.typed`, badges.

---

## Trazabilidad de los dos ejes

| Eje | Sprints |
|-----|---------|
| 🛡️ Saltar bloqueo — destino | 4, 6, 9 |
| 🛡️ Saltar bloqueo — llegar a Tor (censura) | 8 |
| ⚡ Calidad — medir/elegir circuito | 2, 3, 5 |
| ⚡ Calidad — robustez/reintentos | 1, 6 |
| ⚡ Calidad — concurrencia (async) | 7 |
| Productizar / release | 1 (docs), 10 |

---

## Estado

- **Sprint 1**: ✅ implementado en v1.1.0.
- **Sprint 2**: ✅ implementado en v1.2.0.
- **Sprint 3**: ✅ implementado en v1.3.0.
- **Sprint 4**: ✅ implementado en v1.4.0.
- **Sprint 5**: ✅ implementado en v1.5.0.
- **Sprints 6–10**: planificados.
