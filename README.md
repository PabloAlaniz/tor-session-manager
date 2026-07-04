# 🧅 Tor Session Manager

Una librería Python liviana para gestionar sesiones Tor y rotar circuitos programáticamente.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 Casos de Uso

Esta librería está diseñada para propósitos **legítimos**:

- **Web Scraping Ético**: Rotar IPs para respetar rate limits mientras recolectás datos que tenés autorización para acceder
- **Investigación de Seguridad**: Testear cómo tus aplicaciones manejan requests desde diferentes ubicaciones geográficas
- **Testing de Privacidad**: QA para aplicaciones enfocadas en privacidad y sistemas de detección de VPN/proxy
- **Investigación Académica**: Estudiar comportamiento de redes, patrones de censura o características de la red Tor
- **Penetration Testing**: Evaluaciones de seguridad autorizadas que requieren rotación de IP

> ⚠️ **Aviso de Responsabilidad**: Siempre respetá `robots.txt`, términos de servicio y rate limits. Esta herramienta es solo para uso legítimo. El autor no se responsabiliza por mal uso.

## 📦 Instalación

```bash
pip install tor-session-manager
```

### Prerequisitos

Necesitás Tor corriendo localmente con el puerto de control habilitado:

**macOS (Homebrew):**
```bash
brew install tor
# Editá /opt/homebrew/etc/tor/torrc y agregá:
#   ControlPort 9051
#   CookieAuthentication 1
brew services start tor
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install tor
# Editá /etc/tor/torrc y descomentá/agregá:
#   ControlPort 9051
#   CookieAuthentication 1
sudo systemctl restart tor
```

