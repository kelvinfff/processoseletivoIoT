# Contador de Producao Nao-Intrusivo

## Identificacao do Candidato

- **Nome completo:** Kelvin Oliveira Fernandes
- **GitHub:** github.com/kelvinfff

## Visao Geral da Solucao

O projeto implementa um contador de producao industrial nao-intrusivo utilizando um sensor optico LDR. O sistema detecta a passagem de objetos em uma esteira transportadora pela interrupcao do feixe de luz, contabiliza cada peca e monitora micro-paradas (obstrucao prolongada do sensor). Um botao fisico permite resetar o turno de trabalho.

A escolha pelo cenario LIGHT foi motivada pela simplicidade do hardware (apenas LDR + botao, sem necessidade de drivers de protocolo como I2C ou bit-bang) e pela clareza da maquina de estados, que cobre tres cenarios de validacao distintos (contagem, micro-parada e reset) sem sobreposicao de responsabilidades.

## Arquitetura do Sistema Embarcado

O firmware segue uma maquina de estados com tres estados principais, implementada na funcao `handle_ldr_transition()`:

1. **Livre (Clear):** Sensor LDR le alta luminosidade (ADC < 1500). Nenhum objeto obstruindo o feixe.
2. **Bloqueado (Blocked):** Objeto interrompe o feixe (ADC > 1500). Um timer nao-bloqueante baseado em `time.ticks_diff()` inicia a contagem para deteccao de micro-parada.
3. **Micro-parada:** Bloqueio continuo por 5+ segundos dispara alerta unico.

A transicao de **Bloqueado -> Livre** (borda de subida da luminosidade) e o unico momento em que o contador e incrementado, garantindo que a peca passou completamente pelo sensor — e nao apenas entrou no feixe.

O codigo esta organizado em tres funcoes com responsabilidades isoladas:
- `read_ldr_state()`: leitura pura do ADC e comparacao com limiar
- `handle_ldr_transition()`: maquina de estados completa do LDR
- `handle_button()`: leitura do botao com debounce por software

Cada funcao opera sobre variaveis globais de estado, mantendo o loop principal enxuto (6 linhas) e facilitando manutencao e testes.

Fluxo principal:

```
Inicializacao -> Loop (50ms):
  ├─ read_ldr_state(): ADC.read() -> comparacao com limiar 1500
  ├─ handle_ldr_transition(): maquina de estados (clear/blocked/micro-stop)
  ├─ handle_button(): debounce + reset
  └─ sleep(50ms)
```

## Componentes Utilizados na Simulacao

- **ESP32 DevKit C v4:** Microcontrolador principal. Escolhido por ser a plataforma padrao do processo seletivo e por oferecer ADC de 12 bits com atenuacao configuravel, necessario para leitura precisa do LDR.
- **LDR (ldr1):** Sensor fotorresistor `wokwi-photoresistor-sensor` conectado ao GPIO34 (ADC1 canal 6). O pino AO fornece a tensao do divisor resistivo (10K fixo entre VCC e AO, LDR entre AO e GND). Alta luminosidade reduz a resistencia do LDR, diminuindo a tensao em AO e, consequentemente, o valor ADC.
- **Botao (btn1):** Pushbutton `wokwi-pushbutton` no GPIO15 com pull-up interno. Configurado com `bounce: "0"` no diagram.json para comportamento deterministico nos testes CI, com debounce complementar por software.
- **Serial Monitor (UART):** Interface de saida para logs e telemetria, unica forma de saida disponivel no ambiente de CI do Wokwi.

## Decisoes Tecnicas Relevantes

### Leitura analogica (AO) em vez de saida digital (DO)

O modulo LDR possui um pino DO que comuta em um threshold fixo de tensao (~2.5V, equivalente a ~100 lux com os parametros padrao). Esse threshold fixo nao oferece margem segura para distinguir os cenarios do teste: 50 lux (objeto bloqueando) e 800 lux (esteira livre). Ambos estariam do mesmo lado do threshold fixo se a referencia fosse ligeiramente deslocada. A leitura direta do pino AO via ADC permite definir um limiar personalizado (1500) com ampla margem de seguranca em ambas as direcoes.

### Escolha do GPIO34 para o LDR

O GPIO34 pertence ao ADC1 e e um pino exclusivamente de entrada (input-only) no ESP32. Isso elimina o risco de configura-lo acidentalmente como saida e causar curto-circuito no divisor resistivo — uma protecao adicional relevante em ambiente embarcado. Alem disso, o ADC1 e independente do ADC2, que pode sofrer interferencia do Wi-Fi (embora nao utilizado neste projeto, e uma boa pratica reserva-lo).

