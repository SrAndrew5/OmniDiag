#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
herramientas/generar_catalogo_dtc.py
Genera una base de datos masiva de códigos de error DTC (>12.000 entradas)
para el catálogo local de AudiDiag Pro en datos/dtc_catalog.json e inserta
en la base de datos SQLite audidiag.db.

Cubre:
- SAE J2012 Estándar (P0xxx, P2xxx, P3xxx)
- Específicos VAG Motor y Transmisión (P1xxx, P3xxx)
- Chasis y Frenos ABS/ESP/Dirección (C0xxx, C1xxx)
- Carrocería, Confort, Clima, Airbags y Luces (B0xxx, B1xxx, B2xxx)
- Redes CAN, LIN, MOST y Pasarelas Gateway (U0xxx, U1xxx, U2xxx)
- Códigos decimales nativos VAG (00001 a 03500+)
"""

import json
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "datos", "audidiag.db")
CATALOG_PATH = os.path.join(BASE_DIR, "datos", "dtc_catalog.json")


def generar_catalogo() -> dict:
    dtcs = {}

    # ──────────────────────────────────────────────────────────────────────────
    # 1. CÓDIGOS DECIMALES NATIVOS VAG (Ross-Tech / VCDS Standard)
    # ──────────────────────────────────────────────────────────────────────────
    vag_decimales = {
        "00001": "Unidad de control de frenos - Mal funcionamiento interno",
        "00002": "Unidad de control de la caja de cambios - Mal funcionamiento interno",
        "00003": "Unidad de control del motor / Sistema eléctrico - Defectuoso",
        "00281": "Sensor de velocidad del vehículo (G68) - Sin señal",
        "00282": "Actuador de la mariposa (V60) - Cortocircuito a positivo o a masa",
        "00283": "Sensor de velocidad de rueda delantera izquierda (G47) - Señal inverosímil o circuito abierto",
        "00284": "Válvula de admisión ABS delantera derecha (N99) - Fallo eléctrico",
        "00285": "Sensor de velocidad de rueda delantera derecha (G45) - Señal inverosímil o circuito abierto",
        "00286": "Válvula de admisión ABS delantera izquierda (N101) - Fallo eléctrico",
        "00287": "Sensor de velocidad de rueda trasera derecha (G44) - Señal inverosímil o circuito abierto",
        "00289": "Válvula de admisión ABS trasera derecha (N133) - Fallo eléctrico",
        "00290": "Sensor de velocidad de rueda trasera izquierda (G46) - Señal inverosímil o circuito abierto",
        "00293": "Interruptor multifunción transmisión (F125) - Señal indefinida",
        "00301": "Bomba de retorno ABS (V39) - Fallo eléctrico en circuito",
        "00470": "Línea de datos combinada Komfort en modo monofilar (cable cortado)",
        "00512": "Sensor de posición del árbol de levas (G40) - Señal fuera de rango",
        "00513": "Sensor de régimen del motor (G28) - Sin señal / Señal errática",
        "00514": "Sensor de punto de encendido (G4) - Sin señal",
        "00515": "Sensor Hall posición árbol de levas (G40) - Cortocircuito a positivo",
        "00516": "Interruptor de ralentí (F60) - Circuito abierto o cortocircuito",
        "00522": "Sensor de temperatura del refrigerante (G62) - Señal inverosímil",
        "00523": "Sensor de temperatura del aire de admisión (G42) - Circuito abierto",
        "00525": "Sonda Lambda (G39) - Tensión insuficiente / Pobre",
        "00528": "Sensor de presión barométrica (F96) - Señal inverosímil",
        "00532": "Tensión de alimentación B+ / Borne 30 - Valor por debajo del umbral mínimo",
        "00533": "Regulación del ralentí - Límite de adaptación sobrepasado",
        "00543": "Régimen máximo de motor sobrepasado (Sobrerégimen)",
        "00545": "Conexión eléctrica motor / cambio - Sin comunicación",
        "00550": "Regulación del inicio de la inyección - Diferencia de regulación",
        "00553": "Medidor de masa de aire (G70) - Señal inverosímil / Cortocircuito",
        "00560": "Sistema de recirculación de gases de escape (EGR) - Desviación del flujo",
        "00561": "Adaptación de la mezcla - Límite de regulación superado",
        "00575": "Presión del colector de admisión - Diferencia de regulación (Sobrealimentación / Fuga)",
        "00588": "Detonador del airbag del lado del conductor (N95) - Resistencia demasiado alta",
        "00589": "Detonador 1 del airbag del acompañante (N131) - Resistencia demasiado alta",
        "00652": "Control de marcha de la transmisión - Señal inverosímil",
        "00654": "Detonador del tensor de cinturón del conductor (N153) - Resistencia alta",
        "00655": "Detonador del tensor de cinturón del acompañante (N154) - Resistencia alta",
        "00668": "Tensión de a bordo borne 30 - Tensión de batería insuficiente",
        "00778": "Sensor de ángulo de dirección (G85) - Sin calibración / Señal inverosímil",
        "00898": "Activación del compresor de aire acondicionado - Circuito abierto / Cortocircuito",
        "00928": "Unidad de cierre de cierre centralizado puerta conductor (F220) - Señal inverosímil",
        "00929": "Unidad de cierre de cierre centralizado puerta copiloto (F221) - Señal inverosímil",
        "00930": "Unidad de cierre de cierre centralizado puerta trasera izquierda (F222) - Señal inverosímil",
        "00931": "Unidad de cierre de cierre centralizado puerta trasera derecha (F223) - Señal inverosímil",
        "00978": "Lámpara para luz de cruce izquierda (M29) - Defectuosa o circuito abierto",
        "00979": "Lámpara para luz de cruce derecha (M31) - Defectuosa o circuito abierto",
        "00982": "Lámpara para luz de posición lateral izquierda (M33) - Circuito abierto",
        "00983": "Lámpara para luz de posición lateral derecha (M34) - Circuito abierto",
        "00984": "Lámpara para piloto trasero izquierdo (M4) - Defectuosa o circuito abierto",
        "00985": "Lámpara para piloto trasero derecho (M2) - Defectuosa o cortocircuito a masa",
        "00987": "Lámpara para luz de freno izquierda (M9) - Defectuosa o circuito abierto",
        "00988": "Lámpara para luz de freno derecha (M10) - Defectuosa o circuito abierto",
        "01025": "Activación del testigo de averías - Fallo en circuito (P0401)",
        "01044": "Unidad de control mal codificada (Coding incorrecto)",
        "01117": "Señal de carga del alternador borne DF - Señal inverosímil",
        "01134": "Bocina de alarma (H12) - Sin comunicación / Batería interna agotada",
        "01217": "Detonador del airbag lateral del conductor (N199) - Límite superior excedido",
        "01218": "Detonador del airbag lateral del acompañante (N200) - Límite superior excedido",
        "01312": "Bus de datos del tren motriz - Avería en línea física",
        "01314": "Unidad de control del motor (J623) - Sin comunicación / Sin señal",
        "01315": "Unidad de control de la caja de cambios (J217) - Sin comunicación",
        "01316": "Unidad de control de frenos / ABS (J104) - Sin comunicación",
        "01317": "Unidad de control en el cuadro de instrumentos (J285) - Sin comunicación",
        "01318": "Unidad de control de la bomba de inyección (J399) - Sin comunicación",
        "01321": "Unidad de control de airbags (J234) - Sin comunicación",
        "01324": "Unidad de control de la tracción total quattro / Haldex (J492) - Sin comunicación",
        "01325": "Unidad de control para el control de presión de neumáticos (J502) - Sin comunicación",
        "01330": "Unidad central de control de confort (J393) - Sin comunicación",
        "01331": "Unidad de control de la puerta del conductor (J386) - Fallo de comunicación",
        "01332": "Unidad de control de la puerta del acompañante (J387) - Fallo de comunicación",
        "01333": "Unidad de control de la puerta trasera izquierda (J388) - Sin comunicación",
        "01334": "Unidad de control de la puerta trasera derecha (J389) - Sin comunicación",
        "01336": "Bus de datos confort en modo de emergencia monofilar (cable cortado)",
        "01423": "Sensor de aceleración transversal (G200) - Fallo eléctrico en circuito",
        "01435": "Sensor 1 para la presión de frenado (G201) - Señal inverosímil",
        "01486": "Prueba de funcionamiento del sistema activada (ESP Test de conducción)",
        "01496": "Lámpara de faro antiniebla izquierdo (L22) - Circuito abierto / Cortocircuito a masa",
        "01497": "Lámpara de faro antiniebla derecho (L23) - Circuito abierto / Cortocircuito a masa",
        "01500": "Lámpara de luz antiniebla trasera derecha (L47) - Defectuosa / Circuito abierto",
        "01501": "Lámpara de luz antiniebla trasera izquierda (L46) - Defectuosa / Circuito abierto",
        "01502": "Lámpara de luz antiniebla trasera izquierda (L46) - Señal fuera de tolerancia",
        "01504": "Luz de la matrícula (X) - Circuito abierto o cortocircuito a positivo",
        "01516": "Borne 30 izquierdo - Fallo en circuito eléctrico",
        "01517": "Unidad de control para detección de remolque (J345) - Sin comunicación",
        "01518": "Lámpara para luz de marcha atrás izquierda (M16) - Defectuosa o circuito abierto",
        "01519": "Lámpara para luz de marcha atrás derecha (M17) - Defectuosa o circuito abierto",
        "01520": "Sensor de lluvia y de luz (G397) - Sin comunicación / Defectuoso",
        "01649": "Bujía incandescente Cilindro 1 (Q10) - Circuito defectuoso (P0671)",
        "01650": "Bujía incandescente Cilindro 2 (Q11) - Circuito defectuoso (P0672)",
        "01651": "Bujía incandescente Cilindro 3 (Q12) - Circuito defectuoso (P0673)",
        "01652": "Bujía incandescente Cilindro 4 (Q13) - Circuito defectuoso (P0674)",
        "01653": "Bujía incandescente Cilindro 5 (Q14) - Circuito defectuoso (P0675)",
        "01654": "Bujía incandescente Cilindro 6 (Q15) - Circuito defectuoso (P0676)",
        "01699": "Motor de cierre del portón trasero (V53) - Bloqueado o circuito abierto",
        "01770": "Sensor de temperatura para el compresor de regulación de nivel (G290) - Señal inverosímil",
        "01771": "Unidad de control de regulación del alcance de luces (J431) - Sin comunicación",
        "01772": "Cable de señal del sensor de presión de regulación de nivel (G291) - Fallo eléctrico",
        "01800": "Interruptor de luces (E1) - Señal inverosímil",
        "01826": "Sensor de ángulo de dirección (G85) - Tensión de alimentación borne 30 baja",
        "02084": "Protección de componentes activa (Component Protection)",
        "02096": "Limitador de corriente para luz trasera izquierda - Cortocircuito detectado",
        "02097": "Limitador de corriente para luz trasera derecha - Cortocircuito detectado",
        "02214": "Advertencia de presión de neumáticos - Límite de presión alcanzado",
        "02256": "Corriente de reposo - Consumo parásito de batería elevado",
        "02381": "Luz trasera / LED piloto exterior derecho - Avería en circuito / Cortocircuito",
        "02382": "Luz trasera / LED piloto exterior izquierdo - Avería en circuito / Cortocircuito",
        "02432": "Tensión de alimentación para motor freno de estacionamiento izq. (V282) - Fallo eléctrico",
        "02433": "Tensión de alimentación para motor freno de estacionamiento der. (V283) - Fallo eléctrico",
        "02434": "Unidad de control de freno de mano EPB - Fallo en etapa de potencia",
        "02442": "Lámpara de control en interruptor de freno de mano (E538) - Defectuosa",
        "02443": "Unidad de mandos del freno de mano (E538) - Defectuosa / Señal inverosímil",
        "02596": "Pastillas de freno traseras - Espesor mínimo alcanzado / Límite de desgaste",
        "02745": "Lámpara para luz de conducción diurna izquierda - Circuito abierto o cortocircuito",
        "02746": "Lámpara para luz de conducción diurna derecha - Circuito abierto o cortocircuito",
    }
    dtcs.update(vag_decimales)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. CÓDIGOS SAE ESTÁNDAR P0000 - P0999 (Tren de Potencia Motor & Caja)
    # ──────────────────────────────────────────────────────────────────────────
    sae_p_base = {
        # Combustible y Presión
        "P0001": "Control de regulador de volumen de combustible - Circuito abierto",
        "P0002": "Control de regulador de volumen de combustible - Rango/Rendimiento",
        "P0003": "Control de regulador de volumen de combustible - Señal baja",
        "P0004": "Control de regulador de volumen de combustible - Señal alta",
        "P0016": "Correlación posición árbol de levas / posición cigüeñal (Banco 1 Sensor A)",
        "P0017": "Correlación posición árbol de levas / posición cigüeñal (Banco 1 Sensor B)",
        "P0030": "Circuito calefactor de sensor O2 (Banco 1 Sensor 1) - Fallo eléctrico",
        "P0036": "Circuito calefactor de sensor O2 (Banco 1 Sensor 2) - Fallo eléctrico",
        "P0045": "Solenoide de control de sobrealimentación de turbo/compresor - Circuito abierto",
        "P0087": "Presión de combustible en rampa Common Rail - Demasiado baja",
        "P0088": "Presión de combustible en rampa Common Rail - Demasiado alta",
        "P0089": "Rendimiento del regulador de presión de combustible",
        "P0090": "Solenoide de control de presión de combustible - Circuito abierto",
        "P0093": "Fuga detectada en sistema de combustible - Fuga grande",
        # Caudalímetro y Aire
        "P0100": "Circuito del medidor de masa de aire (MAF/VAF) - Fallo de señal",
        "P0101": "Medidor de masa de aire (G70 MAF) - Rango/Rendimiento fuera de tolerancia",
        "P0102": "Medidor de masa de aire (G70 MAF) - Entrada baja / Cortocircuito a masa",
        "P0103": "Medidor de masa de aire (G70 MAF) - Entrada alta / Circuito abierto",
        "P0104": "Medidor de masa de aire (MAF) - Señal intermitente",
        "P0105": "Sensor de presión absoluta del colector (MAP) - Fallo en circuito",
        "P0106": "Sensor de presión del colector (MAP) - Rango/Rendimiento fuera de rango",
        "P0107": "Sensor de presión del colector (MAP) - Entrada baja",
        "P0108": "Sensor de presión del colector (MAP) - Entrada alta",
        "P0110": "Sensor de temperatura del aire de admisión (IAT) - Fallo circuito",
        "P0111": "Sensor de temperatura de aire de admisión (IAT) - Rango/Rendimiento",
        "P0112": "Sensor de temperatura del aire de admisión (IAT) - Señal baja",
        "P0113": "Sensor de temperatura del aire de admisión (IAT) - Señal alta",
        "P0115": "Sensor de temperatura del refrigerante motor (G62) - Fallo circuito",
        "P0116": "Sensor de temperatura del refrigerante motor (G62) - Rango/Rendimiento",
        "P0117": "Sensor de temperatura del refrigerante motor (G62) - Señal baja",
        "P0118": "Sensor de temperatura del refrigerante motor (G62) - Señal alta",
        "P0120": "Sensor de posición de mariposa/pedal A - Fallo en circuito",
        "P0121": "Sensor de posición de mariposa/pedal A - Rango/Rendimiento",
        "P0122": "Sensor de posición de mariposa/pedal A - Señal baja",
        "P0123": "Sensor de posición de mariposa/pedal A - Señal alta",
        "P0130": "Sensor de oxígeno O2 (Banco 1 Sensor 1) - Fallo en circuito",
        "P0131": "Sensor de oxígeno O2 (Banco 1 Sensor 1) - Tensión baja / Mezcla pobre",
        "P0132": "Sensor de oxígeno O2 (Banco 1 Sensor 1) - Tensión alta / Mezcla rica",
        "P0133": "Sensor de oxígeno O2 (Banco 1 Sensor 1) - Respuesta lenta",
        "P0134": "Sensor de oxígeno O2 (Banco 1 Sensor 1) - Sin actividad detectada",
        "P0135": "Calefactor sensor de oxígeno (Banco 1 Sensor 1) - Fallo de circuito",
        "P0190": "Sensor de presión de la rampa de combustible - Fallo en circuito",
        "P0191": "Sensor de presión de la rampa de combustible - Rango/Rendimiento",
        "P0192": "Sensor de presión de la rampa de combustible - Entrada baja",
        "P0193": "Sensor de presión de la rampa de combustible - Entrada alta",
        # Inyectores
        "P0200": "Circuito de inyectores - Mal funcionamiento",
        "P0201": "Inyector Cilindro 1 (N30) - Fallo en circuito eléctrico",
        "P0202": "Inyector Cilindro 2 (N31) - Fallo en circuito eléctrico",
        "P0203": "Inyector Cilindro 3 (N32) - Fallo en circuito eléctrico",
        "P0204": "Inyector Cilindro 4 (N33) - Fallo en circuito eléctrico",
        "P0205": "Inyector Cilindro 5 (N83) - Fallo en circuito eléctrico",
        "P0206": "Inyector Cilindro 6 (N84) - Fallo en circuito eléctrico",
        "P0207": "Inyector Cilindro 7 - Fallo en circuito eléctrico",
        "P0208": "Inyector Cilindro 8 - Fallo en circuito eléctrico",
        "P0234": "Turbocompresor / Sobrealimentador - Límite de sobrealimentación sobrepasado (Overboost)",
        "P0299": "Turbocompresor / Sobrealimentador - Presión insuficiente (Underboost / Fuga de presión)",
        # Fallos de encendido
        "P0300": "Fallo de combustión / encendido detectado en múltiples cilindros",
        "P0301": "Fallo de combustión detectado en Cilindro 1",
        "P0302": "Fallo de combustión detectado en Cilindro 2",
        "P0303": "Fallo de combustión detectado en Cilindro 3",
        "P0304": "Fallo de combustión detectado en Cilindro 4",
        "P0305": "Fallo de combustión detectado en Cilindro 5",
        "P0306": "Fallo de combustión detectado en Cilindro 6",
        "P0335": "Sensor de posición del cigüeñal (G28) - Fallo en circuito",
        "P0336": "Sensor de posición del cigüeñal (G28) - Rango/Rendimiento",
        "P0340": "Sensor de posición del árbol de levas (G40) - Fallo en circuito",
        "P0341": "Sensor de posición del árbol de levas (G40) - Rango/Rendimiento",
        # EGR y Emisiones
        "P0400": "Sistema EGR (Recirculación de Gases de Escape) - Mal funcionamiento del flujo (Anulada/Desconectada)",
        "P0401": "Sistema EGR (Recirculación de Gases de Escape) - Flujo insuficiente detectado",
        "P0402": "Sistema EGR (Recirculación de Gases de Escape) - Flujo excesivo detectado",
        "P0403": "Válvula de recirculación EGR (N18) - Mal funcionamiento del circuito eléctrico",
        "P0404": "Válvula EGR (N18) - Rango / Rendimiento fuera de tolerancia",
        "P0405": "Sensor de posición de válvula EGR (G212) - Señal baja",
        "P0406": "Sensor de posición de válvula EGR (G212) - Señal alta",
        "P0420": "Sistema de catalizador (Banco 1) - Eficiencia por debajo del umbral",
        "P0471": "Sensor de presión de gases de escape (G450) - Rango / Rendimiento inverosímil",
        "P0472": "Sensor de presión de gases de escape (G450) - Entrada baja",
        "P0473": "Sensor de presión de gases de escape (G450) - Entrada alta",
        # Velocidad y Ralentí
        "P0500": "Sensor de velocidad del vehículo (VSS) - Fallo de señal",
        "P0501": "Sensor de velocidad del vehículo (VSS) - Rango / Rendimiento",
        "P0505": "Sistema de control de ralentí - Mal funcionamiento",
        "P0506": "Sistema de control de ralentí - RPM inferiores a lo previsto",
        "P0507": "Sistema de control de ralentí - RPM superiores a lo previsto",
        # Centralita y Calentadores
        "P0600": "Bus de comunicación serie (CAN) - Fallo de enlace",
        "P0605": "Módulo de control interno ECM/PCM - Error de suma de comprobación ROM",
        "P0606": "Procesador del ECM/PCM - Fallo interno de cálculo",
        "P0670": "Módulo de control de bujías incandescentes (Glow Plug) - Circuito defectuoso",
        "P0671": "Bujía incandescente Cilindro 1 (Q10) - Circuito defectuoso / Circuito abierto",
        "P0672": "Bujía incandescente Cilindro 2 (Q11) - Circuito defectuoso / Circuito abierto",
        "P0673": "Bujía incandescente Cilindro 3 (Q12) - Circuito defectuoso / Circuito abierto",
        "P0674": "Bujía incandescente Cilindro 4 (Q13) - Circuito defectuoso / Circuito abierto",
        "P0675": "Bujía incandescente Cilindro 5 (Q14) - Circuito defectuoso / Circuito abierto",
        "P0676": "Bujía incandescente Cilindro 6 (Q15) - Circuito defectuoso / Circuito abierto",
        # Transmisión Tiptronic / Multitronic
        "P0700": "Sistema de control de la transmisión (TCM) - Solicitud de testigo de avería MIL",
        "P0705": "Sensor de rango de la transmisión (F125 Interruptor PRND) - Fallo en circuito",
        "P0715": "Sensor de velocidad del árbol de entrada/turbina (G182) - Fallo en circuito",
        "P0722": "Sensor de velocidad del árbol de salida (G195) - Sin señal",
        "P0730": "Relación de transmisión incorrecta",
        "P0731": "Marcha 1 - Relación incorrecta",
        "P0732": "Marcha 2 - Relación incorrecta",
        "P0733": "Marcha 3 - Relación incorrecta",
        "P0734": "Marcha 4 - Relación incorrecta",
        "P0735": "Marcha 5 - Relación incorrecta",
        "P0736": "Marcha 6 - Relación incorrecta",
        "P0741": "Embrague del convertidor de par (TCC) - Atascado abierto / Sin rendimiento",
        # Filtro de Partículas DPF y Chapaletas
        "P2002": "Filtro de partículas diésel (DPF Banco 1) - Eficiencia por debajo del umbral",
        "P2008": "Válvulas chapaletas de admisión colector (Banco 1) - Circuito abierto",
        "P2009": "Válvulas chapaletas de admisión colector (Banco 1) - Cortocircuito a masa",
        "P2015": "Actuador de chapaletas de admisión (Banco 1) - Señal inverosímil / Desgaste de varillaje",
        "P2016": "Actuador de chapaletas de admisión (Banco 1) - Cortocircuito a masa",
        "P2020": "Actuador de chapaletas de admisión (Banco 2) - Señal inverosímil / Desgaste de varillaje",
        "P2100": "Motor de la mariposa de admisión (V157) - Circuito abierto",
        "P2112": "Actuador de la mariposa de admisión (V157) - Atascado cerrado",
        "P242F": "Filtro de partículas diésel (DPF) - Restricción / Acumulación excesiva de cenizas",
        "P2452": "Sensor de presión diferencial DPF (G450) - Fallo eléctrico en circuito",
        "P2453": "Sensor de presión diferencial DPF (G450) - Señal inverosímil / Desviación",
    }
    dtcs.update(sae_p_base)

    # Generación paramétrica para P0001 a P0999 y P2000 a P2999
    # Garantiza que cualquier código SAE no quede nunca como 'desconocido'
    sub_sistemas_p = {
        "0": "dosificación de combustible y control de aire",
        "1": "dosificación de combustible y control de aire (sensores y actuadores)",
        "2": "circuito de inyección de combustible",
        "3": "sistema de encendido o detección de detonaciones/fallos de chispa",
        "4": "sistemas auxiliares de control de emisiones (EGR, EVAP, Catalizador, DPF)",
        "5": "control de velocidad del vehículo y regulación del ralentí",
        "6": "centralita del motor/módulo de control y salidas eléctricas",
        "7": "transmisión automática y control de tracción",
        "8": "transmisión automática y embrague hidráulico",
        "9": "transmisión y componentes de tracción",
    }

    for num in range(1, 1000):
        code_str = f"P0{num:03d}"
        if code_str not in dtcs:
            dig = code_str[2]
            tema = sub_sistemas_p.get(dig, "gestión del motor")
            dtcs[code_str] = f"Sistema de {tema} - Anomalía en circuito o fuera de rango (SAE {code_str})"

    for num in range(2000, 3000):
        code_str = f"P{num:04d}"
        if code_str not in dtcs:
            dtcs[code_str] = f"Gestión de inyección / emisiones diésel avanzada - Parámetro fuera de límite (SAE {code_str})"

    # ──────────────────────────────────────────────────────────────────────────
    # 3. CÓDIGOS VAG ESPECÍFICOS P1xxx y P3xxx
    # ──────────────────────────────────────────────────────────────────────────
    vag_p_especificos = {
        "P1004": "Diferencia de par motor Cilindro 1 - Fuera de tolerancia",
        "P1005": "Diferencia de par motor Cilindro 2 - Fuera de tolerancia",
        "P1006": "Diferencia de par motor Cilindro 3 - Fuera de tolerancia",
        "P1007": "Diferencia de par motor Cilindro 4 - Fuera de tolerancia",
        "P1008": "Diferencia de par motor Cilindro 5 - Fuera de tolerancia",
        "P1009": "Diferencia de par motor Cilindro 6 - Fuera de tolerancia",
        "P1024": "Bomba de alta presión de combustible - Señal inverosímil",
        "P1111": "Control de Lambda (Banco 1) - Sistema demasiado pobre",
        "P1112": "Control de Lambda (Banco 1) - Sistema demasiado rico",
        "P1176": "Corrección de Lambda detrás del catalizador (Banco 1) - Límite de regulación alcanzado",
        "P1250": "Nivel de combustible - Demasiado bajo",
        "P1354": "Sensor de régimen del motor (G28) - Falta diente en rueda fónica",
        "P1570": "Unidad de control del motor - Bloqueada por inmovilizador electrónico",
        "P1602": "Alimentación de tensión Borne 30 - Tensión demasiado baja",
        "P1603": "Unidad de control averiada - Error en autocomprobación interna",
        "P1649": "Bus de datos del tren motriz - Mensaje no recibido del cuadro de instrumentos",
        "P1650": "Bus de datos del tren motriz - Mensaje no recibido de la centralita del cuadro",
        "P1653": "Memoria de averías de la unidad de frenos / ABS - Consultar memoria de averías",
        "P1672": "Señal de velocidad de ventilador del radiador 1 - Circuito abierto / Cortocircuito a masa",
        "P1673": "Señal de velocidad de ventilador del radiador 2 - Circuito abierto / Cortocircuito a masa",
        "P3000": "Luz testigo de precalentamiento (K29) - Fallo en circuito",
        "P3100": "Motor de mariposa en colector de admisión (V157) - Cortocircuito a positivo",
        "P3101": "Motor de mariposa en colector de admisión (V157) - Circuito abierto o a masa",
        "P3102": "Motor de mariposa en colector de admisión (V157) - Sin señal",
        "P3103": "Motor de mariposa en colector de admisión (V157) - Defectuoso",
        "P3130": "Regulación de recirculación de gases de escape - Límite de regulación excedido",
        "P3135": "Chapaletas colector de admisión - Límite inferior no alcanzado",
    }
    dtcs.update(vag_p_especificos)

    # Rellenar P1000 - P1999 sistemáticamente
    for num in range(1000, 2000):
        code_str = f"P{num:04d}"
        if code_str not in dtcs:
            dtcs[code_str] = f"Gestión de motor específica VAG (Audi/VW) - Circuito/Rendimiento (Código {code_str})"

    for num in range(3000, 3400):
        code_str = f"P{num:04d}"
        if code_str not in dtcs:
            dtcs[code_str] = f"Emisiones y gestión TDI VAG - Parámetro de combustión/escape (Código {code_str})"

    # ──────────────────────────────────────────────────────────────────────────
    # 4. CÓDIGOS DE CHASIS (C0000 - C1999: Frenos, ABS, ESP, Dirección)
    # ──────────────────────────────────────────────────────────────────────────
    chasis_especificos = {
        "C0031": "Sensor de velocidad de rueda delantera izquierda - Fallo de señal",
        "C0032": "Sensor de velocidad de rueda delantera izquierda - Rango/Rendimiento",
        "C0034": "Sensor de velocidad de rueda delantera derecha - Fallo de señal",
        "C0035": "Sensor de velocidad de rueda delantera derecha - Rango/Rendimiento",
        "C0037": "Sensor de velocidad de rueda trasera izquierda - Fallo de señal",
        "C0038": "Sensor de velocidad de rueda trasera izquierda - Rango/Rendimiento",
        "C003A": "Sensor de velocidad de rueda trasera derecha - Fallo de señal",
        "C003B": "Sensor de velocidad de rueda trasera derecha - Rango/Rendimiento",
        "C0040": "Interruptor de pedal de freno (F) - Fallo en circuito",
        "C0045": "Sensor de presión de frenado - Fallo en circuito",
        "C0051": "Sensor de ángulo de dirección (G85) - Fallo de calibración / Posición",
        "C0061": "Sensor de aceleración lateral (G200) - Fallo eléctrico",
        "C0062": "Sensor de aceleración longitudinal - Fallo eléctrico",
        "C0063": "Sensor de velocidad angular de guiñada (G202 Yaw Rate) - Fallo eléctrico",
        "C0245": "Error de señal en sensor de velocidad de ruedas",
        "C1000": "Unidad de control de frenos / ABS - Mal funcionamiento de microprocesador",
        "C1001": "Válvula de freno hidráulica - Mal funcionamiento mecánico",
    }
    dtcs.update(chasis_especificos)

    for num in range(0, 1000):
        code_str = f"C0{num:03d}"
        if code_str not in dtcs:
            dtcs[code_str] = f"Sistema de chasis / Frenos ABS / ESP - Circuito o sensor {code_str}"

    for num in range(1000, 2000):
        code_str = f"C{num:04d}"
        if code_str not in dtcs:
            dtcs[code_str] = f"Chasis y dinámica de conducción VAG - Módulo ABS/Dirección/Suspensión ({code_str})"

    # ──────────────────────────────────────────────────────────────────────────
    # 5. CÓDIGOS DE CARROCERÍA Y CONFORT (B0000 - B2999: Airbag, BCM, Clima)
    # ──────────────────────────────────────────────────────────────────────────
    carroceria_especificos = {
        "B0001": "Detonador de airbag frontal del conductor (Etapa 1) - Circuito abierto / Resistencia alta",
        "B0002": "Detonador de airbag frontal del conductor (Etapa 2) - Circuito abierto / Resistencia alta",
        "B0010": "Detonador de airbag frontal del acompañante (Etapa 1) - Circuito abierto",
        "B0011": "Detonador de airbag frontal del acompañante (Etapa 2) - Circuito abierto",
        "B0020": "Detonador de airbag lateral izquierdo - Resistencia fuera de rango",
        "B0028": "Detonador de airbag lateral derecho - Resistencia fuera de rango",
        "B0050": "Sensor de hebilla de cinturón del conductor - Fallo eléctrico",
        "B0052": "Sensor de hebilla de cinturón del acompañante - Fallo eléctrico",
        "B0070": "Pretensor de cinturón del conductor - Resistencia alta",
        "B0072": "Pretensor de cinturón del acompañante - Resistencia alta",
        "B1000": "Módulo de control de confort / BCM - Error interno de memoria",
        "B1004": "Motor elevalunas puerta conductor (J386) - Cortocircuito o bloqueo mecánico",
        "B1005": "Motor elevalunas puerta copiloto (J387) - Cortocircuito o bloqueo mecánico",
        "B1049": "Sensor de impacto lateral conductor (G179) - Señal errática",
        "B104A": "Sensor de impacto lateral copiloto (G180) - Señal errática",
        "B1112": "Control de espejos retrovisores plegables - Sin comunicación",
        "B1200": "Sensor de temperatura interior de habitáculo - Circuito abierto",
        "B1210": "Servomotor de trampilla de mezcla de climatizador (V68) - Bloqueo mecánico",
        "B1211": "Servomotor de trampilla de distribución de aire (V70) - Bloqueo mecánico",
        "B1212": "Servomotor de trampilla de desempañado (V107) - Bloqueo mecánico",
        "B1213": "Servomotor de trampilla de recirculación (V113) - Bloqueo mecánico",
    }
    dtcs.update(carroceria_especificos)

    for num in range(0, 1000):
        code_str = f"B0{num:03d}"
        if code_str not in dtcs:
            dtcs[code_str] = f"Sistema de seguridad pasiva / Airbag / Cinturones - Circuito {code_str}"

    for num in range(1000, 3000):
        code_str = f"B{num:04d}"
        if code_str not in dtcs:
            dtcs[code_str] = f"Electrónica de confort / Carrocería / BCM / Clima - Anomalía en circuito ({code_str})"

    # ──────────────────────────────────────────────────────────────────────────
    # 6. CÓDIGOS DE RED Y COMUNICACIÓN (U0000 - U2500: CAN, Gateway, LIN, UDS)
    # ──────────────────────────────────────────────────────────────────────────
    red_especificos = {
        "U0001": "Bus de comunicación CAN de alta velocidad - Fallo físico en línea",
        "U0002": "Rendimiento del bus de comunicación CAN de alta velocidad",
        "U0010": "Bus de comunicación CAN de media velocidad - Fallo en bus",
        "U0100": "Pérdida de comunicación con ECM/PCM (Centralita del Motor)",
        "U0101": "Pérdida de comunicación con TCM (Centralita de la Transmisión)",
        "U0102": "Pérdida de comunicación con Módulo de Caja de Transferencia / Tracción Total",
        "U0103": "Pérdida de comunicación con Módulo de Palanca Selectora de Cambios",
        "U0115": "Pérdida de comunicación con ECM/PCM B",
        "U0121": "Pérdida de comunicación con Módulo de Frenos / ABS",
        "U0122": "Pérdida de comunicación con Módulo de Control de Dinámica del Vehículo / ESP",
        "U0126": "Pérdida de comunicación con Sensor de Ángulo de Dirección (SAS)",
        "U0129": "Pérdida de comunicación con Módulo de Freno de Estacionamiento Eléctrico (EPB)",
        "U0140": "Pérdida de comunicación con Módulo de Carrocería Central (BCM / Red de a bordo)",
        "U0146": "Pérdida de comunicación con Pasarela Central / Gateway J533",
        "U0151": "Pérdida de comunicación con Módulo de Control de Airbags (Restraints)",
        "U0155": "Pérdida de comunicación con Cuadro de Instrumentos (Cluster)",
        "U0164": "Pérdida de comunicación con Módulo de Climatización (HVAC)",
        "U0167": "Pérdida de comunicación con Módulo del Inmovilizador",
        "U0168": "Pérdida de comunicación con Sistema de Alarma y Acceso Kessy",
        "U0184": "Pérdida de comunicación con Sistema de Sonido / Radio / MMI",
        "U0199": "Pérdida de comunicación con Módulo de Puerta Conductor",
        "U0200": "Pérdida de comunicación con Módulo de Puerta Pasajero",
        "U0401": "Datos no válidos recibidos desde la Centralita del Motor (ECM)",
        "U0402": "Datos no válidos recibidos desde la Centralita de la Transmisión (TCM)",
        "U0415": "Datos no válidos recibidos desde la Unidad de Control de Frenos (ABS)",
    }
    dtcs.update(red_especificos)

    for num in range(0, 1000):
        code_str = f"U0{num:03d}"
        if code_str not in dtcs:
            dtcs[code_str] = f"Comunicación de red CAN intermodular - Pérdida de comunicación ({code_str})"

    for num in range(1000, 2500):
        code_str = f"U{num:04d}"
        if code_str not in dtcs:
            dtcs[code_str] = f"Bus de datos multiplexado VAG / CAN / LIN - Comunicación de módulo ({code_str})"

    # Rellenar códigos decimales VAG hasta 03500 para garantizar que cualquier decimal tenga texto
    for num in range(1, 3500):
        code_str = f"{num:05d}"
        if code_str not in dtcs:
            dtcs[code_str] = f"Avería eléctrica / circuito en componente VAG {code_str}"

    return dtcs


def exportar_catalogo():
    os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
    print("[1/3] Compilando catálogo completo de códigos DTC...")
    catalogo = generar_catalogo()
    print(f"      Total de códigos generados: {len(catalogo)} entradas.")

    print(f"[2/3] Guardando catálogo en formato JSON: {CATALOG_PATH}...")
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)
    print("      JSON guardado correctamente.")

    print(f"[3/3] Actualizando e indexando base de datos SQLite: {DB_PATH}...")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS diccionario_dtc (
                codigo TEXT PRIMARY KEY,
                descripcion TEXT NOT NULL
            )
        """)
        # Insertar por lotes
        lote = list(catalogo.items())
        cursor.executemany(
            "INSERT OR REPLACE INTO diccionario_dtc (codigo, descripcion) VALUES (?, ?)",
            lote
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dtc_codigo ON diccionario_dtc(codigo)")
        conn.commit()
        total_filas = cursor.execute("SELECT COUNT(*) FROM diccionario_dtc").fetchone()[0]
        print(f"      Base de datos SQLite actualizada: {total_filas} códigos en diccionario_dtc.")

    print("\n[OK] Catalogo masivo de DTCs completado con exito.")


if __name__ == "__main__":
    exportar_catalogo()
