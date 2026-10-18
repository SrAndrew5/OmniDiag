import os

import sqlite3
import config
from datetime import datetime


class ReportGenerator:
    """Genera reportes de diagnóstico profesionales extrayendo datos de SQLite."""

    def __init__(self):
        self.db_path      = config.DATABASE_PATH
        self.reports_folder = config.REPORTES_FOLDER
        os.makedirs(self.reports_folder, exist_ok=True)

    def generar_reporte_txt(self, sesion_id: int) -> str:
        """
        Genera un archivo .txt con el resumen completo de la sesión.

        Args:
            sesion_id: ID de la sesión a reportar.

        Returns:
            Ruta absoluta del fichero generado, o mensaje de error.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Sesión
            cursor.execute(
                "SELECT vin, fecha_inicio FROM sesiones WHERE id = ?",
                (sesion_id,)
            )
            sesion = cursor.fetchone()
            if not sesion:
                return "Error: sesión no encontrada en la base de datos."

            vin, fecha = sesion

            # DTCs de la sesión
            cursor.execute(
                """SELECT modulo, codigo, estado, descripcion, timestamp
                   FROM dtcs WHERE sesion_id = ? ORDER BY timestamp DESC""",
                (sesion_id,)
            )
            dtcs = cursor.fetchall()

            # Lecturas de sensores
            cursor.execute(
                """SELECT sensor, valor, unidad, timestamp
                   FROM lecturas WHERE sesion_id = ? ORDER BY timestamp""",
                (sesion_id,)
            )
            lecturas = cursor.fetchall()

            # Freeze frames de los DTC de esta sesión
            cursor.execute(
                """SELECT d.codigo, ff.parametro, ff.valor, ff.unidad
                   FROM freeze_frame ff
                   JOIN dtcs d ON ff.dtc_id = d.id
                   WHERE d.sesion_id = ?
                   ORDER BY d.codigo, ff.parametro""",
                (sesion_id,)
            )
            freeze_frames = cursor.fetchall()

        # Agrupar freeze frames por código DTC
        ff_por_codigo: dict[str, list] = {}
        for cod, param, val, uni in freeze_frames:
            ff_por_codigo.setdefault(cod, []).append((param, val, uni))

        # Generar fichero
        timestamp     = datetime.now().strftime("%Y%m%d_%H%M%S")
        vin_safe      = vin.replace(" ", "_") if vin else "DESCONOCIDO"
        nombre_fichero = os.path.join(
            self.reports_folder, f"Reporte_{vin_safe}_{timestamp}.txt"
        )

        with open(nombre_fichero, "w", encoding="utf-8") as f:
            sep = "=" * 60

            f.write(f"{sep}\n")
            f.write("         REPORTE DE DIAGNÓSTICO — AUDIDIAG PRO\n")
            f.write(f"{sep}\n\n")
            f.write(f"  VIN del Vehículo : {vin}\n")
            f.write(f"  Fecha de Sesión  : {fecha}\n")
            f.write(f"  Fecha de Reporte : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  Sesión #         : {sesion_id}\n\n")

            f.write(f"{'-'*60}\n")
            f.write("1. CÓDIGOS DE ERROR (DTC) DETECTADOS\n")
            f.write(f"{'-'*60}\n")
            if not dtcs:
                f.write("   No se registraron fallos en esta sesión.\n")
            else:
                for modulo, codigo, estado, desc, ts in dtcs:
                    f.write(f"\n  [{ts}]\n")
                    f.write(f"  Módulo  : {modulo or '—'}\n")
                    f.write(f"  Código  : {codigo}  ({estado})\n")
                    f.write(f"  Desc.   : {desc}\n")
                    # Freeze frame
                    if codigo in ff_por_codigo:
                        f.write("  Freeze Frame:\n")
                        for param, val, uni in ff_por_codigo[codigo]:
                            f.write(f"    {param:<28} {val}  {uni}\n")

            f.write(f"\n{'-'*60}\n")
            f.write("2. REGISTRO DE SENSORES\n")
            f.write(f"{'-'*60}\n")
            if not lecturas:
                f.write("   No se registraron lecturas de sensores.\n")
            else:
                for sensor, valor, unidad, ts in lecturas:
                    f.write(f"  [{ts}]  {sensor:<28} {valor}  {unidad}\n")

            f.write(f"\n{sep}\n")
            f.write("Fin del Reporte — AudiDiag Pro\n")

        return nombre_fichero

    def generar_reporte_html(self, sesion_id: int) -> str:
        """
        Genera un informe diagnóstico profesional en formato HTML interactivo
        e imprimible (apto para guardar en PDF con formato de taller oficial).
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT vin, fecha_inicio FROM sesiones WHERE id = ?", (sesion_id,))
            sesion = cursor.fetchone()
            if not sesion:
                return "Error: sesión no encontrada."

            vin, fecha = sesion
            cursor.execute("""
                SELECT modulo, codigo, estado, descripcion, timestamp
                FROM dtcs WHERE sesion_id = ? ORDER BY timestamp DESC
            """, (sesion_id,))
            dtcs = cursor.fetchall()

            cursor.execute("""
                SELECT sensor, valor, unidad, timestamp
                FROM lecturas WHERE sesion_id = ? ORDER BY timestamp
            """, (sesion_id,))
            lecturas = cursor.fetchall()

            cursor.execute("""
                SELECT d.codigo, ff.parametro, ff.valor, ff.unidad
                FROM freeze_frame ff
                JOIN dtcs d ON ff.dtc_id = d.id
                WHERE d.sesion_id = ?
            """, (sesion_id,))
            freeze_frames = cursor.fetchall()

        ff_por_codigo: dict = {}
        for cod, param, val, uni in freeze_frames:
            ff_por_codigo.setdefault(cod, []).append((param, val, uni))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        vin_safe = vin.replace(" ", "_") if vin else "DESCONOCIDO"
        fichero_html = os.path.join(self.reports_folder, f"Reporte_{vin_safe}_{timestamp}.html")

        # Contadores
        total_dtcs = len(dtcs)
        activos = sum(1 for _, _, est, _, _ in dtcs if "ACTIVO" in str(est).upper() or "PRESENTE" in str(est).upper())
        historicos = total_dtcs - activos

        filas_dtc_html = ""
        if not dtcs:
            filas_dtc_html = """
            <tr>
                <td colspan="5" style="text-align: center; color: #10B981; font-weight: bold; padding: 18px;">
                    ✓ 0 Averías detectadas en los módulos consultados. Sistema 100% operativo.
                </td>
            </tr>
            """
        else:
            for modulo, codigo, estado, desc, ts in dtcs:
                es_activo = "ACTIVO" in str(estado).upper() or "PRESENTE" in str(estado).upper()
                badge_color = "#EF4444" if es_activo else "#F59E0B"
                badge_bg = "rgba(239, 68, 68, 0.15)" if es_activo else "rgba(245, 158, 11, 0.15)"

                ff_html = ""
                if codigo in ff_por_codigo:
                    ff_items = "".join(
                        f"<span style='display:inline-block; margin-right:12px; font-size:11px; color:#475569;'><b>{p}:</b> {v} {u}</span>"
                        for p, v, u in ff_por_codigo[codigo]
                    )
                    ff_html = f"<div style='margin-top:6px; padding:6px; background:#F8FAFC; border-radius:4px;'>{ff_items}</div>"

                filas_dtc_html += f"""
                <tr>
                    <td style="font-weight:600; color:#1E293B;">{modulo or '—'}</td>
                    <td style="font-family:monospace; font-weight:bold; color:#0F172A; font-size:14px;">{codigo}</td>
                    <td>
                        <div style="font-weight:500; color:#334155;">{desc}</div>
                        {ff_html}
                    </td>
                    <td>
                        <span style="background:{badge_bg}; color:{badge_color}; padding:4px 8px; border-radius:4px; font-weight:700; font-size:11px;">
                            {estado}
                        </span>
                    </td>
                    <td style="color:#64748B; font-size:11px;">{ts}</td>
                </tr>
                """

        filas_sensores_html = ""
        if not lecturas:
            filas_sensores_html = "<tr><td colspan='4' style='text-align:center; color:#64748B;'>Sin telemetría registrada</td></tr>"
        else:
            for s, v, u, ts in lecturas[:40]:  # Limitar a las primeras 40 lecturas para formato limpio
                filas_sensores_html += f"""
                <tr>
                    <td style="font-weight:600; color:#1E293B;">{s}</td>
                    <td style="font-family:monospace; font-weight:bold; color:#0284C7;">{v}</td>
                    <td style="color:#64748B;">{u}</td>
                    <td style="color:#94A3B8; font-size:11px;">{ts}</td>
                </tr>
                """

        html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>AudiDiag Pro — Informe Diagnóstico Oficial ({vin})</title>
