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

int velocidad = 180; // Rango de 0 a 255

void setup() {
  // El módulo Bluetooth de Me Auriga comparte el puerto Serial a 115200 baudios
  Serial.begin(115200);

  // Configuración del anillo LED
  anilloLeds.setpin(44);
  anilloLeds.setColor(0, 0, 80, 0); // Verde suave al iniciar
  anilloLeds.show();

  // Sonido de inicio (880 Hz por 150 ms)
  buzzer.tone(45, 880, 150);
  delay(150);
}

void parar() {
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
  // Comprobar si han llegado comandos por Bluetooth/USB
  if (Serial.available() > 0) {
    char comando = Serial.read();

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
        buzzer.tone(45, 1000, 200);
        break;
    }
  }
}