# Política de Seguridad

## Versiones soportadas

Solo la última versión menor recibe correcciones de seguridad.

| Versión | Soportada |
| ------- | --------- |
| 1.10.x  | ✅        |
| < 1.10  | ❌        |

## Cómo reportar una vulnerabilidad

**No abras un issue público** para reportar vulnerabilidades.

Usá alguna de estas vías privadas:

1. **GitHub (preferida):** pestaña *Security* → [**Report a vulnerability**](https://github.com/PabloAlaniz/tor-session-manager/security/advisories/new).
2. **Email:** pablo@culturainteractiva.com con el asunto `[SECURITY] tor-session-manager`.

Incluí, en lo posible:

- Versión de la librería, de Python y de Tor, y sistema operativo.
- Descripción del problema y su impacto.
- Pasos para reproducirlo o una prueba de concepto mínima.
- Si tenés una propuesta de fix, bienvenida.

## Qué esperar

- **Acuse de recibo:** dentro de los 5 días hábiles.
- **Evaluación inicial:** dentro de los 14 días, con confirmación (o no) del problema y un plan.
- **Corrección:** según la severidad. Se publica una versión nueva en PyPI y un advisory en GitHub, con crédito a quien lo reportó si así lo desea.

Pedimos no divulgar públicamente el problema hasta que haya una versión corregida disponible.

## Alcance

Están dentro del alcance los problemas de **esta librería**, por ejemplo:

- Tráfico (requests, DNS) que sale por fuera del proxy SOCKS cuando la librería indica que va por Tor.
- Exposición o manejo inseguro de credenciales del ControlPort (password, cookie).
- Ejecución de código o lectura de archivos no intencionada a partir de input controlado por un tercero.
- Fallas en las políticas de enrutamiento que filtren la IP real.

Quedan **fuera** del alcance:

- Limitaciones inherentes de Tor o del protocolo (correlación de tráfico, nodos de salida maliciosos, etc.).
- Vulnerabilidades en Tor, `stem`, `requests`, `PySocks` u otras dependencias: reportalas a sus proyectos (avisanos si nos afectan de forma particular).
- Configuraciones inseguras del usuario (por ejemplo, ControlPort expuesto a la red sin autenticación).