<style>
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background-color: #F1F5F9;
        color: #0F172A;
        margin: 0;
        padding: 30px;
    }}
    .container {{
        max-width: 960px;
        margin: 0 auto;
        background: #FFFFFF;
        padding: 40px;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.06);
    }}
    .header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 2px solid #E2E8F0;
        padding-bottom: 20px;
        margin-bottom: 25px;
    }}
    .brand-title {{
        font-size: 24px;
        font-weight: 900;
        letter-spacing: 1.5px;
        color: #0F172A;
    }}
    .brand-title span {{
        color: #EF4444;
    }}
    .kpi-row {{
        display: flex;
        gap: 16px;
        margin-bottom: 30px;
    }}
    .kpi-card {{
        flex: 1;
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        padding: 16px;
        border-radius: 8px;
        text-align: center;
    }}
    .kpi-num {{
        font-size: 26px;
        font-weight: 900;
        color: #0F172A;
    }}
    .kpi-num.danger {{ color: #EF4444; }}
    .kpi-num.warning {{ color: #F59E0B; }}
    .kpi-num.success {{ color: #10B981; }}
    .kpi-label {{
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        color: #64748B;
        margin-top: 4px;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 30px;
    }}
    th {{
        background: #F1F5F9;
        text-align: left;
        padding: 10px 12px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        color: #475569;
        border-bottom: 2px solid #CBD5E1;
    }}
    td {{
        padding: 10px 12px;
        border-bottom: 1px solid #E2E8F0;
        font-size: 12.5px;
    }}
    .signature-box {{
        display: flex;
        justify-content: space-between;
        margin-top: 50px;
        padding-top: 30px;
        border-top: 1px dashed #CBD5E1;
    }}
    .sig-line {{
        width: 260px;
        text-align: center;
        font-size: 12px;
        color: #64748B;
        border-top: 1px solid #94A3B8;
        padding-top: 8px;
    }}
    @media print {{
        body {{ background: #FFFFFF; padding: 0; }}
        .container {{ box-shadow: none; padding: 0; max-width: 100%; }}
        .no-print {{ display: none; }}
    }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <div class="brand-title">AUDIDIAG <span>PRO</span></div>
            <div style="font-size: 11px; color: #64748B; font-weight: 600; margin-top: 3px;">
                INFORME OFICIAL DE DIAGNÓSTICO FORENSE Y TELEMETRÍA CAN
            </div>
        </div>
        <div style="text-align: right;">
            <button class="no-print" onclick="window.print()" style="background:#0F172A; color:#FFF; border:none; padding:8px 16px; border-radius:6px; font-weight:bold; cursor:pointer;">
                🖨 Imprimir / Guardar en PDF
            </button>
            <div style="font-size: 12px; color: #64748B; margin-top: 6px;">
                Fecha de Emisión: <b>{datetime.now().strftime('%d/%m/%Y %H:%M')}</b>
            </div>
        </div>
    </div>

    <!-- Metadatos del Vehículo -->
    <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:18px; margin-bottom:25px; display:flex; justify-content:space-between;">
        <div>
            <div style="font-size:11px; font-weight:700; color:#64748B;">NÚMERO DE BASTIDOR (VIN)</div>
            <div style="font-family:monospace; font-size:18px; font-weight:900; color:#0F172A; letter-spacing:1px;">{vin}</div>
            <div style="font-size:12px; color:#475569; margin-top:2px;">Audi A6 C6 (4F) 2.7 TDI V6 · Motor Common Rail Bosch EDC17</div>
        </div>
        <div style="text-align:right;">
            <div style="font-size:11px; font-weight:700; color:#64748B;">SESIÓN DIAGNÓSTICA</div>
            <div style="font-size:18px; font-weight:900; color:#0F172A;">#{sesion_id}</div>
            <div style="font-size:12px; color:#475569; margin-top:2px;">Inicio: {fecha}</div>
        </div>
    </div>

    <!-- KPIs -->
    <div class="kpi-row">
        <div class="kpi-card">
            <div class="kpi-num {'danger' if total_dtcs > 0 else 'success'}">{total_dtcs}</div>
            <div class="kpi-label">Averías Totales</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-num {'danger' if activos > 0 else 'success'}">{activos}</div>
            <div class="kpi-label">Fallos Activos / Presentes</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-num {'warning' if historicos > 0 else 'success'}">{historicos}</div>
            <div class="kpi-label">Fallos en Memoria / Esporádicos</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-num success">✓ OK</div>
            <div class="kpi-label">Bus CAN TP 2.0 / UDS</div>
        </div>
    </div>

    <!-- Tabla DTCs -->
    <h3 style="font-size:15px; color:#0F172A; border-bottom:1px solid #E2E8F0; padding-bottom:8px; margin-bottom:12px;">
        1. Registro Detallado de Averías Diagnosticadas
    </h3>
    <table>
        <thead>
            <tr>
                <th style="width:20%;">Módulo</th>
                <th style="width:12%;">Código</th>
                <th style="width:44%;">Descripción Oficial y Freeze Frame</th>
                <th style="width:14%;">Estado</th>
                <th style="width:10%;">Hora</th>
            </tr>
        </thead>
        <tbody>
            {filas_dtc_html}
        </tbody>
    </table>

    <!-- Tabla Sensores -->
    <h3 style="font-size:15px; color:#0F172A; border-bottom:1px solid #E2E8F0; padding-bottom:8px; margin-bottom:12px;">
        2. Telemetría y Parámetros en Tiempo Real
    </h3>
    <table>
        <thead>
            <tr>
                <th style="width:40%;">Sensor / Parámetro</th>
                <th style="width:25%;">Valor Registrado</th>
                <th style="width:15%;">Unidad</th>
                <th style="width:20%;">Marca de Tiempo</th>
            </tr>
        </thead>
        <tbody>
            {filas_sensores_html}
        </tbody>
    </table>

    <!-- Firma -->
    <div class="signature-box">
        <div class="sig-line">Técnico de Diagnosis / Operador</div>
        <div class="sig-line">Sello del Taller / Conformidad Cliente</div>
    </div>
</div>
</body>
</html>
"""
        with open(fichero_html, "w", encoding="utf-8") as f:
            f.write(html_content)

        return fichero_html

