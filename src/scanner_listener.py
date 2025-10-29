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

    KEY_MAP = {
        ecodes.KEY_1: '1', ecodes.KEY_2: '2', ecodes.KEY_3: '3', ecodes.KEY_4: '4',
        ecodes.KEY_5: '5', ecodes.KEY_6: '6', ecodes.KEY_7: '7', ecodes.KEY_8: '8',
        ecodes.KEY_9: '9', ecodes.KEY_0: '0',
        ecodes.KEY_A: 'a', ecodes.KEY_B: 'b', ecodes.KEY_C: 'c', ecodes.KEY_D: 'd',
        ecodes.KEY_E: 'e', ecodes.KEY_F: 'f', ecodes.KEY_G: 'g', ecodes.KEY_H: 'h',
        ecodes.KEY_I: 'i', ecodes.KEY_J: 'j', ecodes.KEY_K: 'k', ecodes.KEY_L: 'l',
        ecodes.KEY_M: 'm', ecodes.KEY_N: 'n', ecodes.KEY_O: 'o', ecodes.KEY_P: 'p',
        ecodes.KEY_Q: 'q', ecodes.KEY_R: 'r', ecodes.KEY_S: 's', ecodes.KEY_T: 't',
        ecodes.KEY_U: 'u', ecodes.KEY_V: 'v', ecodes.KEY_W: 'w', ecodes.KEY_X: 'x',
        ecodes.KEY_Y: 'y', ecodes.KEY_Z: 'z',
        ecodes.KEY_MINUS: '-', ecodes.KEY_EQUAL: '=', ecodes.KEY_LEFTBRACE: '[',
        ecodes.KEY_RIGHTBRACE: ']', ecodes.KEY_SEMICOLON: ';', ecodes.KEY_APOSTROPHE: "'",
        ecodes.KEY_GRAVE: '`', ecodes.KEY_BACKSLASH: '\\', ecodes.KEY_COMMA: ',',
        ecodes.KEY_DOT: '.', ecodes.KEY_SLASH: '/', ecodes.KEY_SPACE: ' ',
    }

    # Mapeo para teclas con Shift presionado
    SHIFT_KEY_MAP = {
        ecodes.KEY_1: '!', ecodes.KEY_2: '@', ecodes.KEY_3: '#', ecodes.KEY_4: '$',
        ecodes.KEY_5: '%', ecodes.KEY_6: '^', ecodes.KEY_7: '&', ecodes.KEY_8: '*',
        ecodes.KEY_9: '(', ecodes.KEY_0: ')',
        ecodes.KEY_A: 'A', ecodes.KEY_B: 'B', ecodes.KEY_C: 'C', ecodes.KEY_D: 'D',
        ecodes.KEY_E: 'E', ecodes.KEY_F: 'F', ecodes.KEY_G: 'G', ecodes.KEY_H: 'H',
        ecodes.KEY_I: 'I', ecodes.KEY_J: 'J', ecodes.KEY_K: 'K', ecodes.KEY_L: 'L',
        ecodes.KEY_M: 'M', ecodes.KEY_N: 'N', ecodes.KEY_O: 'O', ecodes.KEY_P: 'P',
        ecodes.KEY_Q: 'Q', ecodes.KEY_R: 'R', ecodes.KEY_S: 'S', ecodes.KEY_T: 'T',
        ecodes.KEY_U: 'U', ecodes.KEY_V: 'V', ecodes.KEY_W: 'W', ecodes.KEY_X: 'X',
        ecodes.KEY_Y: 'Y', ecodes.KEY_Z: 'Z',
        ecodes.KEY_MINUS: '_', ecodes.KEY_EQUAL: '+', ecodes.KEY_LEFTBRACE: '{',
        ecodes.KEY_RIGHTBRACE: '}', ecodes.KEY_SEMICOLON: ':', ecodes.KEY_APOSTROPHE: '"',
        ecodes.KEY_GRAVE: '~', ecodes.KEY_BACKSLASH: '|', ecodes.KEY_COMMA: '<',
        ecodes.KEY_DOT: '>', ecodes.KEY_SLASH: '?', ecodes.KEY_SPACE: ' ',
    }

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
                # Buscar dispositivos que contengan palabras clave de scanners
                if any(keyword in device_name for keyword in ['SCAN', 'BARCODE', 'QR', 'READER']):
                    scanner_devices.append(device)

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
        with self.lock:
            if device.path in self.device_states:
                print(f"⚠️  Ya existe estado para {device.path}, ignorando reinicio")
                return  # Ya está registrado

            self.device_states[device.path] = {
                'current_code': '',
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

                with self.lock:
                    known_paths = set(self.device_states.keys())

                    # Nuevos dispositivos
                    new_paths = current_paths - known_paths
                    for device in current_devices:
                        if device.path in new_paths:
                            device_name = device.name.upper()
                            print(f"device_name: {device_name}")
                            print(f"🔍 Scanner detectado: {device.name} ({device.path})")
                            self._start_device_thread(device)
                            print(f"🆕 Scanner conectado: {device.name} ({device.path})")

                    # Dispositivos desconectados
                    removed_paths = known_paths - current_paths
                    for path in removed_paths:
                        print(f"🔌 Scanner desconectado: {path}")
                        self.device_states.pop(path, None)

                        # Eliminar el thread asociado si existe
                        self.threads = [t for t in self.threads if t.name != f"Scanner-{path}"]

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
        """Procesa una tecla presionada o liberada de un dispositivo específico."""
        state = self.device_states[device_path]
        
        # Detectar estado de Shift
        if keycode in ('KEY_LEFTSHIFT', 'KEY_RIGHTSHIFT'):
            state['shift_pressed'] = (keystate == 1)
            return

        # Solo procesar cuando la tecla es presionada (keystate = 1)
        if keystate != 1:
            return
        print(f"keycode: {keycode}")
        if keycode == 'KEY_ENTER':
            if state['current_code']:
                if not self._is_processing:  # bandera para evitar procesamiento concurrente
                    self._is_processing = True
                    data = state['current_code']
                    thread = threading.Thread(
                        target=self._process_qr_data_threadsafe,
                        args=(data, device_name),
                        daemon=True
                    )
                    thread.start()
                else:
                    print("⚠️ Escaneo ignorado: proceso anterior aún en curso.")
                state['current_code'] = ""
        else:
            key_value = getattr(ecodes, keycode, None)
            if key_value is not None:
                # Usar el mapa correspondiente según el estado de Shift
                key_map = self.SHIFT_KEY_MAP if state['shift_pressed'] else self.KEY_MAP
                if key_value in key_map:
                    state['current_code'] += key_map[key_value]

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
