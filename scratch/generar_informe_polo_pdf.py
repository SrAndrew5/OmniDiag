# -*- coding: utf-8 -*-
"""
Generador de Informe Técnico Oficial en PDF para Volkswagen Polo 9N3
Vehículo: VW Polo 9N3 (2007) 1.9 TDI PD - Confort 6Q0 959 433 E
"""

import os
import subprocess
import shutil

HTML_CONTENT = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
    @page {
        size: A4;
        margin: 12mm 15mm 12mm 15mm;
    }
    body {
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
        color: #1e293b;
        margin: 0;
        padding: 0;
        font-size: 12.5px;
        line-height: 1.45;
        background: #ffffff;
    }
    .header {
        border-bottom: 3px solid #0284c7;
        padding-bottom: 10px;
        margin-bottom: 14px;
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
    }
    .header-title h1 {
        margin: 0 0 3px 0;
        font-size: 20px;
        color: #0f172a;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .header-title .subtitle {
        font-size: 12px;
        color: #64748b;
        font-weight: 500;
    }
    .badge-certified {
        background: #0284c7;
        color: #ffffff;
        padding: 5px 12px;
        border-radius: 16px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        display: inline-block;
    }
    .meta-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 10px 12px;
        margin-bottom: 15px;
    }
    .meta-item .label {
        font-size: 10px;
        color: #64748b;
        text-transform: uppercase;
        font-weight: 700;
        margin-bottom: 2px;
    }
    .meta-item .value {
        font-size: 12.5px;
        color: #0f172a;
        font-weight: 600;
    }
    .meta-item .value.accent {
        color: #0284c7;
        font-family: Consolas, monospace;
        font-weight: 700;
    }
    .kpi-row {
        display: flex;
        gap: 10px;
        margin-bottom: 16px;
    }
    .kpi-card {
        flex: 1;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 10px;
        border-radius: 6px;
        text-align: center;
    }
    .kpi-num {
        font-size: 20px;
        font-weight: 900;
        color: #0f172a;
    }
    .kpi-num.danger { color: #dc2626; }
    .kpi-num.warning { color: #d97706; }
    .kpi-num.success { color: #16a34a; }
    .kpi-label {
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        color: #64748b;
        margin-top: 2px;
    }
    .section-title {
        font-size: 13.5px;
        font-weight: 700;
        color: #0f172a;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        border-left: 4px solid #0284c7;
        padding-left: 8px;
        margin-top: 14px;
        margin-bottom: 10px;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 14px;
        font-size: 11.5px;
    }
    th {
        background: #f1f5f9;
        text-align: left;
        padding: 8px 10px;
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        color: #475569;
        border-bottom: 2px solid #cbd5e1;
    }
    td {
        padding: 8px 10px;
        border-bottom: 1px solid #e2e8f0;
        vertical-align: top;
    }
    .dtc-code {
        font-family: Consolas, monospace;
        font-weight: 700;
        font-size: 12px;
        color: #dc2626;
    }
    .badge-static {
        background: #fee2e2;
        color: #991b1b;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 700;
        display: inline-block;
    }
    .badge-esporadico {
        background: #fef3c7;
        color: #92400e;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 700;
        display: inline-block;
    }
    .badge-ok {
        background: #dcfce7;
        color: #166534;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 700;
        display: inline-block;
    }
    .info-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 10px 12px;
        margin-bottom: 12px;
        font-size: 11.5px;
    }
    .info-card h4 {
        margin: 0 0 5px 0;
        font-size: 12px;
        color: #0f172a;
        font-weight: 700;
    }
    .highlight-box {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 6px;
        padding: 10px 12px;
        margin-bottom: 12px;
        font-size: 11.5px;
    }
    .footer {
        border-top: 1px solid #e2e8f0;
        padding-top: 8px;
        margin-top: 15px;
        font-size: 10px;
        color: #94a3b8;
        display: flex;
        justify-content: space-between;
    }
</style>
</head>
<body>

<div class="header">
    <div class="header-title">
        <h1>Informe Pericial de Diagnosis Forense y Confort</h1>
        <div class="subtitle">AudiDiag Pro Diagnosis Suite · Protocolo VAG K-Line KWP1281</div>
    </div>
    <div style="text-align: right;">
        <span class="badge-certified">AUDITORÍA K-LINE</span>
        <div style="font-size: 10.5px; color: #64748b; margin-top: 4px;">Fecha: 03/10/2026</div>
    </div>
</div>

<div class="meta-grid">
    <div class="meta-item">
        <div class="label">Vehículo</div>
        <div class="value">VW Polo 9N3 (2007)</div>
    </div>
    <div class="meta-item">
        <div class="label">Motorización</div>
        <div class="value">1.9 TDI PD (Bomba-Inyector)</div>
    </div>
    <div class="meta-item">
        <div class="label">Centralita Confort (46)</div>
        <div class="value accent">6Q0 959 433 E</div>
    </div>
    <div class="meta-item">
        <div class="label">Codificación EEPROM</div>
        <div class="value accent">00019 (WSC: 00788)</div>
    </div>
    <div class="meta-item">
        <div class="label">Interfaz Hardware</div>
        <div class="value">FTDI KKL USB (COM4)</div>
    </div>
    <div class="meta-item">
        <div class="label">Protocolo Físico</div>
        <div class="value">K-Line Pin 7 (10.400 Baud)</div>
    </div>
    <div class="meta-item">
        <div class="label">Plataforma Bastidor</div>
        <div class="value">PQ24 (VAG Polo/Ibiza/Fabia)</div>
    </div>
    <div class="meta-item">
        <div class="label">Estado Cierre Selectivo</div>
        <div class="value" style="color: #16a34a; font-weight: 700;">DESACTIVADO (ÉXITO)</div>
    </div>
</div>

<div class="kpi-row">
    <div class="kpi-card">
        <div class="kpi-num danger">4</div>
        <div class="kpi-label">Averías Totales</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-num danger">2</div>
        <div class="kpi-label">Fallos Estáticos (Activos)</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-num warning">2</div>
        <div class="kpi-label">Fallos Esporádicos (Memoria)</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-num success">0</div>
        <div class="kpi-label">Fallos en Frenos / ABS</div>
    </div>
</div>

<div class="section-title">1. Memoria de Averías Registradas (Auto-Scan K-Line)</div>
<table>
    <thead>
        <tr>
            <th style="width: 14%;">Módulo</th>
            <th style="width: 12%;">Código</th>
            <th style="width: 14%;">Tipo / Estado</th>
            <th style="width: 38%;">Descripción del Componente</th>
            <th style="width: 22%;">Impacto y Dictamen Técnico</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><strong>Módulo 46</strong><br><span style="color:#64748b; font-size:10px;">Confort / BCM</span></td>
            <td><span class="dtc-code">00928</span></td>
            <td><span class="badge-esporadico">ESPORÁDICO</span></td>
            <td><strong>Unidad de cierre centralizado, lado conductor (F220)</strong><br><span style="color:#64748b;">Señal inverosímil en los microinterruptores internos de la cerradura.</span></td>
            <td>Fallo clásico de microswitch en cerraduras VAG. Puede provocar disparos de alarma erróneos o confusión en la detección de puerta abierta/cerrada.</td>
        </tr>
        <tr>
            <td><strong>Módulo 46</strong><br><span style="color:#64748b; font-size:10px;">Confort / BCM</span></td>
            <td><span class="dtc-code">00932</span></td>
            <td><span class="badge-static">ESTÁTICO</span></td>
            <td><strong>Motor elevalunas, lado conductor (V147)</strong><br><span style="color:#64748b;">Avería eléctrica en el circuito de control o potencia del motor de la puerta.</span></td>
            <td>Revisar conector del fuelle pasamuros entre la puerta del conductor y el pilar A (cables cortados/pelados o falso contacto).</td>
        </tr>
        <tr>
            <td><strong>Módulo 01</strong><br><span style="color:#64748b; font-size:10px;">Motor (EDC15/17)</span></td>
            <td><span class="dtc-code">01650</span><br><span style="color:#64748b; font-size:9.5px;">SAE P0672</span></td>
            <td><span class="badge-static">ESTÁTICO</span></td>
            <td><strong>Bujía incandescente Cilindro 2 (Q11)</strong><br><span style="color:#64748b;">Circuito defectuoso / circuito abierto en el calentador nº 2.</span></td>
            <td>Calentador del cilindro 2 fundido. Afecta al arranque en frío y regeneración. Comprobar con tester de resistencia (~0.6 a 1.2 Ω) y sustituir.</td>
        </tr>
        <tr>
            <td><strong>Módulo 01</strong><br><span style="color:#64748b; font-size:10px;">Motor (EDC15/17)</span></td>
            <td><span class="dtc-code">00532</span></td>
            <td><span class="badge-esporadico">ESPORÁDICO</span></td>
            <td><strong>Tensión de alimentación Borne 30 (B+)</strong><br><span style="color:#64748b;">Valor de tensión de batería por debajo del umbral mínimo operativo.</span></td>
            <td>Tensión baja puntual durante el arranque o por batería baja en pruebas pasadas. El alternador carga correctamente una vez en marcha.</td>
        </tr>
        <tr>
            <td><strong>Módulo 03</strong><br><span style="color:#64748b; font-size:10px;">ABS / ESP</span></td>
            <td><span style="font-weight:700; color:#16a34a;">00000</span></td>
            <td><span class="badge-ok">SIN FALLOS</span></td>
            <td><strong>Sistema de Frenos Antibloqueo y Control de Tracción</strong></td>
            <td>Centralita responde con 0 fallos. Sistema hidráulico y sensores de rueda en perfecto estado.</td>
        </tr>
    </tbody>
</table>

<div class="section-title">2. Auditoría de Confort: Cierre Selectivo y Configuración de EEPROM</div>
<div class="highlight-box">
    <strong>✓ Estado del Cierre Selectivo (1 Toque abre todo):</strong><br>
    Se modificó la codificación de la centralita confort <code>6Q0 959 433 E</code> de <strong>00018</strong> a <strong>00019</strong>. El bit de apertura selectiva ha sido recalculado y grabado con éxito en la memoria EEPROM. Ahora una sola pulsación en el telemando abre simultáneamente todas las puertas y el portón trasero.
</div>

<div class="section-title">3. Análisis Técnico del Pitido / Zumbido de Alarma al Cerrar</div>
<div class="info-card">
    <h4>¿Por qué sigue sonando un pitido/zumbido tras poner el Canal 06 a 0?</h4>
    <ul>
        <li><strong>El Canal 06 solo controla el Claxon normal del volante:</strong> El valor <code>0</code> grabado desactiva con éxito los toques de bocina estándar.</li>
        <li><strong>El sonido no es claxon, es un tono agudo/zumbido de sirena:</strong> Esto confirma al 100% que el coche cuenta con un módulo de alarma acústico dedicado (bien la sirena inteligente VAG <strong>H12 DWA</strong> en el vano/paso de rueda, o una alarma accesoria instalada en concesionario tipo Cobra/Meta System).</li>
        <li><strong>Relación directa con la avería 00928 (Cerradura Conductor):</strong> Al tener la cerradura del conductor el microinterruptor tocado, cuando envías la orden de cierre, el módulo de alarma detecta una discrepancia en el estado de los seguros y emite un zumbido/pitido de aviso o rearme de seguridad.</li>
        <li><strong>Vía de solución:</strong> Revisar bajo el capó si hay una pequeña bocina/sirena adicional con una llave de desactivación, o en su defecto reparar las soldaduras del microinterruptor de la cerradura F220.</li>
    </ul>
</div>

<div class="section-title">4. Consulta de Confort: Subida de Ventanillas y Techo Solar con Mando</div>
<div class="info-card">
    <h4>¿Se pueden subir las ventanillas y cerrar el techo solar manteniendo pulsado el mando?</h4>
    <ul>
        <li><strong>Comportamiento con la Llave Física:</strong> Si introduces el espadín en el bombín de la puerta del conductor, giras hacia la posición de cerrar y <strong>mantienes 2 segundos</strong>, las ventanillas suben y el techo solar (trapa solar) se cierra automáticamente por función de confort mecánica.</li>
        <li><strong>Comportamiento con el Telemando RF:</strong> En la plataforma PQ24 (Polo 9N / 9N3 con módulo confort 6Q0 959 433), Volkswagen <strong>bloqueó de fábrica por firmware</strong> el confort de ventanillas y techo desde los botones de la llave. No se puede activar mediante un simple canal de adaptación (el canal 14 no está disponible en este módulo).</li>
        <li><strong>Afectación por la avería 00932:</strong> El motor elevalunas del conductor tiene grabada la avería estática <code>00932</code>. Mientras exista esta avería o falso contacto en el motor, el módulo confort inhibe las rutinas automáticas de confort de ventanillas.</li>
    </ul>
</div>

<div class="footer">
    <div>AudiDiag Pro CAN & K-Line Diagnostic Framework · Volkswagen Polo 9N3</div>
    <div>Informe Generado con Éxito · Archivo: INFORME_DIAGNOSTICO_VW_POLO_9N.pdf</div>
</div>

</body>
</html>
"""

def main():
    project_dir = r"c:\Users\Iulica\Desktop\AudiDiagProjectGemini"
    desktop_dir = r"C:\Users\Iulica\Desktop"
    
    html_file = os.path.join(project_dir, "informe_polo_temp.html")
    pdf_project = os.path.join(project_dir, "INFORME_DIAGNOSTICO_VW_POLO_9N.pdf")
    pdf_desktop = os.path.join(desktop_dir, "INFORME_DIAGNOSTICO_VW_POLO_9N.pdf")
    
    # 1. Write HTML
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)
    print(f"HTML generado en: {html_file}")
    
    # 2. Compile to PDF using Edge headless
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    cmd = [
        edge_path,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_project}",
        html_file
    ]
    
    print("Exportando a PDF con Microsoft Edge...")
    subprocess.run(cmd, check=True)
    
    if os.path.exists(pdf_project):
        print(f"PDF generado con éxito en el proyecto: {pdf_project}")
        shutil.copy2(pdf_project, pdf_desktop)
        print(f"Copia creada directamente en tu Escritorio: {pdf_desktop}")
    else:
        print("Error: No se encontró el archivo PDF generado.")
        
    if os.path.exists(html_file):
        os.remove(html_file)

if __name__ == "__main__":
    main()
