# obd/vag_dtc_smart_guide.py
# ══════════════════════════════════════════════════════════════════════════════
# Guía Inteligente de Averías Oficiales VAG (Audi A6 C6 / Grupo VAG).
# Proporciona:
#   1. Identificación técnica de componente según esquemas eléctricos Audi (N, G, V, F, J).
#   2. Ubicación física exacta en el vehículo (dónde meter la mano).
#   3. Causas típicas y puntos débiles reconocidos en el Audi A6 C6 (4F).
#   4. Pasos de comprobación y solución de taller recomendada.
# ══════════════════════════════════════════════════════════════════════════════

from typing import Dict, Optional


GUIA_DTC_VAG: Dict[str, dict] = {
    # ── AIRBAG Y SEGURIDAD PASIVA (MÓDULO 15) ──
    "01217": {
        "sistema": "Airbags / Seguridad Pasiva (Módulo 15)",
        "componente": "Detonador Airbag Lateral Delantero Conductor (N199)",
        "ubicacion": "Debajo del asiento del conductor. Conector amarillo de 3 pines ubicado en el mazo de cables que sube por la guía del asiento.",
        "causas_tipicas": "Holgura en los terminales de la clema amarilla bajo el asiento producida al regular la posición del asiento longitudinalmente (95% de los casos en A6 C6). Rara vez detonador defectuoso.",
        "comprobacion": "1. Desconectar la batería (borne negativo) y esperar 5 minutos.\n2. Localizar el conector amarillo bajo el asiento del conductor.\n3. Desconectar y aplicar limpiador de contactos residuo cero (evitar polímetro directo en pines de airbag por riesgo de detonación).\n4. Ajustar ligeramente la presión de los pines metálicos y fijar con una brida para evitar vibraciones.\n5. Borrar el fallo en la centralita 15 con la app.",
    },
    "01218": {
        "sistema": "Airbags / Seguridad Pasiva (Módulo 15)",
        "componente": "Detonador Airbag Lateral Delantero Acompañante (N200)",
        "ubicacion": "Debajo del asiento del copiloto. Conector amarillo de 3 pines en la base del asiento.",
        "causas_tipicas": "Falso contacto en la clema amarilla al mover el asiento del copiloto o aspirar debajo.",
        "comprobacion": "Procedimiento idéntico al asiento del conductor: limpieza de conector amarillo bajo el asiento del acompañante, ajuste de pines y borrado con la app.",
    },
    "00588": {
        "sistema": "Airbags / Seguridad Pasiva (Módulo 15)",
        "componente": "Detonador Airbag Conductor / Volante (N95)",
        "ubicacion": "En el centro del volante, detrás del módulo del claxon y conectado al anillo de la columna de dirección.",
        "causas_tipicas": "Pistas flex rotas o desgastadas en el Anillo de Airbag / Carrete de Dirección (Clockspring) tras muchos giros de volante.",
        "comprobacion": "1. Comprobar si los mandos del volante o la bocina también fallan a ratos al girar.\n2. Si la resistencia es > 5 Ω constante independientemente del giro, sustituir el anillo de airbag (módulo 16 / anillo de dirección).",
    },
    "00589": {
        "sistema": "Airbags / Seguridad Pasiva (Módulo 15)",
        "componente": "Detonador Airbag Frontal Acompañante (N131)",
        "ubicacion": "Detrás de la guantera del copiloto, en la parte superior del salpicadero.",
        "causas_tipicas": "Clema de conexión detrás de la guantera floja o interruptor de desactivación por llave defectuoso.",
        "comprobacion": "Desmontar la guantera (5 tornillos Torx T20), inspeccionar la clema amarilla superior del airbag y comprobar el cableado.",
    },
    "01221": {
        "sistema": "Airbags / Seguridad Pasiva (Módulo 15)",
        "componente": "Sensor de Colisión Lateral / Puerta Conductor (G179)",
        "ubicacion": "En el interior del panel de la puerta del conductor, fijado a la chapa interior cerca del altavoz.",
        "causas_tipicas": "Cables cortados en el fuelle de goma que une la puerta con el chasis (pilar A), o entrada de agua por la guía de la ventanilla.",
        "comprobacion": "Inspeccionar los cables del pasamuros de goma de la puerta del conductor antes de cambiar el sensor.",
    },
    "01222": {
        "sistema": "Airbags / Seguridad Pasiva (Módulo 15)",
        "componente": "Sensor de Colisión Lateral / Puerta Copiloto (G180)",
        "ubicacion": "En el interior del panel de la puerta del acompañante.",
        "causas_tipicas": "Cables cortados en el fuelle de goma de la puerta del acompañante.",
        "comprobacion": "Retirar el fuelle de goma entre puerta y pilar A y verificar si hay cables partidos o deshilachados.",
    },

    # ── MOTOR 2.7 / 3.0 V6 TDI (MÓDULO 01) ──
    "P0671": {
        "sistema": "Gestión Motor V6 TDI (Módulo 01)",
        "componente": "Bujía de Precalentamiento / Calentador Cilindro 1 (Q10)",
        "ubicacion": "Culata delantera derecha (Banco 1, cilindro frontal más cercano al radiador).",
        "causas_tipicas": "Resistencia del calentador quemada internamente (abierta) o pipeta de conexión sulfatada.",
        "comprobacion": "1. Medir con polímetro en resistencia entre la punta del calentador y masa: debe dar 0.5 a 1.2 Ω. Si da infinito, está fundido.\n2. Sustituir aplicando par de apriete exacto (15-18 Nm) con motor tibio.",
    },
    "P0672": {
        "sistema": "Gestión Motor V6 TDI (Módulo 01)",
        "componente": "Bujía de Precalentamiento / Calentador Cilindro 2 (Q11)",
        "ubicacion": "Culata derecha (Banco 1, cilindro central).",
        "causas_tipicas": "Calentador quemado o resistencia interna degradada.",
        "comprobacion": "Medir resistencia con polímetro (nominal ~0.8 Ω). Sustituir si supera los 2.5 Ω o da circuito abierto.",
    },
    "P0673": {
        "sistema": "Gestión Motor V6 TDI (Módulo 01)",
        "componente": "Bujía de Precalentamiento / Calentador Cilindro 3 (Q12)",
        "ubicacion": "Culata derecha (Banco 1, cilindro trasero más cercano al habitáculo).",
        "causas_tipicas": "Calentador quemado.",
        "comprobacion": "Medir resistencia ohmica. Comprobar que le llega tensión positiva momentánea al dar contacto.",
    },
    "P0674": {
        "sistema": "Gestión Motor V6 TDI (Módulo 01)",
        "componente": "Bujía de Precalentamiento / Calentador Cilindro 4 (Q13)",
        "ubicacion": "Culata izquierda (Banco 2, cilindro frontal más cercano al radiador).",
        "causas_tipicas": "Calentador quemado.",
        "comprobacion": "Medición de resistencia y sustitución del calentador del cilindro 4.",
    },
    "P0675": {
        "sistema": "Gestión Motor V6 TDI (Módulo 01)",
        "componente": "Bujía de Precalentamiento / Calentador Cilindro 5 (Q14)",
        "ubicacion": "Culata izquierda (Banco 2, cilindro central).",
        "causas_tipicas": "Calentador fundido.",
        "comprobacion": "Sustitución recomendada de la bujía de precalentamiento cil. 5.",
    },
    "P0676": {
        "sistema": "Gestión Motor V6 TDI (Módulo 01)",
        "componente": "Bujía de Precalentamiento / Calentador Cilindro 6 (Q15)",
        "ubicacion": "Culata izquierda (Banco 2, cilindro trasero junto a la bomba de alta presión).",
        "causas_tipicas": "Calentador fundido.",
        "comprobacion": "Sustitución del calentador del cilindro 6.",
    },
    "P0401": {
        "sistema": "Emisiones y Gases de Escape (Módulo 01)",
        "componente": "Sistema EGR (Válvula N18 / Enfriador EGR)",
        "ubicacion": "Parte trasera de la V del motor, entre los colectores de admisión y el turbo.",
        "causas_tipicas": "Carbonilla y hollín acumulados en el cuerpo de la válvula EGR y en el tubo de recirculación metálico que reducen el caudal de aire recirculado.",
        "comprobacion": "1. Desmontar el tubo metálico de la EGR e inspeccionar el grado de carbonilla.\n2. Limpiar el cuerpo de la válvula EGR con desengrasante para admisión y comprobar que la mariposa se mueve suavemente sin atascarse.\n3. Ejecutar ajuste básico de EGR en la app.",
    },
    "P2015": {
        "sistema": "Admisión Variable V6 TDI (Módulo 01)",
        "componente": "Chapaletas de Colector de Admisión / Servomotores V157 / V275",
        "ubicacion": "Sobre los colectores de admisión de plástico en ambas culatas (Banco 1 derecha, Banco 2 izquierda).",
        "causas_tipicas": "Holgura en las bieletas articuladas de plástico o desgaste de los topes mecánicos que hacen que el servomotor sobrepase el límite de ángulo (0-90°).",
        "comprobacion": "1. Comprobar si las varillas tienen juego suelto.\n2. Instalar el tope metálico de refuerzo P2015 en el servomotor.\n3. Ejecutar la función 'Ajuste Básico Chapaletas V157' en la pestaña Mantenimiento de la app.",
    },
    "P0299": {
        "sistema": "Sobrealimentación y Turbo (Módulo 01)",
        "componente": "Turbocompresor / Válvula Reguladora de Presión N75",
        "ubicacion": "Turbo en el centro de la V del motor / N75 junto al paso de rueda delantero izquierdo.",
        "causas_tipicas": "Fuga de aire en los manguitos de intercooler (manguito de goma agrietado tras la curva), geometría variable del turbo atascada por carbonilla o actuador electrónico del turbo con soldaduras frías.",
        "comprobacion": "1. Inspeccionar visualmente si hay manchas de aceite en los tubos del intercooler (indica fuga de presión).\n2. Comprobar el recorrido suave de la varilla del actuador de la geometría variable.",
    },

    # ── FRENOS, DIRECCIÓN Y SUSPENSIÓN (MÓDULOS 03, 16) ──
    "00778": {
        "sistema": "Frenos ABS/ESP y Dirección (Módulos 03 / 16)",
        "componente": "Sensor de Ángulo de Dirección (G85)",
        "ubicacion": "En la columna de dirección, detrás del volante y solidario al anillo del airbag.",
        "causas_tipicas": "Pérdida de la calibración de cero tras desconectar la batería o alineación de ruedas.",
        "comprobacion": "1. Poner las ruedas en línea recta y el volante nivelado.\n2. Ejecutar la función 'Calibración Sensor G85' en la pestaña Mantenimiento de la app (Login 40168).\n3. El testigo ESP se apagará inmediatamente.",
    },
    "00283": {
        "sistema": "Frenos ABS / ESP (Módulo 03)",
        "componente": "Sensor de Velocidad Rueda Delantera Izquierda (G47)",
        "ubicacion": "Buje de la rueda delantera izquierda, enfrente de la corona dentada/magnética del rodamiento.",
        "causas_tipicas": "Sensor sucio con ferralla metálica de las pastillas de freno, cableado rozado con el amortiguador o rodamiento con banda magnética dañada.",
        "comprobacion": "Extraer el sensor con tornillo Allen de 5 mm, limpiar el sensor magnético y verificar con el polímetro la señal de pulsos al girar la rueda.",
    },
    "00285": {
        "sistema": "Frenos ABS / ESP (Módulo 03)",
        "componente": "Sensor de Velocidad Rueda Delantera Derecha (G45)",
        "ubicacion": "Buje de la rueda delantera derecha.",
        "causas_tipicas": "Suciedad o cable cortado en el paso de rueda.",
        "comprobacion": "Limpieza del sensor y verificación de continuidad en el conector del paso de rueda.",
    },

    # ── CONFORT Y CARROCERÍA (MÓDULOS 09, 46, 52) ──
    "00928": {
        "sistema": "Cierre Centralizado y Confort (Módulos 42 / 46)",
        "componente": "Unidad de Cierre de Puerta del Conductor (F220)",
        "ubicacion": "Dentro de la puerta del conductor, mecanismo de la cerradura.",
        "causas_tipicas": "Microinterruptor (microswitch) desgastado dentro de la cerradura. El coche no detecta si la puerta se abre (la luz de cortesía no enciende o el coche se vuelve a cerrar solo).",
        "comprobacion": "Sustituir el microinterruptor de la cerradura o la cerradura completa.",
    },
    "00929": {
        "sistema": "Cierre Centralizado y Confort (Módulos 52 / 46)",
        "componente": "Unidad de Cierre de Puerta del Copiloto (F221)",
        "ubicacion": "Dentro de la puerta del acompañante.",
        "causas_tipicas": "Microswitch de puerta del acompañante defectuoso.",
        "comprobacion": "Comprobar si el cuadro marca la puerta abierta al abrir la puerta del copiloto.",
    },
    "01044": {
        "sistema": "Codificación de Centralita (Varios Módulos)",
        "componente": "Unidad de Control Mal Codificada (Control Module Incorrectly Coded)",
        "ubicacion": "Módulo afectado (Gateway 19, Confort 46 o Motor 01).",
        "causas_tipicas": "Se grabó un valor de Long Coding que no concuerda con el equipamiento real del coche (ej: marcar xenon cuando lleva halógenas, o marcar cambio manual en un automático).",
        "comprobacion": "Restaurar la codificación original mediante el 'Comparador Diff de Backups' de la app o revisar la lista de equipamiento del Gateway.",
    },
    "01598": {
        "sistema": "Gestión de Batería y Red de Bordo (Módulo 19 - Gateway / BEM)",
        "componente": "Tensión de la Batería del Vehículo (BEM J644 / J533)",
        "ubicacion": "Batería en maletero y módulo Gateway J533 bajo el salpicadero.",
        "causas_tipicas": "Tensión de batería por debajo de 11.8V en reposo. Batería degradada, alternador sin carga o consumo parásito en reposo.",
        "comprobacion": "1. Medir tensión en bornes del vano motor.\n2. Si la batería tiene más de 5 años, sustituir y codificar con el asistente BEM en la pestaña Mantenimiento de la app.",
    },

    # ── ALARMA ANTIRROBO DWA (MÓDULO 46 CONFORT / BCM2 J393) ──
    "01134": {
        "sistema": "Alarma Antirrobo DWA (Módulo 46 - Confort)",
        "componente": "Bocina / Sirena de Alarma con Batería Integrada (H12)",
        "ubicacion": "En el vano motor, debajo del torpedo vierteaguas (zona del mecanismo de limpiaparabrisas) o tras la aleta delantera derecha.",
        "causas_tipicas": "⭐ EL FALLO ESTRELLA DEL A6 C6: Las pilas recargables de Ni-MH internas de la sirena H12 han envejecido, sulfatado y derramado ácido sobre la placa de circuito impreso. El cortocircuito interno hace que la alarma se DISPARE SOLA aleatoriamente por la noche.",
        "comprobacion": "1. Si suena de noche sin motivo, el 90% es la sirena H12.\n2. Desconectar la clavija de la sirena H12 para comprobar si cesan los disparos.\n3. Sustituir la sirena H12 (ref. 1K0 951 605 o 8K0 951 605) o abrirla con cúter para desoldar las pilas sulfatadas y limpiar con alcohol isopropílico.",
    },
    "01370": {
        "sistema": "Alarma Antirrobo DWA (Módulo 46 - Confort)",
        "componente": "Sensor de Vigilancia del Habitáculo / Volumétrico (G273)",
        "ubicacion": "En el plafón superior de luces del techo (junto al retrovisor interior).",
        "causas_tipicas": "Una polilla, mosca o araña atrapada dentro del coche de noche; ventanilla dejada 1 cm abierta con corriente de aire; o sensor ultrasónico descalibrado.",
        "comprobacion": "1. Pulsar el botón de desactivación de volumétricos (en el canto de la puerta del conductor) antes de cerrar el coche.\n2. Si la alarma no vuelve a saltar, revisar que no haya insectos o ajustar sensibilidad en adaptación del módulo 46.",
    },
    "01371": {
        "sistema": "Alarma Antirrobo DWA (Módulo 46 - Confort)",
        "componente": "Interruptor de Contacto de Puerta Conductor (F2)",
        "ubicacion": "Integrado dentro de la cerradura eléctrica de la puerta del conductor.",
        "causas_tipicas": "Microinterruptor (microswitch) de la cerradura desgastado. Falso contacto de puerta abierta cuando el coche está cerrado.",
        "comprobacion": "Verificar si la luz de cortesía de la puerta parpadea o si el cuadro marca puerta abierta de forma intermitente.",
    },
    "01574": {
        "sistema": "Alarma Antirrobo DWA (Módulo 46 - Confort)",
        "componente": "Interruptor de Contacto del Capó Motor (F266)",
        "ubicacion": "En el cierre central del capó delantero, dentro del pestillo del radiador.",
        "causas_tipicas": "Humedad, grasa o suciedad en el microswitch del pestillo del capó. Al enfriarse el coche de noche, el contacto dilata y dispara la alarma.",
        "comprobacion": "1. Desconectar la clema de 2 pines del cierre del capó y limpiar con limpiacontactos.\n2. Verificar en el cuadro de instrumentos si el aviso de capó abierto aparece correctamente.",
    },
    "01572": {
        "sistema": "Alarma Antirrobo DWA (Módulo 46 - Confort)",
        "componente": "Sensor de Inclinación y Antirremolque (G384)",
        "ubicacion": "Bajo la consola central o en el lateral derecho del maletero.",
        "causas_tipicas": "El coche está aparcado en una cuesta muy inclinada, suspensión neumática bajando lentamente por la noche, o sensor de aceleración descalibrado.",
        "comprobacion": "Pulsar el botón de desactivación de remolque (en la puerta del conductor) al aparcar para comprobar si el sensor es el causante.",
    },
}


