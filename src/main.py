from machine import Pin, ADC
import time

LDR_PIN = 34
BTN_PIN = 15
LDR_THRESHOLD = 1500
MICRO_STOP_SECONDS = 5
DEBOUNCE_MS = 50

ldr = ADC(Pin(LDR_PIN))
ldr.atten(ADC.ATTN_11DB)

btn = Pin(BTN_PIN, Pin.IN, Pin.PULL_UP)

print("Contador de Producao Inicializado")

count = 0
blocked = False
block_start_ms = 0
micro_stop_alerted = False

last_btn_state = 1
last_btn_change_ms = 0


def read_ldr_state():
    """Le o LDR e retorna True se bloqueado (lux baixo, ADC alto)."""
    value = ldr.read()
    return value > LDR_THRESHOLD


def handle_ldr_transition(is_blocked, now):
    """Processa a maquina de estados do sensor LDR.

    Transicao de descida (livre -> bloqueado): objeto entrou no feixe,
    inicia o timer de micro-parada.

    Transicao de subida (bloqueado -> livre): objeto passou completamente,
    incrementa o contador.

    Bloqueio mantido: verifica se ultrapassou o limite de micro-parada
    usando ticks_diff, que e seguro contra wrap-around do contador de 32 bits.
    """
    global count, blocked, block_start_ms, micro_stop_alerted

    if is_blocked and not blocked:
        blocked = True
        block_start_ms = now
        micro_stop_alerted = False

    elif not is_blocked and blocked:
        blocked = False
        count += 1
        print("Peca detectada! Total: " + str(count))
        micro_stop_alerted = False

    elif is_blocked and blocked:
        elapsed = time.ticks_diff(now, block_start_ms) / 1000.0
        if elapsed >= MICRO_STOP_SECONDS and not micro_stop_alerted:
            print("Alerta: Micro-parada detectada!")
            micro_stop_alerted = True


def handle_button(now):
    """Le o botao de reset com debounce por software.

    So aceita uma transicao de estado se a ultima mudanca ocorreu
    ha mais de DEBOUNCE_MS, filtrando bouncing mecanico.
    """
    global count, blocked, micro_stop_alerted, last_btn_state, last_btn_change_ms

    btn_raw = btn.value()

    if btn_raw != last_btn_state:
        if time.ticks_diff(now, last_btn_change_ms) > DEBOUNCE_MS:
            last_btn_state = btn_raw
            if btn_raw == 0:
                count = 0
                blocked = False
                micro_stop_alerted = False
                print("Turno resetado com sucesso. Contadores zerados.")
        last_btn_change_ms = now


while True:
    now = time.ticks_ms()
    is_blocked = read_ldr_state()
    handle_ldr_transition(is_blocked, now)
    handle_button(now)
    time.sleep(0.05)
