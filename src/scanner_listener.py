"""Módulo que encapsula la lógica de escucha del dispositivo scanner QR."""

from typing import NoReturn
import evdev
from evdev import ecodes
import jwt
import RPi.GPIO as GPIO
import time


class ScannerListener:
    """Servicio que escucha continuamente las lecturas del scanner QR."""

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

    def __init__(self, device_path: str = "/dev/input/event5", relay_pin: int = 17, relay_duration: float = 30.0) -> None:
        """Inicializa el servicio de escucha y configura el GPIO."""
        self.device_path = device_path
        self.is_running: bool = False
        self.current_code: str = ""
        self.shift_pressed: bool = False
        self.relay_pin = relay_pin
        self.relay_duration = relay_duration
        
        # Configurar GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.relay_pin, GPIO.OUT)
        GPIO.output(self.relay_pin, GPIO.LOW)

    def start(self) -> NoReturn:
        """Inicia el bucle de escucha infinito del scanner."""
        self.is_running = True
        print("🔍 Servicio de escucha del scanner QR iniciado")
        print(f"📱 Escuchando dispositivo: {self.device_path}")
        print(f"⚡ GPIO configurado en pin: {self.relay_pin}")
        print("⚠️  Presiona Ctrl+C para detener el servicio\n")
        
        try:
            device = evdev.InputDevice(self.device_path)
            print(f"✅ Conectado a: {device.name}\n")
            
            for event in device.read_loop():
                if event.type == ecodes.EV_KEY:
                    key_event = evdev.categorize(event)
                    # keystate: 0 = up, 1 = down, 2 = hold
                    if key_event.keystate in (0, 1):
                        self._handle_key(key_event.keycode, key_event.keystate)
        except KeyboardInterrupt:
            self._shutdown()
        except PermissionError:
            print("❌ Error: No tienes permisos para acceder al dispositivo")
            print(f"   Ejecuta: sudo chmod 666 {self.device_path}")
            self._shutdown()
        except Exception as e:
            print(f"❌ Error: {e}")
            self._shutdown()

    def _handle_key(self, keycode: str, keystate: int) -> None:
        """Procesa una tecla presionada o liberada."""
        # Detectar estado de Shift
        if keycode in ('KEY_LEFTSHIFT', 'KEY_RIGHTSHIFT'):
            self.shift_pressed = (keystate == 1)  # 1 = presionado, 0 = liberado
            return

        # Solo procesar cuando la tecla es presionada (keystate = 1)
        if keystate != 1:
            return

        if keycode == 'KEY_ENTER':
            if self.current_code:
                self._process_qr_data(self.current_code)
                self.current_code = ""
        else:
            key_value = getattr(ecodes, keycode, None)
            if key_value is not None:
                # Usar el mapa correspondiente según el estado de Shift
                key_map = self.SHIFT_KEY_MAP if self.shift_pressed else self.KEY_MAP
                if key_value in key_map:
                    self.current_code += key_map[key_value]

    def _process_qr_data(self, data: str) -> None:
        """Procesa y muestra los datos del código QR escaneado."""
        print(f"🔐 QR Detectado: {data}\n")
        
        try:
            # Decodificar el JWT sin verificar la firma
            decoded = jwt.decode(data, options={"verify_signature": False})
            print("✅ JWT Decodificado:")
            for key, value in decoded.items():
                print(f"   {key}: {value}")
            print()
            
            # Activar el relé si el JWT es válido
            self._activate_relay()
            
        except jwt.DecodeError:
            print("⚠️  El QR no es un JWT válido")
            print(f"   Contenido: {data}\n")
        except Exception as e:
            print(f"❌ Error al decodificar JWT: {e}\n")

    def _activate_relay(self) -> None:
        """Activa el relé conectado al GPIO."""
        try:
            print(f"🔌 Activando relé en GPIO {self.relay_pin}...")
            GPIO.output(self.relay_pin, GPIO.HIGH)
            print(f"✅ Relé ON - Manteniéndose por {self.relay_duration} segundos")
            
            time.sleep(self.relay_duration)
            
            GPIO.output(self.relay_pin, GPIO.LOW)
            print("🔌 Relé OFF\n")
        except Exception as e:
            print(f"❌ Error al activar el relé: {e}\n")

    def _shutdown(self) -> None:
        """Detiene el servicio de forma limpia y limpia el GPIO."""
        self.is_running = False
        GPIO.cleanup()
        print("\n\n🛑 Servicio detenido. GPIO limpiado. ¡Hasta pronto!")
