from machine import Pin, PWM
import time

motor_in1 = Pin(25, Pin.OUT)
motor_in2 = Pin(26, Pin.OUT)
motor_en  = PWM(Pin(27), freq=1000)

# Speed: 0–1023 (ESP32 PWM)
SPEED = 600   # try 300–700 range

def motor_up():
    print("UP")
    motor_in1.value(1)
    motor_in2.value(0)
    motor_en.duty(SPEED)

def motor_down():
    print("DOWN")
    motor_in1.value(0)
    motor_in2.value(1)
    motor_en.duty(SPEED)

def motor_stop():
    print("STOP")
    motor_en.duty(0)

print("Controlled Motor Test\n")

while True:
    motor_up()
    time.sleep(3)

    motor_stop()
    time.sleep(5)

    motor_down()
    time.sleep(6)

    motor_stop()
    time.sleep(5)