### Atenuacao ADC.ATTN_11DB

A atenuacao de 11dB amplia o range de leitura do ADC para aproximadamente 0-3.6V. Com VCC de 3.3V no ESP32, o divisor resistivo do LDR produz tensoes entre ~0.4V (500 lux) e ~2.0V (50 lux). Sem atenuacao (ATTN_0DB, range 0-1.1V), os valores acima de 1.1V seriam saturados, impossibilitando a leitura correta do estado de bloqueio (50 lux produz ~2.04V).

### Threshold ADC de 1500

O valor foi calculado com base na formula de resistencia do LDR fornecida pelo Wokwi: R = rl10 * (10/lux)^gamma, com rl10=50k e gamma=0.7.

- **50 lux (bloqueado):** R ≈ 16.2k, V_AO = 3.3 * 16200/(16200+10000) ≈ 2.04V, ADC ≈ 2321
- **800 lux (livre):** R ≈ 2.25k, V_AO = 3.3 * 2250/(2250+10000) ≈ 0.61V, ADC ≈ 690

O threshold de 1500 situa-se exatamente no ponto medio, com margem de 810 pontos ADC (≈27% da faixa) para cada lado — robusto mesmo com variacao de componentes ou ruido.

### Timer com `time.ticks_diff()` em vez de `time.time()` ou `time.sleep()`

`time.ticks_ms()` retorna um contador de milissegundos de 32 bits que wrappa a cada ~12 horas. A funcao `ticks_diff()` trata esse wrap-around automaticamente usando aritmetica modular, tornando a medicao de intervalos imune a overflow — essencial para um sistema embarcado que pode operar por turnos prolongados. `time.sleep()` foi evitado para temporizacao porque e bloqueante e impediria a leitura simultanea do botao durante a espera.

### Debounce por software com `ticks_diff()`

Embora o botao no diagram.json tenha bounce desabilitado (`"bounce": "0"`), o debounce por software foi mantido como camada adicional de seguranca, alinhado ao requisito do LIGHT.md ("a leitura do botao btn1 deve conter um tratamento de debounce"). A implementacao usa o mesmo `ticks_diff()` do timer de micro-parada, mantendo consistencia no codigo e exigindo apenas 50ms de estabilidade para aceitar uma transicao — valor padrao para pushbuttons mecanicos (tipicamente 10-50ms).

### Separacao em funcoes com responsabilidade unica

O codigo foi organizado em tres funcoes (`read_ldr_state`, `handle_ldr_transition`, `handle_button`) que encapsulam comportamentos independentes. Isso permite testar mentalmente cada modulo isoladamente: a leitura do sensor, a maquina de estados e o tratamento do botao sao completamente desacoplados. O loop principal fica reduzido a 6 linhas, facilitando a compreensao do fluxo geral e futuras manutencoes.

## Resultados Obtidos

O sistema atende todos os requisitos do cenario LIGHT:

1. **Contagem de pecas (test_1):** Detecta corretamente a borda de subida da luminosidade (50->800 lux) e incrementa o contador. A contagem so ocorre na saida do objeto, nunca na entrada, eliminando falsos positivos por trepidacao.
2. **Micro-parada (test_2):** Identifica bloqueio continuo superior a 5 segundos e emite alerta unico. O flag `micro_stop_alerted` impede disparos repetidos, mantendo o log serial limpo.
3. **Reset de turno (test_3):** Responde ao acionamento do botao com debounce de 50ms, zerando contador, estado de bloqueio e flag de micro-parada em uma unica operacao atomica.

Alem dos cenarios de teste, o codigo trata edge cases como:
- Wrap-around do contador de `ticks_ms()` (tratado por `ticks_diff`)
- Bouncing de botao (filtrado pelo debounce)
- Transicoes espurias do LDR (so bordas de subida incrementam)
- Bloqueio inicial ao ligar (timer so inicia apos confirmacao de estado)

## Comentarios Adicionais (Opcional)

O principal desafio foi adaptar a tabela de referencia do Wokwi (calculada para VCC=5V) para a tensao de operacao de 3.3V do ESP32, recalibrando os valores ADC esperados para cada nivel de lux. O calculo foi validado com a formula de resistencia do LDR fornecida na documentacao oficial do componente.

Com mais tempo, seria interessante adicionar:
- Display OLED para visualizacao local do contador e status
- Calculo de pecas por minuto (PPM) para metricas de produtividade em tempo real
- Interface Wi-Fi para envio de telemetria a um dashboard remoto
- Memoria nao-volatil (NVS) para preservar o contador entre reinicializacoes
