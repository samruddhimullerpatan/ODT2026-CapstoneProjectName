from machine import Pin, PWM
import bluetooth
import time

# ── BLE SETUP ────────────────────────────────────────────────────────────
name = "tootie"

ble = bluetooth.BLE()
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

ir0 = Pin(32, Pin.IN)
ir1 = Pin(33, Pin.IN)
ir2 = Pin(34, Pin.IN)

DOOR_OPEN_DUTY  = 26
DOOR_CLOSE_DUTY = 128
DOOR_WAIT_MS    = 3000

# ── STATE ────────────────────────────────────────────────────────────────
current_floor = 0
target_floor  = 0
floor_reached = False
moving        = False

IDLE             = "IDLE"
MOVING           = "MOVING"
ARRIVED          = "ARRIVED"
DOOR_OPEN_STATE  = "DOOR_OPEN"
DOOR_CLOSE_STATE = "DOOR_CLOSE"

state         = IDLE
door_timer_ms = 0

# ── MOTOR ────────────────────────────────────────────────────────────────
def motor_up():
    motor_in1.value(1); motor_in2.value(0); motor_en.value(1)

def motor_down():
    motor_in1.value(0); motor_in2.value(1); motor_en.value(1)

def motor_stop():
    motor_in1.value(0); motor_in2.value(0); motor_en.value(0)

# ── DOORS ────────────────────────────────────────────────────────────────
def door_open():
    servo_left.duty(DOOR_OPEN_DUTY)
    servo_right.duty(DOOR_OPEN_DUTY)

def door_close():
    servo_left.duty(DOOR_CLOSE_DUTY)
    servo_right.duty(DOOR_CLOSE_DUTY)

# ── IR INTERRUPTS ────────────────────────────────────────────────────────
def floor_0_hit(pin):
    global current_floor, floor_reached
    current_floor = 0
    floor_reached = True

def floor_1_hit(pin):
    global current_floor, floor_reached
    current_floor = 1
    floor_reached = True

def floor_2_hit(pin):
    global current_floor, floor_reached
    current_floor = 2
    floor_reached = True

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
            raw_msg = ble.gatts_read(char_handle).rstrip(b'\x00')
            msg = raw_msg.decode().strip()
            print("Received:", msg)

            if msg in ("0", "1", "2"):
                req = int(msg)
                if state == IDLE:
                    target_floor = req
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

while True:

    if state == IDLE:
        pass

    elif state == MOVING:
        if not moving:
            moving = True
            floor_reached = False
            if current_floor < target_floor:
                motor_up()
                print(f"Moving UP to floor {target_floor}")
            else:
                motor_down()
                print(f"Moving DOWN to floor {target_floor}")

        if floor_reached:
            floor_reached = False
            if current_floor == target_floor:
                motor_stop()
                moving = False
                state = ARRIVED

    elif state == ARRIVED:
        print(f"At floor {current_floor}")
        door_open()
        door_timer_ms = time.ticks_ms()
        state = DOOR_OPEN_STATE

    elif state == DOOR_OPEN_STATE:
        if time.ticks_diff(time.ticks_ms(), door_timer_ms) >= DOOR_WAIT_MS:
            door_close()
            state = DOOR_CLOSE_STATE

    elif state == DOOR_CLOSE_STATE:
        if time.ticks_diff(time.ticks_ms(), door_timer_ms) >= DOOR_WAIT_MS + 1500:
            state = IDLE
            print("Ready")

    time.sleep_ms(10)