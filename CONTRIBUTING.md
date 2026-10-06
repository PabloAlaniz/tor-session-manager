# Cómo contribuir

¡Gracias por querer mejorar **tor-session-manager**! Esta guía explica cómo reportar problemas, proponer cambios y preparar un pull request.

Al participar aceptás el [Código de Conducta](CODE_OF_CONDUCT.md).

## Antes de empezar

- **Bugs:** abrí un issue con el formulario [Reporte de bug](https://github.com/PabloAlaniz/tor-session-manager/issues/new?template=bug_report.yml). Incluí la salida de `tor-session status`: resuelve la mitad de los diagnósticos.
- **Ideas o features:** abrí un issue con el formulario [Propuesta de feature](https://github.com/PabloAlaniz/tor-session-manager/issues/new?template=feature_request.yml) antes de escribir código grande, así acordamos el enfoque.
- **Vulnerabilidades:** **no** abras un issue público. Seguí la [Política de Seguridad](SECURITY.md).
- Buscá primero entre los [issues existentes](https://github.com/PabloAlaniz/tor-session-manager/issues) para no duplicar.

### Alcance del proyecto

La librería existe para usos legítimos (scraping ético, investigación, testing de privacidad, pentesting autorizado; ver el README). No se aceptan cambios cuyo propósito principal sea evadir controles de seguridad con fines abusivos, saltear autenticación o facilitar ataques a terceros.

## Entorno de desarrollo

Requisitos: Python 3.9 o superior y git.

```bash
git clone https://github.com/<tu-usuario>/tor-session-manager.git
cd tor-session-manager
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -e ".[dev,async]"
```

**No hace falta tener Tor corriendo para los tests:** el controller, el proxy y la red están mockeados. Tor solo es necesario para probar a mano contra la red real (ver *Prerequisitos* en el README).

## Checks locales

Son los mismos que corre la CI (`.github/workflows/ci.yml`, Python 3.9 a 3.12):

```bash
pytest --cov=tor_session_manager --cov-report=term-missing   # tests
black tor_session_manager tests                              # formato
isort tor_session_manager tests                              # orden de imports
mypy tor_session_manager                                     # tipos
```

## Convenciones

- **Ramas:** creá una rama desde `main` con un nombre descriptivo (`fix/rotacion-timeout`, `feat/pool-async`, `docs/...`).
- **Commits:** mensajes claros que expliquen el *por qué*, no solo el *qué*.
- **Tests:** todo código nuevo o bug corregido viene con su test en `tests/`. Si arreglás un bug, el test debería fallar sin tu fix.
- **Compatibilidad:** el código tiene que funcionar en Python 3.9 (nada de `match`, `X | Y` en anotaciones evaluadas en runtime, etc.).
- **Dependencias:** evitá sumar dependencias obligatorias; si son necesarias, que sean un extra opcional en `pyproject.toml` (como `async`).
- **API pública:** si cambiás o agregás algo de la API o de la CLI, actualizá el README en el mismo PR. Evitá romper compatibilidad; si es inevitable, explicalo en el PR.
- **Idioma:** la documentación y los issues van en español; el código, los nombres y los docstrings, en inglés (como el resto del repo).

## Pull requests

1. Hacé fork y trabajá en una rama propia.
2. Corré los checks locales.
3. Abrí el PR contra `main` completando el template.
4. La CI tiene que pasar en verde. Puede haber pedidos de cambios en la revisión: es parte normal del proceso.

PRs chicos y enfocados se revisan más rápido que uno grande que toca muchas cosas.

## Releases

Las hace el maintainer: se sube la versión en `pyproject.toml` y en `tor_session_manager/__init__.py`, se mergea a `main` y se publica un GitHub Release; el workflow `publish.yml` sube el paquete a PyPI. No hace falta que bumpees la versión en tu PR.

## ¿Dudas?

Abrí un issue con la pregunta. ¡Gracias por contribuir! 🧅
