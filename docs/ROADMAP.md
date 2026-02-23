# Roadmap - tor-session-manager

**Última actualización:** 2026-02-22

---

## 🎯 Visión

Librería de referencia en Python para gestión de sesiones Tor, publicada en PyPI con excelente documentación y soporte para casos de uso modernos (async, scraping frameworks).

---

## Fase 1: Release inicial (Inmediato)

### 1.1 Empaquetado
- [ ] **Crear pyproject.toml** con metadata completa
- [ ] **Configurar GitHub Actions** para publish a PyPI
- [ ] **Primer release v0.1.0** en PyPI y GitHub Releases
- [ ] **Actualizar README** con badge de PyPI

### 1.2 Robustez
- [ ] **Multiple IP checkers**: Fallback a ifconfig.me, httpbin.org/ip
- [ ] **Timeout configurable** para get_ip()
- [ ] **Retry en get_ip()** si primer intento falla

### 1.3 Testing
- [ ] **Aumentar coverage** a 80%+
- [ ] **Badge de coverage** en README
- [ ] **Mock de Tor** para tests sin Tor real

---

## Fase 2: Features avanzados (Q2 2026)

### 2.1 Async support
- [ ] **TorClientAsync** con aiohttp
- [ ] **Async context manager**
- [ ] **Ejemplos de uso** con asyncio

### 2.2 Circuit info
- [ ] **get_exit_country()**: País del nodo de salida
- [ ] **get_circuit_info()**: Detalles del circuito actual
- [ ] **wait_for_new_ip()**: Rotar hasta obtener IP diferente

### 2.3 Integraciones
- [ ] **pytest-tor-session**: Fixture para tests
- [ ] **Scrapy middleware**: TorRotateMiddleware

---

## Fase 3: Ecosistema (Q3-Q4 2026)

### 3.1 CLI
- [ ] **Comando tor-session**: Uso desde terminal
- [ ] **tor-session rotate**: Rotar y mostrar nueva IP
- [ ] **tor-session check**: Verificar estado de Tor

### 3.2 Documentación
- [ ] **Sphinx docs** en Read the Docs
- [ ] **Ejemplos completos** para casos de uso comunes
- [ ] **Blog post** sobre scraping ético

### 3.3 Comunidad
- [ ] **Issue templates** para bugs y features
- [ ] **Contributing guide**
- [ ] **Code of conduct**

---

## 📋 Backlog técnico

| Tarea | Prioridad | Estimación |
|-------|-----------|------------|
| pyproject.toml + PyPI | Alta | 1h |
| Multiple IP checkers | Alta | 30min |
| Badge de coverage | Media | 30min |
| Async client | Media | 4h |
| pytest plugin | Baja | 2h |
| CLI tool | Baja | 3h |

---

## 🚫 Out of scope (por ahora)

- GUI/Desktop app
- Proxy chain (Tor → otro proxy)
- Hidden services (.onion)
- Mobile support

---

## 📝 Notas de decisiones

### ¿Por qué stem?
- Librería oficial de Tor Project
- Mantenida activamente
- API estable y bien documentada

### ¿Por qué no torpy?
- torpy incluye su propio Tor, más pesado
- Queremos usar Tor del sistema para control
- stem es más liviana y flexible

### ¿Por qué socks5h?
- La "h" significa que DNS se resuelve por Tor
- Sin ella, DNS leakea la IP real
- Es el modo correcto para anonimato

### Versioning
- Seguimos SemVer (MAJOR.MINOR.PATCH)
- Breaking changes incrementan MAJOR
- v0.x.x significa API no estable aún
