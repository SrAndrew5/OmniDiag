"""
Catálogo oficial de codificaciones y funciones de confort para Audi A6 C6 (4F Facelift, 2008-2011).
Específicamente verificado para Audi A6 2.7 TDI V6 (2010) con protocolo CAN + UDS.

Módulos cubiertos:
- Confort / Electrónica (46) - BCM2 J393 / Centralita de confort
- Central Eléctrica / Luces (09) - BCM1 J519 / Red de a bordo
- Cuadro de Instrumentos (17) - J285 Combinado de instrumentos
- ABS / ESP (03) - Bloque de frenos y estabilidad
- Motor (01) - EDC17 Gestión motor 2.7 TDI
"""

CATALOGO_CONFORT_A6 = {
    "Confort / Electrónica (46)": [
        # ── RETROVISORES Y ESPEJOS ──
        {
            "id": "plegado_espejos_mando",
            "nombre": "Plegado de retrovisores al cerrar coche",
            "desc": "Pliega los espejos retrovisores automáticamente al pulsar el botón de cerrar en el mando a distancia.",
            "byte": 4,
            "bit": 4,
        },
        {
            "id": "despliegue_espejos_abrir",
            "nombre": "Despliegue de retrovisores al abrir con mando",
            "desc": "Despliega los espejos retrovisores automáticamente al pulsar el botón de abrir en el mando a distancia.",
            "byte": 4,
            "bit": 6,
        },
        {
            "id": "despliegue_espejos_contacto",
            "nombre": "Despliegue de retrovisores al encender contacto",
            "desc": "Mantiene los espejos plegados al abrir puertas y los despliega solo al poner el contacto del motor (evita desplegar si solo recoges algo del coche).",
            "byte": 4,
            "bit": 7,
        },
        {
            "id": "espejo_marcha_atras",
            "nombre": "Inclinación espejo copiloto en marcha atrás",
            "desc": "Baja automáticamente el cristal del espejo derecho al engranar marcha atrás para enfocar el bordillo y proteger las llantas.",
            "byte": 4,
            "bit": 3,
        },
        {
            "id": "menu_espejos_mmi",
            "nombre": "Menú confort de retrovisores en pantalla MMI",
            "desc": "Habilita la opción 'Plegar retrovisores' dentro del menú Car > Sistemas > Cierre centralizado de la pantalla MMI.",
            "byte": 7,
            "bit": 7,
        },
        # ── ILUMINACIÓN Y BIENVENIDA ──
        {
            "id": "coming_home",
            "nombre": "Luces de bienvenida (Coming Home)",
            "desc": "Mantiene encendidas las luces exteriores temporalmente tras apagar el motor y cerrar el coche.",
            "byte": 0,
            "bit": 6,
        },
        {
            "id": "leaving_home",
            "nombre": "Luces de cortesía al abrir (Leaving Home)",
            "desc": "Enciende antinieblas y posición al desbloquear el coche con el mando a distancia.",
            "byte": 0,
            "bit": 5,
        },
        {
            "id": "iluminacion_ambiental_mmi",
            "nombre": "Regulación iluminación ambiental en MMI",
            "desc": "Habilita en la pantalla MMI el menú de ajuste de intensidad de luz de suelo y paneles de puertas.",
            "byte": 6,
            "bit": 1,
        },
        # ── ELEVALUNAS Y TECHO ──
        {
            "id": "ventanillas_mando_cerrar",
            "nombre": "Cierre confort de ventanillas con mando",
            "desc": "Sube todas las ventanillas automáticamente al mantener pulsado el botón de cerrar del mando.",
            "byte": 1,
            "bit": 2,
        },
        {
            "id": "ventanillas_mando_abrir",
            "nombre": "Apertura confort de ventanillas con mando",
            "desc": "Baja todas las ventanillas al mantener pulsado el botón de abrir del mando a distancia.",
            "byte": 1,
            "bit": 3,
        },
        {
            "id": "techo_solar_mando",
            "nombre": "Cierre confort de techo solar con mando",
            "desc": "Cierra el techo solar automáticamente junto a las ventanillas con el mando a distancia.",
            "byte": 1,
            "bit": 4,
        },
        {
            "id": "cierre_lluvia_rain_closing",
            "nombre": "Cierre automático por lluvia (Rain Closing)",
            "desc": "Cierra ventanillas y techo automáticamente si el sensor RLS detecta gotas de lluvia con el coche cerrado y aparcado.",
            "byte": 1,
            "bit": 5,
        },
        # ── CIERRES, ACCESOS Y MALETERO ──
        {
            "id": "auto_lock_15kmh",
            "nombre": "Cierre automático de puertas a 15 km/h",
            "desc": "Bloquea automáticamente todas las cerraduras al superar 15 km/h (seguridad anti-asalto).",
            "byte": 2,
            "bit": 0,
        },
        {
            "id": "auto_unlock_llave",
            "nombre": "Desbloqueo automático al retirar la llave",
            "desc": "Abre automáticamente los seguros de todas las puertas al sacar la llave del contacto.",
            "byte": 2,
            "bit": 1,
        },
        {
            "id": "apertura_selectiva_puertas",
            "nombre": "Apertura selectiva de puertas (1 toque / 2 toques)",
            "desc": "Una pulsación en el mando abre solo la puerta del conductor; una segunda pulsación abre todas las demás.",
            "byte": 2,
            "bit": 2,
        },
        {
            "id": "apertura_maletero_retardo",
            "nombre": "Apertura remota maletero con retardo de seguridad",
            "desc": "Exige mantener presionado el botón de maletero durante 1.5s para evitar aperturas involuntarias en el bolsillo.",
            "byte": 2,
            "bit": 3,
        },
        # ── ALARMAS, CONFIRMACIONES Y SEGURIDAD ──
        {
            "id": "bip_cierre_alarma",
            "nombre": "Pitido acústico (bip) al cerrar con mando",
            "desc": "Emite una confirmación sonora corta con la bocina de la alarma al bloquear el vehículo.",
            "byte": 3,
            "bit": 1,
        },
        {
            "id": "bip_apertura_alarma",
            "nombre": "Confirmación acústica (doble bip) al abrir con mando",
            "desc": "Emite dos confirmaciones sonoras cortas con la bocina de alarma al desbloquear el coche.",
            "byte": 3,
            "bit": 3,
        },
        {
            "id": "parpadeo_intermitentes_cierre",
            "nombre": "Confirmación visual intermitentes al cerrar",
            "desc": "Los intermitentes parpadean una vez para confirmar visualmente el cierre total del coche.",
            "byte": 3,
            "bit": 2,
        },
        {
            "id": "intermitentes_autopista_confort",
            "nombre": "Intermitentes confort de autopista (3 parpadeos)",
            "desc": "Un toque leve sin enclavar la palanca genera una secuencia de 3 intermitencias para cambio de carril.",
            "byte": 3,
            "bit": 4,
        },
        {
            "id": "frenada_emergencia_parpadeo",
            "nombre": "Parpadeo de luces en frenada de emergencia",
            "desc": "Hace parpadear las luces de freno a alta frecuencia ante deceleraciones bruscas en carretera.",
            "byte": 5,
            "bit": 0,
        },
        {
            "id": "luces_emergencia_post_parada",
            "nombre": "4 intermitentes tras detención de emergencia",
            "desc": "Enciende los 4 intermitentes de peligro automáticamente tras detenerse por completo en una frenada de pánico.",
            "byte": 5,
            "bit": 1,
        },
    ],

    "Central Eléctrica / Luces (09)": [
        {
            "id": "cornering_lights",
            "nombre": "Luces de giro en antinieblas (Cornering Lights)",
            "desc": "Enciende el faro antiniebla del lado correspondiente al girar el volante o poner el intermitente a velocidad < 40 km/h.",
            "byte": 4,
            "bit": 0,
        },
        {
            "id": "drl_wink",
            "nombre": "Atenuación luz diurna LED al poner intermitente (Wink)",
            "desc": "Reduce la intensidad o apaga la tira LED diurna frontal mientras parpadea el intermitente para una señalización óptima.",
            "byte": 3,
            "bit": 7,
        },
        {
            "id": "luces_nordicas_traseras",
            "nombre": "Modo Escandinavo / Pilotos traseros permanentes con DRL",
            "desc": "Mantiene los pilotos traseros de posición encendidos de forma continua junto a las luces diurnas LED frontales.",
            "byte": 0,
            "bit": 4,
        },
        {
            "id": "antinieblas_con_largas",
            "nombre": "Antinieblas activos simultáneamente con ráfagas / largas",
            "desc": "Permite mantener los antinieblas delanteros activos al dar luces de carretera o ráfagas.",
            "byte": 2,
            "bit": 1,
        },
        {
            "id": "drl_ajuste_mmi",
            "nombre": "Menú de luces diurnas delanteras en pantalla MMI",
            "desc": "Habilita la casilla para activar o desactivar las luces diurnas LED directamente desde el menú Exterior Lights del MMI.",
            "byte": 3,
            "bit": 0,
        },
        {
            "id": "lavafaros_tiempo_retardo",
            "nombre": "Retardo de activación para eyectores lavafaros xenón",
            "desc": "Exige mantener la palanca más de 2 segundos para disparar el agua de los faros, evitando el gasto innecesario de líquido.",
            "byte": 5,
            "bit": 3,
        },
    ],

    "Cuadro Instrumentos (17)": [
        {
            "id": "needle_sweep",
            "nombre": "Barrido de agujas al arrancar (Needle Sweep)",
            "desc": "Recorrido completo de agujas de velocímetro y cuentavueltas de 0 a tope al poner contacto (estilo S6/RS6).",
            "byte": 1,
            "bit": 0,
        },
        {
            "id": "lap_timer_oil",
            "nombre": "Menú Lap Timer y Temp. Aceite digital en FIS",
            "desc": "Activa en el display central el cronómetro de tiempos de circuito y la lectura numérica de temperatura de aceite motor.",
            "byte": 1,
            "bit": 3,
        },
        {
            "id": "logo_s6_rs6",
            "nombre": "Pantalla de bienvenida deportiva S6 / RS6 en FIS",
            "desc": "Muestra el logotipo de alto rendimiento S6 / RS6 en la pantalla central a color del cuadro al dar el contacto.",
            "byte": 1,
            "bit": 4,
        },
        {
            "id": "aviso_cinturon",
            "nombre": "Aviso acústico cinturón de seguridad",
            "desc": "Alerta sonora periódica si el cinturón del conductor no está abrochado.",
            "byte": 0,
            "bit": 1,
        },
        {
            "id": "aviso_velocidad_120",
            "nombre": "Aviso acústico de exceso de velocidad límite",
            "desc": "Alerta sonora y aviso en pantalla al rebasar el límite de velocidad fijado (ej. 120 km/h en autopista).",
            "byte": 0,
            "bit": 6,
        },
        {
            "id": "desactivar_aviso_bombilla_led",
            "nombre": "Modo Matrícula LED (Desactivar chequeo en frío)",
            "desc": "Desactiva la comprobación por resistencia en frío para poder instalar bombillas o plafones LED sin aviso de fallo en cuadro.",
            "byte": 2,
            "bit": 4,
        },
    ],

    "ABS / ESP (03)": [
        {
            "id": "tpms_indirecto_abs",
            "nombre": "Control de presión neumáticos indirecto (TPMS por ABS)",
            "desc": "Calcula anomalías en el radio de rodadura usando los captadores de velocidad de rueda para detectar pinchazos sin sensores de válvula.",
            "byte": 1,
            "bit": 2,
        },
        {
            "id": "hill_hold_assist",
            "nombre": "Asistente de arranque en pendiente (Hill Hold Assist)",
            "desc": "Mantiene la presión hidráulica de frenos durante 2 segundos en cuesta arriba para arrancar sin que el coche caiga hacia atrás.",
            "byte": 1,
            "bit": 5,
        },
    ],

    "Motor (01)": [
        {
            "id": "drl_luces_diurnas",
            "nombre": "Luces diurnas DRL permanentes",
            "desc": "Mantiene las luces diurnas LED frontales siempre encendidas con el vehículo en marcha.",
            "byte": 0,
            "bit": 3,
        },
        {
            "id": "tempomat_crucero",
            "nombre": "Control de crucero (Tempomat) habilitado",
            "desc": "Habilita la lógica del regulador automático de velocidad de crucero en la ECU motor EDC17.",
            "byte": 5,
            "bit": 0,
        },
        {
            "id": "limite_velocidad_motor",
            "nombre": "Desactivación limitador suave de velocidad máxima",
            "desc": "Ajuste de mapeado de la lógica secundaria de velocidad punta en ECU motor 2.7 TDI V6.",
            "byte": 6,
            "bit": 2,
        },
    ],
}
