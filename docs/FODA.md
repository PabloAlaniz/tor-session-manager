# Análisis FODA - tor-session-manager

> ⚠️ **Supersedido.** El roadmap vigente vive en [`SPRINTS.md`](SPRINTS.md).

**Fecha:** 2026-02-22  
**Analista:** Margarita (AI)

---

## 🟢 Fortalezas

### Código
- **API limpia y Pythonic:** Context managers, type hints, docstrings completos
- **Principio de responsabilidad única:** Client separado de excepciones
- **Exceptions bien diseñadas:** Jerarquía clara con base class `TorSessionError`
- **Logging integrado:** Debug mode disponible para troubleshooting

### Arquitectura
- **Dependencia mínima:** Solo `stem` y `requests`, sin bloat
- **Configurable:** Puertos, passwords, delays son parámetros
- **Helpers útiles:** `rotate_and_get_ip()` one-liner, propiedad `proxies`
- **Context manager flexible:** `rotated_session()` para circuitos frescos

### Documentación
- **README excelente:** Ejemplos, troubleshooting, disclaimers legales
- **Docstrings completos:** Todas las clases y métodos documentados
- **Instalación clara:** Instrucciones para macOS, Linux, Windows

### Testing
- **CI configurado:** GitHub Actions con pytest
- **Tests existentes:** Base para agregar más coverage

---

## 🔴 Debilidades

### Distribución
- **No publicado en PyPI:** README dice `pip install tor-session-manager` pero no existe
- **Sin setup.py/pyproject.toml:** Falta configuración de empaquetado

### Funcionalidad
- **Solo IPv4:** No valida ni soporta IPv6
- **Un solo método de IP check:** Dependencia de api.ipify.org
- **Sin connection pooling:** Crea nueva sesión en cada llamada sin context manager

### Testing
- **Coverage desconocido:** No hay badge ni reporte
- **Sin tests de integración:** Los tests requieren Tor corriendo

### Seguridad
- **Cookie auth asumida:** Si falla, el error no es claro
- **Sin validación de IP:** Confía ciegamente en respuesta de ipify

---

## 🟡 Oportunidades

### Publicación
- **PyPI release:** Publicar en PyPI para cumplir la promesa del README
- **GitHub Releases:** Tags versionados con changelogs
- **Badges:** Coverage, PyPI version, downloads

### Mejoras técnicas
- **Async support:** `aiohttp` + `asyncio` para scraping concurrente
- **Connection pool:** Reutilizar conexiones entre requests
- **Multiple IP checkers:** Fallback si ipify falla (ifconfig.me, httpbin.org)
- **IPv6 support:** Validar y soportar ambos protocolos

### Features
- **Circuit info:** Exponer información del circuito actual (país de salida, etc.)
- **Wait for new IP:** Rotar hasta obtener IP diferente a la actual
- **Proxy chain:** Soporte para Tor → otro proxy

### Integraciones
- **Plugin para pytest:** Fixture que provee cliente Tor
- **Scrapy middleware:** Integración nativa con Scrapy
- **CLI tool:** Comando `tor-rotate` para uso en shell scripts

---

## 🔵 Amenazas

### Técnicas
- **Rate limits de Tor:** 10 rotaciones/min puede no ser suficiente
- **Cambios en stem:** Dependencia de librería de terceros
- **ipify downtime:** Single point of failure para get_ip()

### Legales
- **Mal uso:** La herramienta puede usarse para actividades no éticas
- **Responsabilidad:** README tiene disclaimer pero podría no ser suficiente

### Competencia
- **Alternativas existentes:** `torpy`, `requests-tor`, etc.
- **VPN services:** Para muchos casos, VPN es más simple que Tor

### Adopción
- **Nicho pequeño:** El público objetivo (scraping ético + Tor) es limitado
- **Sin publicar:** Nadie puede instalarlo sin clonar el repo

---

## 📊 Matriz de Prioridades

| Acción | Impacto | Esfuerzo | Prioridad |
|--------|---------|----------|-----------|
| Publicar en PyPI | Alto | Bajo | 🔴 Alta |
| Multiple IP checkers | Medio | Bajo | 🔴 Alta |
| Agregar más tests | Medio | Medio | 🟡 Media |
| Async support | Alto | Alto | 🟡 Media |
| CLI tool | Bajo | Medio | 🟢 Baja |

---

## 🎯 Recomendación Principal

**Prioridad #1:** Publicar en PyPI. El README promete `pip install tor-session-manager` que actualmente no funciona. Esto es confuso para usuarios y daña credibilidad.

**Pasos:**
1. Crear `pyproject.toml` con metadata
2. Configurar GitHub Actions para publish automático
3. Primer release como v0.1.0

**Quick win:** Agregar fallback IP checkers para mayor robustez.