def obtener_ficha_dtc(codigo: str, descripcion_base: str = "") -> dict:
    """
    Obtiene la ficha técnica guiada con ubicación física, causas típicas y solución recomendada.
    Si el código no está en la base enriquecida, genera un diagnóstico estructurado
    analizando el código y las siglas de componente oficial VAG (N, G, V, F, J).
    """
    c_limpio = str(codigo).strip().upper().replace("VAG ", "").replace("DTC ", "")
    
    # Búsqueda exacta
    for k, v in GUIA_DTC_VAG.items():
        if k in c_limpio or c_limpio in k:
            return {
                "codigo": codigo,
                "encontrado": True,
                **v
            }

    # Análisis heurístico por familia de componente oficial VAG
    tipo_comp = "Componente electrónico general"
    ubicacion_heur = "Consultar el esquema eléctrico del módulo correspondiente."
    
    desc_u = descripcion_base.upper()
    if "(N" in desc_u:
        tipo_comp = "Electroválvula, Inyector o Detonador Pirotécnico (Prefijo Oficial 'N')"
        ubicacion_heur = "Actuador eléctrico cableado a la unidad de control del módulo."
    elif "(G" in desc_u:
        tipo_comp = "Sensor o Captador de Medición (Prefijo Oficial 'G')"
        ubicacion_heur = "Sensor físico en bloque motor, ruedas, columna o carrocería."
    elif "(V" in desc_u:
        tipo_comp = "Motor Eléctrico o Servomotor de Regulación (Prefijo Oficial 'V')"
        ubicacion_heur = "Actuador mecánico motorizado (chapaleta, bomba o pinza de freno)."
    elif "(F" in desc_u:
        tipo_comp = "Interruptor o Conmutador Mecánico (Prefijo Oficial 'F')"
        ubicacion_heur = "Mando, pedal, cerradura o sensor de final de carrera."
    elif "(J" in desc_u:
        tipo_comp = "Unidad de Control Electrónica / Centralita (Prefijo Oficial 'J')"
        ubicacion_heur = "Módulo de gestión electrónica conectado al bus CAN."

    return {
        "codigo": codigo,
        "encontrado": False,
        "sistema": "Módulo de Control VAG",
        "componente": tipo_comp,
        "ubicacion": ubicacion_heur,
        "causas_tipicas": "Falso contacto en conector, caída de tensión en línea de alimentación o componente interno averiado.",
        "comprobacion": "1. Verificar alimentación y masa con polímetro.\n2. Comprobar continuidad del cableado hasta la centralita.\n3. Borrar la avería tras subsanar el circuito."
    }
