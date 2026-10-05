#include <Arduino.h>
#include <Wire.h>
#include <SoftwareSerial.h>
#include <MeAuriga.h>
MeEncoderOnBoard MotorIzquierdo(SLOT1);
MeEncoderOnBoard MotorDerecho(SLOT2);
MeRGBLed anilloLeds(0, 12);
MeBuzzer buzzer;
unsigned long ultimoMovimiento = 0;
bool enMovimiento = false;
int velocidad = 100;
void parar() {
  enMovimiento = false;
  MotorIzquierdo.setMotorPwm(0);
  MotorDerecho.setMotorPwm(0);
}
void setup() {
  Serial.begin(115200);
  parar();
  anilloLeds.setpin(44);
  anilloLeds.setColor(0, 0, 80, 0);
  anilloLeds.show();
  buzzer.tone(45, 880, 150);
  Serial.println("RANGER_READY_V1");
}
void loop() {
  if (enMovimiento && millis() - ultimoMovimiento > 600) {
    parar();
    Serial.println("AUTO_STOP");
  }
  if (Serial.available() <= 0) return;
  char comando = Serial.read();
  if (comando >= 'A' && comando <= 'Z') comando += 32;
  if (comando == '\r' || comando == '\n') return;
  if (comando == '?') { Serial.println("RANGER_READY_V1"); return; }
  if (comando == 'w' || comando == 'a' || comando == 's' || comando == 'd') {
    ultimoMovimiento = millis();
    enMovimiento = true;
  }
  switch (comando) {
    case 'w': MotorIzquierdo.setMotorPwm(-velocidad); MotorDerecho.setMotorPwm(velocidad); break;
    case 's': MotorIzquierdo.setMotorPwm(velocidad); MotorDerecho.setMotorPwm(-velocidad); break;
    case 'a': MotorIzquierdo.setMotorPwm(velocidad); MotorDerecho.setMotorPwm(velocidad); break;
    case 'd': MotorIzquierdo.setMotorPwm(-velocidad); MotorDerecho.setMotorPwm(-velocidad); break;
    case 'x': parar(); break;
    case '1': anilloLeds.setColor(0,255,0,0); anilloLeds.show(); break;
    case '2': anilloLeds.setColor(0,0,255,0); anilloLeds.show(); break;
    case '3': anilloLeds.setColor(0,0,0,255); anilloLeds.show(); break;
    case '0': anilloLeds.setColor(0,0,0,0); anilloLeds.show(); break;
    case 'p': parar(); buzzer.tone(45,1000,200); break;
    default: parar(); Serial.println("ERR_COMMAND"); return;
  }
  Serial.print("OK ");
  Serial.println(comando);
}