**Windows:**
Descargá desde [torproject.org](https://www.torproject.org/download/) y configurá `torrc`.

## 🚀 Inicio Rápido

### Uso Básico

```python
from tor_session_manager import TorClient

with TorClient() as client:
    print(f"IP actual: {client.get_ip()}")
    
    client.rotate()  # Obtener nuevo circuito
    
    print(f"Nueva IP: {client.get_ip()}")
```

### One-liner

```python
from tor_session_manager import rotate_and_get_ip

nueva_ip = rotate_and_get_ip()
print(f"Nueva IP: {nueva_ip}")
```

### Con Requests

```python
import requests
from tor_session_manager import TorClient

client = TorClient()

# Usá la propiedad proxies con cualquier llamada de requests
response = requests.get(
    "https://httpbin.org/ip",
    proxies=client.proxies,
    timeout=30
)
print(response.json())
```

### Scraping con Rotación

```python
import time
import requests
from tor_session_manager import TorClient

def scrape_con_rotacion(urls: list[str], delay: float = 1.0):
    """Scrapear URLs con rotación automática de IP y rate limiting."""
    resultados = []
    
    with TorClient() as client:
        for i, url in enumerate(urls):
            # Rotar cada 10 requests
            if i > 0 and i % 10 == 0:
                client.rotate()
                print(f"Rotado a nueva IP: {client.get_ip()}")
            
            # Delay respetuoso entre requests
            time.sleep(delay)
            
            response = requests.get(url, proxies=client.proxies, timeout=30)
            resultados.append(response.text)
    
    return resultados
```

## 📖 Referencia de API

### TorClient

```python
TorClient(
    control_port: int = 9051,    # Puerto de control de Tor
    socks_port: int = 9050,      # Puerto proxy SOCKS de Tor  
    password: str = None,        # Password del puerto de control (si no usás cookie auth)
    rotate_delay: float = 2.0,   # Segundos de espera después de rotar
)
```

**Métodos:**

| Método | Descripción |
|--------|-------------|
| `is_ready()` | Verificar si Tor está corriendo y bootstrapped |
| `rotate()` | Solicitar nuevo circuito (nueva IP de salida) |
| `get_ip()` | Obtener IP pública actual a través de Tor (con fallback entre varios servicios) |
| `wait_for_new_ip(previous_ip=None, max_attempts=5)` | Rotar hasta que la IP de salida realmente cambie |
| `proxies` | Propiedad que devuelve dict de proxy para requests |

> 💡 **Rotación verificada:** `rotate()` a veces reutiliza el mismo nodo de salida, así que la IP puede
> no cambiar. `wait_for_new_ip()` rota repetidamente hasta observar una IP distinta (o agotar
> `max_attempts`), útil cuando necesitás garantizar un exit nuevo entre requests.

```python
with TorClient() as client:
    ip_vieja = client.get_ip()
    ip_nueva = client.wait_for_new_ip(previous_ip=ip_vieja)
    print(f"{ip_vieja} -> {ip_nueva}")
```

> 🔁 **IP checkers con fallback:** `get_ip()` prueba varios servicios en orden
> (ipify, ifconfig.me, icanhazip, httpbin), de modo que la caída de uno solo no rompe la resolución
> de IP. Si todos fallan levanta `AllIPCheckersFailedError`.

**Context Managers:**

```python
# Uso estándar - verifica que Tor esté listo
with TorClient() as client:
    ...

# Rotar antes de una operación específica
with client.rotated_session():
    # Circuito fresco para este bloque
    ...
```

### Excepciones

| Excepción | Descripción |
|-----------|-------------|
| `TorSessionError` | Excepción base |
| `TorConnectionError` | No se puede conectar al controlador de Tor |
| `TorNotReadyError` | Tor no está completamente bootstrapped |
| `IPFetchError` | No se puede determinar la IP pública |
| `AllIPCheckersFailedError` | Fallaron todos los servicios de checkeo de IP (subclase de `IPFetchError`) |

## ⚙️ Cómo Funciona

Esta librería actúa como un puente entre tu código Python y la red Tor:

```
Tu código  →  TorClient  →  Tor Proxy (SOCKS5)  →  Internet
                   ↕
            Controlador Tor
           (rotación de circuitos)
```

### Componentes

1. **Proxy SOCKS5** (puerto 9050): Tu tráfico HTTP/HTTPS pasa por acá para salir a través de Tor
2. **Puerto de Control** (puerto 9051): Permite enviar comandos a Tor (como rotar circuitos)
3. **TorClient**: Maneja la autenticación y envía señales al controlador

### Flujo de Rotación

1. Se envía señal `NEWNYM` al puerto de control de Tor
2. Tor construye un nuevo circuito con diferentes nodos relay
3. Se espera `rotate_delay` segundos (por defecto 2s) para que el circuito se establezca
4. Las próximas requests usarán el nuevo circuito → nueva IP de salida

### Limitaciones

- **Rate limits de Tor**: No podés rotar circuitos instantáneamente. Tor tiene límites (~10 rotaciones/min)
- **Velocidad**: Tor es más lento que una conexión directa (3+ saltos en la red)
- **Misma IP posible**: Ocasionalmente podés obtener la misma IP después de rotar (aunque es poco probable)

## 🔧 Configuración

### Puertos Personalizados

```python
client = TorClient(
    control_port=9151,  # Puerto de control no estándar
    socks_port=9150,    # Puerto SOCKS no estándar
)
```

### Autenticación por Password

Si usás password auth en lugar de cookie auth:

```python
client = TorClient(password="tu_password_de_control")
```

### Logging

Habilitá debug logging para ver qué está pasando:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🧪 Testeando tu Setup

```python
from tor_session_manager import TorClient

client = TorClient()

if client.is_ready():
    print("✅ Tor está corriendo y listo")
    with client:
        print(f"📍 Tu IP de Tor: {client.get_ip()}")
else:
    print("❌ Tor no está listo - verificá la instalación")
```

## 🔍 Troubleshooting

### "TorConnectionError: Failed to connect to Tor controller"

**Causas comunes:**
- Tor no está corriendo → `brew services start tor` (macOS) o `sudo systemctl start tor` (Linux)
- Puerto de control no habilitado → agregá `ControlPort 9051` en `torrc`
- Firewall bloqueando conexión local

**Verificar:**
```bash
# Verificar si Tor está corriendo
ps aux | grep tor

# En Linux, verificar status
sudo systemctl status tor
```

### "TorNotReadyError: Tor is not fully bootstrapped"

Tor puede tardar unos segundos en conectarse a la red. Esperá ~10-15 segundos después de iniciar Tor antes de usar la librería.

**Verificar status:**
```python
from tor_session_manager import TorClient

client = TorClient()
if client.is_ready():
    print("✅ Listo")
else:
    print("❌ Esperá un momento y volvé a intentar")
```

### "IPFetchError: Failed to fetch IP address"

**Causas:**
- Tor no está ruteando el tráfico correctamente
- Problema de conectividad general
- Sitio de verificación de IP bloqueado

**Solución:**
1. Verificá que Tor esté corriendo
2. Probá manualmente: `curl --proxy socks5h://127.0.0.1:9050 https://api.ipify.org`
3. Si falla, verificá la configuración de Tor

### Puertos personalizados no funcionan

Si cambiaste los puertos en `torrc`, asegurate de reiniciar Tor:

```bash
# macOS
brew services restart tor

# Linux
sudo systemctl restart tor
```

### La rotación no cambia la IP

Esto puede pasar ocasionalmente. Tor tiene un pool finito de nodos de salida y puede asignarte el mismo. Intentá rotar nuevamente o esperá unos segundos.

### Logging para debugging

Habilitá logs detallados para ver qué está pasando:

```python
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## 🤝 Contribuciones

¡Las contribuciones son bienvenidas! Sentite libre de abrir issues y pull requests.

## 📄 Licencia

MIT License - ver [LICENSE](LICENSE) para detalles.

## 👤 Autor

**Pablo Alaniz** - [@PabloAlaniz](https://github.com/PabloAlaniz)

---

*Construido para la comunidad de investigación de seguridad e ingeniería de datos* 🔐
