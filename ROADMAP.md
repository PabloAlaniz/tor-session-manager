# ROADMAP - tor-session-manager

> ⚠️ **Supersedido.** Este roadmap quedó obsoleto y contradictorio con otros archivos de planificación.
> La fuente única de verdad es ahora [`docs/SPRINTS.md`](docs/SPRINTS.md).

*Actualizado: 2025-02-19*

## ✅ Completado

- [x] Core functionality (TorClient, rotate, get_ip)
- [x] Context managers
- [x] Exceptions hierarchy
- [x] Unit tests con pytest
- [x] CI con GitHub Actions
- [x] Documentación completa en español
- [x] Publicación en PyPI v1.0.0

## 🎯 v1.1.0 - Mejoras de calidad

| Tarea | Prioridad | Esfuerzo |
|-------|-----------|----------|
| Agregar archivo LICENSE (MIT) | Alta | 5 min |
| Agregar `py.typed` marker | Media | 5 min |
| Agregar badges (CI, PyPI, coverage) | Media | 10 min |
| Coverage report a codecov/coveralls | Baja | 30 min |

## 🚀 v1.2.0 - Nuevas features

| Tarea | Prioridad | Esfuerzo |
|-------|-----------|----------|
| Carpeta `examples/` con scripts demo | Media | 1h |
| docker-compose con Tor preconfigurado | Media | 2h |
| Soporte para múltiples instancias Tor | Baja | 4h |
| Métricas de rotación (tiempo, éxito) | Baja | 2h |

## 🔮 Futuro (evaluar demanda)

- **Async support**: Versión con `aiohttp` + `aiosocks` para concurrencia
- **Circuit pinning**: Mantener el mismo circuito para una sesión específica
- **Exit node selection**: Elegir país del nodo de salida
- **Health monitoring**: Endpoint para verificar salud del circuito

## 📝 Marketing

- [ ] Escribir artículo de Medium sobre scraping ético con Tor
- [ ] Anunciar en r/Python y r/webscraping
- [ ] Agregar al awesome-python-scraping

---

*El paquete está funcional y publicado. Las mejoras son incrementales.*
