from machine import Pin, PWM
import bluetooth
import time
from neopixel import NeoPixel

# ── BLE SETUP ────────────────────────────────────────────────────────────
name = "tootie"

ble = bluetooth.BLE()
ble.active(False)
time.sleep(0.5)
ble.active(True)
ble.config(gap_name=name)

SERVICE_UUID = bluetooth.UUID("6e400001-b5a3-f393-e0a9-e50e24dcca9e")
CHAR_UUID    = bluetooth.UUID("6e400002-b5a3-f393-e0a9-e50e24dcca9e")

CHAR    = (CHAR_UUID, bluetooth.FLAG_WRITE)
SERVICE = (SERVICE_UUID, (CHAR,),)
((char_handle,),) = ble.gatts_register_services((SERVICE,))

connections = set()

# ── HARDWARE ─────────────────────────────────────────────────────────────
motor_in1 = Pin(25, Pin.OUT)
motor_in2 = Pin(26, Pin.OUT)
motor_en  = Pin(27, Pin.OUT)

servo_left  = PWM(Pin(18), freq=50)
servo_right = PWM(Pin(19), freq=50)

# 🔥 8 LED STRIP
strip = NeoPixel(Pin(13), 8)

ir0 = Pin(32, Pin.IN, Pin.PULL_UP)
ir1 = Pin(33, Pin.IN, Pin.PULL_UP)
ir2 = Pin(34, Pin.IN, Pin.PULL_UP)

DOOR_OPEN_DUTY  = 128
DOOR_CLOSE_DUTY = 26
DOOR_WAIT_MS    = 3000

# ── STATE ────────────────────────────────────────────────────────────────
current_floor = 0
target_floor  = 0
floor_reached = False
moving        = False

# 🔧 IR debounce
last_trigger_time = 0
DEBOUNCE_MS = 800

IDLE             = "IDLE"
MOVING           = "MOVING"
ARRIVED          = "ARRIVED"
DOOR_OPEN_STATE  = "DOOR_OPEN"
DOOR_CLOSE_STATE = "DOOR_CLOSE"

state         = IDLE
door_timer_ms = 0

# ── MOTOR ────────────────────────────────────────────────────────────────
def motor_up():
    motor_in1.value(1)
    motor_in2.value(0)
    motor_en.value(1)

def motor_down():
    motor_in1.value(0)
    motor_in2.value(1)
    motor_en.value(1)

def motor_stop():
    motor_in1.value(0)
    motor_in2.value(0)
    motor_en.value(0)

# ── DOORS ────────────────────────────────────────────────────────────────
def door_open():
    servo_left.duty(DOOR_OPEN_DUTY)
    servo_right.duty(DOOR_OPEN_DUTY)

def door_close():
    servo_left.duty(DOOR_CLOSE_DUTY)
    servo_right.duty(DOOR_CLOSE_DUTY)

# ── NEOPIXEL ─────────────────────────────────────────────────────────────
def show_floor(floor):
    counts = [2, 5, 8]
    colors = [(0, 255, 0), (0, 150, 255), (255, 100, 0)]

    count = counts[floor]
    color = colors[floor]

    for i in range(8):
        if i < count:
            strip[i] = color
        else:
            strip[i] = (0, 0, 0)
    strip.write()

def leds_off():
    for i in range(8):
        strip[i] = (0, 0, 0)
    strip.write()

# ── IR INTERRUPTS (WITH DEBOUNCE) ────────────────────────────────────────
def handle_ir(floor):
    global current_floor, floor_reached, last_trigger_time
    now = time.ticks_ms()

    if time.ticks_diff(now, last_trigger_time) > DEBOUNCE_MS:
        current_floor = floor
        floor_reached = True
        last_trigger_time = now
        print("IR: floor", floor, "triggered")

def floor_0_hit(pin): handle_ir(0)
def floor_1_hit(pin): handle_ir(1)
def floor_2_hit(pin): handle_ir(2)

ir0.irq(trigger=Pin.IRQ_FALLING, handler=floor_0_hit)
ir1.irq(trigger=Pin.IRQ_FALLING, handler=floor_1_hit)
ir2.irq(trigger=Pin.IRQ_FALLING, handler=floor_2_hit)

# ── BLE IRQ ──────────────────────────────────────────────────────────────
def ble_irq(event, data):
    global connections, target_floor, state

    if event == 1:
        conn_handle, _, _ = data
        connections.add(conn_handle)
        print("Connected")

    elif event == 2:
        conn_handle, _, _ = data
        connections.discard(conn_handle)
        print("Disconnected")
        advertise(name)

    elif event == 3:
        conn_handle, value_handle = data
        if value_handle == char_handle:
            raw = ble.gatts_read(char_handle).rstrip(b'\x00')
            msg = raw.decode().strip()
            print("Received:", msg)

            if msg in ("0", "1", "2") and state == IDLE:
                req = int(msg)
                target_floor  = req
                floor_reached = False

                if req == current_floor:
                    state = ARRIVED
                else:
                    state = MOVING

ble.irq(ble_irq)

# ── ADVERTISING ──────────────────────────────────────────────────────────
def advertise(name):
    name_bytes = name.encode()
    adv = (bytearray([0x02, 0x01, 0x06]) +
           bytearray([len(name_bytes) + 1, 0x09]) +
           name_bytes)
    ble.gap_advertise(100, adv)
    print("Advertising as:", name)

# ── MAIN LOOP ────────────────────────────────────────────────────────────
advertise(name)
print("Waiting for connection...")

show_floor(current_floor)

while True:

    if state == IDLE:
        pass

    elif state == MOVING:
        if not moving:
            moving = True
            floor_reached = False

            if current_floor < target_floor:
                motor_up()
                print("Going UP")
            else:
                motor_down()
                print("Going DOWN")

        if floor_reached:
            floor_reached = False

            if current_floor == target_floor:
                motor_stop()
                moving = False
                state = ARRIVED

    elif state == ARRIVED:
        print("Arrived at floor", current_floor)
        show_floor(current_floor)
        door_open()
        door_timer_ms = time.ticks_ms()
        state = DOOR_OPEN_STATE

    elif state == DOOR_OPEN_STATE:
        if time.ticks_diff(time.ticks_ms(), door_timer_ms) >= DOOR_WAIT_MS:
            door_close()
            state = DOOR_CLOSE_STATE

    elif state == DOOR_CLOSE_STATE:
        if time.ticks_diff(time.ticks_ms(), door_timer_ms) >= DOOR_WAIT_MS + 1500:
            moving = False
            state = IDLE
            print("Ready")

    time.sleep_ms(10) 