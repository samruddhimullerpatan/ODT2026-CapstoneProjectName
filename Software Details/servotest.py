from machine import Pin,PWM
#DutyCycle of PWM corresponds to position of the...
#...shaft of the servomotor
import time#For delay

my_servo = PWM(Pin(18),freq=50)
your_servo= PWM(Pin (19), freq=50)

while True:#Continous running of the loop
    my_servo.duty(26)
    your_servo.duty(26)#Move the shaft to approx. 0 degree
    time.sleep(2)#Give it some time to reach the position
    my_servo.duty(128)
    your_servo.duty(128)#Move the shaft to approx. 180 degree
    time.sleep(2)#Give it some time to reach the position