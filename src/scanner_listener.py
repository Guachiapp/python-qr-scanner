"""Módulo que encapsula la lógica de escucha del dispositivo scanner QR."""

from typing import NoReturn, List
import evdev
from evdev import ecodes
import jwt
import RPi.GPIO as GPIO
import time
import threading


class ScannerListener:
    """Servicio que escucha continuamente las lecturas de múltiples scanners QR."""
    STRING_KEY_MAP = {
        'KEY_A': 'a', 'KEY_B': 'b', 'KEY_C': 'c', 'KEY_D': 'd',
        'KEY_E': 'e', 'KEY_F': 'f', 'KEY_G': 'g', 'KEY_H': 'h',
        'KEY_I': 'i', 'KEY_J': 'j', 'KEY_K': 'k', 'KEY_L': 'l',
        'KEY_M': 'm', 'KEY_N': 'n', 'KEY_O': 'o', 'KEY_P': 'p',
        'KEY_Q': 'q', 'KEY_R': 'r', 'KEY_S': 's', 'KEY_T': 't',
        'KEY_U': 'u', 'KEY_V': 'v', 'KEY_W': 'w', 'KEY_X': 'x',
        'KEY_Y': 'y', 'KEY_Z': 'z',
        'KEY_1': '1', 'KEY_2': '2', 'KEY_3': '3', 'KEY_4': '4',
        'KEY_5': '5', 'KEY_6': '6', 'KEY_7': '7', 'KEY_8': '8',
        'KEY_9': '9', 'KEY_0': '0',
        'KEY_MINUS': '-', 'KEY_EQUAL': '=', 'KEY_LEFTBRACE': '[',
        'KEY_RIGHTBRACE': ']', 'KEY_SEMICOLON': ';', 'KEY_APOSTROPHE': "'",
        'KEY_GRAVE': '`', 'KEY_BACKSLASH': '\\', 'KEY_COMMA': ',',
        'KEY_DOT': '.', 'KEY_SLASH': '/', 'KEY_SPACE': ' ',
    }

    STRING_SHIFT_KEY_MAP = {
        'KEY_A': 'A', 'KEY_B': 'B', 'KEY_C': 'C', 'KEY_D': 'D',
        'KEY_E': 'E', 'KEY_F': 'F', 'KEY_G': 'G', 'KEY_H': 'H',
        'KEY_I': 'I', 'KEY_J': 'J', 'KEY_K': 'K', 'KEY_L': 'L',
        'KEY_M': 'M', 'KEY_N': 'N', 'KEY_O': 'O', 'KEY_P': 'P',
        'KEY_Q': 'Q', 'KEY_R': 'R', 'KEY_S': 'S', 'KEY_T': 'T',
        'KEY_U': 'U', 'KEY_V': 'V', 'KEY_W': 'W', 'KEY_X': 'X',
        'KEY_Y': 'Y', 'KEY_Z': 'Z',
        'KEY_1': '!', 'KEY_2': '@', 'KEY_3': '#', 'KEY_4': '$',
        'KEY_5': '%', 'KEY_6': '^', 'KEY_7': '&', 'KEY_8': '*',
        'KEY_9': '(', 'KEY_0': ')',
        'KEY_MINUS': '_', 'KEY_EQUAL': '+', 'KEY_LEFTBRACE': '{',
        'KEY_RIGHTBRACE': '}', 'KEY_SEMICOLON': ':', 'KEY_APOSTROPHE': '"',
        'KEY_GRAVE': '~', 'KEY_BACKSLASH': '|', 'KEY_COMMA': '<',
        'KEY_DOT': '>', 'KEY_SLASH': '?', 'KEY_SPACE': ' ',
    }

    _printed_device_list = False

    def __init__(self, relay_pin: int = 17, relay_duration: float = 3.0) -> None:
        """Inicializa el servicio de escucha y configura el GPIO."""
        self.is_running: bool = False
        self._is_processing = False
        self.relay_pin = relay_pin
        self.relay_duration = relay_duration
        self.threads: List[threading.Thread] = []
        self.device_states = {}  # Track state per device
        self.lock = threading.Lock()  # Para sincronizar acceso al relé
        
        # Configurar GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.relay_pin, GPIO.OUT)
        GPIO.output(self.relay_pin, GPIO.HIGH)

    @staticmethod
    def find_scanner_devices() -> List[evdev.InputDevice]:
        """Detecta automáticamente todos los dispositivos scanner conectados por USB."""
        scanner_devices = []

        try:
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

            for device in devices:

                device_name = device.name.upper()
                if not ScannerListener._printed_device_list:
                    print(f"INIT device_name: {device_name}, path: {device.path}, phys: {device.phys})")
                # Buscar dispositivos que contengan palabras clave de scanners
                if any(keyword in device_name for keyword in ['SCAN', 'BARCODE', 'QR', 'READER']):
                    scanner_devices.append(device)
            ScannerListener._printed_device_list = True

        except Exception as e:
            print(f"❌ Error al buscar dispositivos: {e}")

        return scanner_devices

    def start(self) -> NoReturn:
        self.is_running = True
        print("🟢 Servicio iniciado. Esperando scanners...")
        print(f"⚡ GPIO configurado en pin: {self.relay_pin}")
        print("⚠️  Presiona Ctrl+C para detener el servicio\n")

        scanner_devices = self.find_scanner_devices()

        if not scanner_devices:
            print("⚠️ No hay scanners disponibles al inicio. Esperando conexiones...")

        try:
            for device in scanner_devices:
                self._start_device_thread(device)

            monitor_thread = threading.Thread(target=self._monitor_devices, daemon=True)
            monitor_thread.start()

            while self.is_running:
                time.sleep(1)

        except KeyboardInterrupt:
            self._shutdown()
        except Exception as e:
            print(f"❌ Error general: {e}")
            self._shutdown()

    def _start_device_thread(self, device: evdev.InputDevice) -> None:
        """Inicia el hilo de escucha para un dispositivo, validando que esté disponible."""
        with self.lock:
            try:
                # Verificar que el descriptor se puede abrir
                device.capabilities()
            except Exception as e:
                print(f"⚠️  No se puede abrir {device.path}: {e}")
                return

            if device.path in self.device_states:
                print(f"🔁 Reiniciando estado para {device.path}")

            self.device_states[device.path] = {
                'current_code': [],
                'shift_pressed': False
            }

            thread = threading.Thread(
                target=self._listen_device,
                args=(device,),
                daemon=True,
                name=f"Scanner-{device.path}"
            )
            thread.start()
            self.threads.append(thread)
            print(f"🚀 Thread iniciado para: {device.name} ({device.path})")

    def _monitor_devices(self, interval: float = 5.0) -> None:
        """Monitorea continuamente los dispositivos conectados y actualiza listeners dinámicamente."""
        previous_paths = set()

        while self.is_running:
            try:
                current_devices = [d for d in self.find_scanner_devices()]
                current_paths = set(device.path for device in current_devices)

                # --- Listas de tareas para ejecutar FUERA del lock ---
                devices_to_add = []
                # ----------------------------------------------------

                with self.lock:
                    known_paths = set(self.device_states.keys())

                    # Nuevos dispositivos
                    new_paths = current_paths - known_paths
                    for device in current_devices:
                        if device.path in new_paths:
                            # No inicies el thread aquí, solo márcalo
                            devices_to_add.append(device)

                    # Dispositivos desconectados
                    removed_paths = known_paths - current_paths
                    for path in removed_paths:
                        print(f"🔌 Scanner desconectado: {path}")
                        self.device_states.pop(path, None)

                        # Eliminar el thread asociado si existe
                        for t in self.threads:
                            if t.name == f"Scanner-{path}" and t.is_alive():
                                print(f"🧹 Terminando thread para {path}")
                                # No se puede forzar kill, pero se elimina del registro
                        self.threads = [t for t in self.threads if t.name != f"Scanner-{path}"]

                # --- FIN DEL BLOQUE 'with self.lock' ---

                # --- Ahora, ejecutamos las tareas pendientes FUERA del lock ---
                for device in devices_to_add:
                    device_name = device.name.upper()
                    print(f"device_name: {device_name}")
                    print(f"🔍 Scanner detectado: {device.name} ({device.path})")

                    # Esta llamada ahora es segura
                    self._start_device_thread(device)

                    print(f"🆕 Scanner conectado: {device.name} ({device.path})")

                # Solo imprimir resumen si hubo cambios
                if current_paths != previous_paths:
                    print(f"✅ Total de scanners detectados: {len(current_paths)}\n")
                    previous_paths = current_paths

            except Exception as e:
                print(f"❌ Error en monitor de dispositivos: {e}")

            time.sleep(interval)

    def _listen_device(self, device: evdev.InputDevice) -> None:
        """Escucha eventos de un dispositivo específico en su propio thread."""
        device_path = device.path
        device_name = device.name
        
        try:
            print(f"👂 Escuchando: {device_name} en {device_path}")
            
            for event in device.read_loop():
                if not self.is_running:
                    break
                    
                if event.type == ecodes.EV_KEY:
                    key_event = evdev.categorize(event)
                    # keystate: 0 = up, 1 = down, 2 = hold
                    if key_event.keystate in (0, 1):
                        self._handle_key(device_path, device_name, key_event.keycode, key_event.keystate)
                        
        except PermissionError:
            print(f"❌ Error: No tienes permisos para acceder a {device_path}")
            print(f"   Ejecuta: sudo chmod 666 {device_path}")
        except OSError as e:
            if self.is_running:
                print(f"⚠️  Dispositivo desconectado: {device_name} ({device_path})")
        except Exception as e:
            if self.is_running:
                print(f"❌ Error en {device_name}: {e}")

    def _handle_key(self, device_path: str, device_name: str, keycode: str, keystate: int) -> None:
        if device_path not in self.device_states:
            return

        state = self.device_states[device_path]

        if keycode in ('KEY_LEFTSHIFT', 'KEY_RIGHTSHIFT'):
            state['shift_pressed'] = (keystate == 1)
            return

        if keystate != 1:
            return

        if keycode == 'KEY_ENTER':
            if state['current_code']:
                if not self._is_processing:
                    self._is_processing = True
                    data = "".join(state['current_code']).strip()
                    thread = threading.Thread(
                        target=self._process_qr_data_threadsafe,
                        args=(data, device_name),
                        daemon=True
                    )
                    thread.start()
                else:
                    print("⚠️ Escaneo ignorado: proceso anterior aún en curso.")
            state['current_code'] = []
        else:
            key_map = self.STRING_SHIFT_KEY_MAP if state['shift_pressed'] else self.STRING_KEY_MAP
            if keycode in key_map:
                if not state['current_code']:  # Esto indica que es el primer carácter
                    print(f"📡 Evento detectado en {device_name}. Iniciando lectura...")
                state['current_code'].append(key_map[keycode])

    def _process_qr_data_threadsafe(self, data: str, device_name: str):
        try:
            self._process_qr_data(data, device_name)
        finally:
            self._is_processing = False

    def _process_qr_data(self, data: str, device_name: str) -> None:
        """Procesa y muestra los datos del código QR escaneado."""
        print(f"🔐 QR Detectado desde [{device_name}]: {data}\n")
        
        try:
            # Decodificar el JWT sin verificar la firma
            decoded = jwt.decode(data, options={"verify_signature": False})
            print("✅ JWT Decodificado:")
            for key, value in decoded.items():
                print(f"   {key}: {value}")
            print()
            
            # Activar el relé si el JWT es válido
            self._activate_relay(device_name)
            
        except jwt.DecodeError:
            print("⚠️  El QR no es un JWT válido")
            print(f"   Contenido: {data}\n")
        except Exception as e:
            print(f"❌ Error al decodificar JWT: {e}\n")

    def _activate_relay(self, device_name: str) -> None:
        """Activa el relé conectado al GPIO de forma thread-safe."""
        with self.lock:  # Sincronizar acceso al relé entre múltiples threads
            try:
                print(f"🔌 Activando relé en GPIO {self.relay_pin} (trigger desde {device_name})...")
                GPIO.output(self.relay_pin, GPIO.LOW)
                print(f"✅ Relé ON - Manteniéndose por {self.relay_duration} segundos")
                
                time.sleep(self.relay_duration)
                
                GPIO.output(self.relay_pin, GPIO.HIGH)
                print("🔌 Relé OFF\n")
            except Exception as e:
                print(f"❌ Error al activar el relé: {e}\n")

    def _shutdown(self) -> None:
        """Detiene el servicio de forma limpia y limpia el GPIO."""
        print("\n🛑 Deteniendo servicio...")
        self.is_running = False
        
        # Esperar a que todos los threads terminen
        for thread in self.threads:
            thread.join(timeout=2)
        
        GPIO.cleanup()
        print("✅ GPIO limpiado. ¡Hasta pronto!\n")
