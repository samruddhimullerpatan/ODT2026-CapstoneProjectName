from machine import Pin, PWM
import bluetooth
import time
from neopixel import NeoPixel

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

# ── HARDWARE SETUP ────────────────────────────────────────────────────────
motor_in1 = Pin(25, Pin.OUT)
motor_in2 = Pin(26, Pin.OUT)
motor_en  = Pin(27, Pin.OUT)

servo_left  = PWM(Pin(18), freq=50)
servo_right = PWM(Pin(19), freq=50)

strip = NeoPixel(Pin(13, Pin.OUT), 10)

ir0 = Pin(32, Pin.IN)   # Floor 0 (bottom)
ir1 = Pin(33, Pin.IN)   # Floor 1 (middle)
ir2 = Pin(34, Pin.IN)   # Floor 2 (top)

# Timer-based fallback — how long each floor-to-floor travel should take (ms)
# If IR doesn't trigger within this time, we stop anyway
TRAVEL_TIMEOUT = {
    (0, 1): 4000,
    (1, 0): 4000,
    (1, 2): 4000,
    (2, 1): 4000,
    (0, 2): 8000,
    (2, 0): 8000,
}

DOOR_OPEN_DUTY  = 26
DOOR_CLOSE_DUTY = 128
DOOR_WAIT_MS    = 3000

# ── STATE ────────────────────────────────────────────────────────────────
current_floor  = 0
target_floor   = 0
floor_reached  = False      # set by IR interrupt only
emergency_flag = False

# State machine states
IDLE       = "IDLE"
MOVING     = "MOVING"
ARRIVED    = "ARRIVED"
DOOR_OPEN  = "DOOR_OPEN"
DOOR_CLOSE = "DOOR_CLOSE"
EMERGENCY  = "EMERGENCY"

state = IDLE

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
# Floor 0 → 3 LEDs lit, Floor 1 → 6 LEDs lit, Floor 2 → all 10 lit
FLOOR_LED_COUNT = [3, 6, 10]
FLOOR_COLOR     = (0, 150, 255)     # same color for all, just fill amount changes

def show_floor(floor):
    count = FLOOR_LED_COUNT[floor]
    for i in range(10):
        strip[i] = FLOOR_COLOR if i < count else (0, 0, 0)
    strip.write()

def leds_off():
    for i in range(10):
        strip[i] = (0, 0, 0)
    strip.write()

def leds_emergency():
    for i in range(10):
        strip[i] = (255, 80, 0)
        strip.write()
        time.sleep_ms(50)

# ── IR INTERRUPTS ─────────────────────────────────────────────────────────
# These only set flags — all logic stays in the main loop
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
    global connections, emergency_flag, target_floor, state

    if event == 1:      # connected
        conn_handle, _, _ = data
        connections.add(conn_handle)
        print("Connected")

    elif event == 2:    # disconnected
        conn_handle, _, _ = data
        connections.discard(conn_handle)
        print("Disconnected")
        advertise(name)

    elif event == 3:    # data received
        conn_handle, value_handle = data
        if value_handle == char_handle:
            msg = ble.gatts_read(char_handle).decode().strip()
            print("Received:", msg)

            if msg == "E":
                # Emergency is high-priority — flag it, state machine handles it
                emergency_flag = True

            elif msg == "S":
                # Reset only works if not moving
                if state == IDLE or state == EMERGENCY:
                    emergency_flag = False
                    motor_stop()
                    leds_off()
                    state = IDLE

            elif msg in ["0", "1", "2"]:
                req = int(msg)
                # Only accept new floor request if idle
                if state == IDLE:
                    if req == current_floor:
                        # Already here — just do a door cycle
                        target_floor = req
                        state = ARRIVED
                    else:
                        target_floor = req
                        floor_reached = False
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

# ── HELPERS ──────────────────────────────────────────────────────────────
move_start_ms  = 0
door_timer_ms  = 0

def start_moving():
    """Kick off motor in the right direction and start the safety timer."""
    global move_start_ms
    move_start_ms = time.ticks_ms()
    if current_floor < target_floor:
        motor_up()
    else:
        motor_down()

# ── MAIN LOOP ─────────────────────────────────────────────────────────────
advertise(name)
print("Waiting for connection...")

while True:

    # ── Emergency check — highest priority, runs every iteration ──────────
    if emergency_flag and state != EMERGENCY:
        motor_stop()
        state = EMERGENCY

    # ── STATE MACHINE ─────────────────────────────────────────────────────

    if state == IDLE:
        pass    # waiting for BLE command

    elif state == MOVING:
        # First iteration after entering MOVING — start the motor
        if move_start_ms == 0:
            start_moving()

        # IR sensor got there
        if floor_reached:
            floor_reached = False
            if current_floor == target_floor:
                motor_stop()
                move_start_ms = 0
                state = ARRIVED
            else:
                # Passed a middle floor — not our stop, keep going
                # (motor already running, just reset flag)
                pass

        # Safety fallback — timer expired, stop anyway
        timeout = TRAVEL_TIMEOUT.get((current_floor, target_floor), 9000)
        if time.ticks_diff(time.ticks_ms(), move_start_ms) > timeout:
            motor_stop()
            move_start_ms = 0
            print("Timeout fallback — stopping at estimated position")
            state = ARRIVED

    elif state == ARRIVED:
        print(f"At floor {current_floor}")
        show_floor(current_floor)
        door_open()
        door_timer_ms = time.ticks_ms()
        state = DOOR_OPEN

    elif state == DOOR_OPEN:
        # Non-blocking wait — check clock each loop
        if time.ticks_diff(time.ticks_ms(), door_timer_ms) >= DOOR_WAIT_MS:
            door_close()
            state = DOOR_CLOSE

    elif state == DOOR_CLOSE:
        # Give servo a moment to physically close before declaring IDLE
        # If your servo is slow, bump this up
        if time.ticks_diff(time.ticks_ms(), door_timer_ms) >= DOOR_WAIT_MS + 1500:
            state = IDLE

    elif state == EMERGENCY:
        motor_stop()
        leds_emergency()

        # Drive back to floor 0 if not already there
        if current_floor != 0:
            floor_reached = False
            motor_down()
            # Wait for IR floor 0, with a hard timeout
            emg_start = time.ticks_ms()
            while not floor_reached:
                if time.ticks_diff(time.ticks_ms(), emg_start) > TRAVEL_TIMEOUT.get((current_floor, 0), 9000):
                    break
                time.sleep_ms(10)
            motor_stop()
            current_floor = 0

        door_open()
        time.sleep_ms(3000)
        door_close()
        leds_off()

        emergency_flag = False
        state = IDLE

    time.sleep_ms(10)