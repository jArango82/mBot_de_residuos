#include <Arduino.h>
#include <Wire.h>
#include <SoftwareSerial.h>
#include <MeAuriga.h>

// Motores Encoder para mBot Ranger (Me Auriga)
MeEncoderOnBoard MotorIzquierdo(SLOT1);
MeEncoderOnBoard MotorDerecho(SLOT2);

// Anillo de 12 LEDs RGB (pin 44 en Me Auriga)
MeRGBLed anilloLeds(0, 12);

// Zumbador (pin 45 en Me Auriga)
MeBuzzer buzzer;

unsigned long ultimoMovimiento = 0;
bool enMovimiento = false;
void parar();

int velocidad = 100; // Rango de 0 a 255

void setup() {
  // Control USB desde Python: 115200 baudios
  Serial.begin(115200);
  parar();

  // Configuración del anillo LED
  anilloLeds.setpin(44);
  anilloLeds.setColor(0, 0, 80, 0); // Verde suave al iniciar
  anilloLeds.show();

  // Sonido de inicio (880 Hz por 150 ms)
  buzzer.tone(45, 880, 150);
  delay(150);
  Serial.println("RANGER_READY_V1");
}

void parar() {
  enMovimiento = false;
  MotorIzquierdo.setMotorPwm(0);
  MotorDerecho.setMotorPwm(0);
}

void avanzar() {
  // En configuración oruga (Land Raider), un motor va invertido respecto al otro
  MotorIzquierdo.setMotorPwm(-velocidad);
  MotorDerecho.setMotorPwm(velocidad);
}

void retroceder() {
  MotorIzquierdo.setMotorPwm(velocidad);
  MotorDerecho.setMotorPwm(-velocidad);
}

void girarIzquierda() {
  MotorIzquierdo.setMotorPwm(velocidad);
  MotorDerecho.setMotorPwm(velocidad);
}

void girarDerecha() {
  MotorIzquierdo.setMotorPwm(-velocidad);
  MotorDerecho.setMotorPwm(-velocidad);
}

void loop() {
  if (enMovimiento && millis() - ultimoMovimiento > 600) {
    parar();
    Serial.println("AUTO_STOP");
  }
  // Comprobar comandos USB
  if (Serial.available() > 0) {
    char comando = Serial.read();

    if (comando >= 'A' && comando <= 'Z') comando += 32;
    if (comando == '\r' || comando == '\n') return;
    if (comando == '?') { Serial.println("RANGER_READY_V1"); return; }
    if (comando == 'w' || comando == 'a' || comando == 's' || comando == 'd') {
      ultimoMovimiento = millis();
      enMovimiento = true;
    }
    switch (comando) {
      // --- MOVIMIENTO ---
      case 'w':
      case 'W':
        avanzar();
        break;

      case 's':
      case 'S':
        retroceder();
        break;

      case 'a':
      case 'A':
        girarIzquierda();
        break;

      case 'd':
      case 'D':
        girarDerecha();
        break;

      case 'x':
      case 'X': // Detener
        parar();
        break;

      // --- LUCES ---
      case '1': // Rojo
        anilloLeds.setColor(0, 255, 0, 0);
        anilloLeds.show();
        break;

      case '2': // Verde
        anilloLeds.setColor(0, 0, 255, 0);
        anilloLeds.show();
        break;

      case '3': // Azul
        anilloLeds.setColor(0, 0, 0, 255);
        anilloLeds.show();
        break;

      case '0': // Apagar LEDs
        anilloLeds.setColor(0, 0, 0, 0);
        anilloLeds.show();
        break;

      // --- SONIDO ---
      case 'p':
      case 'P':
        parar();
        buzzer.tone(45, 1000, 200);
        break;
      default:
        parar();
        Serial.println("ERR_COMMAND");
        return;
    }
    Serial.print("OK ");
    Serial.println(comando);
  }
}