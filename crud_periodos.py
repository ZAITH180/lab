from conexion import Conexion
from crud_clientes import TarifaService
from decimal import Decimal
from datetime import datetime
import json

class PeriodoCRUD:
    def __init__(self):
        self.db = Conexion()
        self.tarifa_service = TarifaService()

    def listar(self, cliente_id=None):
        if cliente_id:
            return self.db.ejecutar_consulta("SELECT * FROM periodos WHERE cliente_id=? ORDER BY fecha_desde", (cliente_id,))
        return self.db.ejecutar_consulta("""
            SELECT p.*, c.nombre as cliente_nombre FROM periodos p
            JOIN clientes c ON c.id=p.cliente_id ORDER BY p.fecha_desde DESC
        """)

    def validar_periodo(self, cliente_id, producto_codigo, desde, hasta, balance):
        # RF03 Fechas
        if desde >= hasta:
            raise ValueError("La fecha Hasta debe ser posterior a la fecha Desde.")
        if Decimal(str(balance)) <= 0:
            raise ValueError("Ingrese un balance mayor que cero.")

        # RF05 - Hasta puede coincidir con Desde del siguiente, por eso usamos < y > no <= >=
        # RF04 - No superposición: [Desde, Hasta) -> se superpone si NOT (existente_hasta <= nuevo_desde OR existente_desde >= nuevo_hasta)
        superpuestos = self.db.ejecutar_consulta("""
            SELECT * FROM periodos WHERE cliente_id=? AND producto_codigo=?
            AND NOT (fecha_hasta <=? OR fecha_desde >=?)
        """, (cliente_id, producto_codigo, desde, hasta))

        if len(superpuestos) > 0:
            raise ValueError("El período indicado se superpone con un período existente.")

        # RF10, RF11, RF12 - Tarifa
        tarifa = self.tarifa_service.seleccionar_tarifa(Decimal(str(balance)), producto_codigo)
        return tarifa

    def registrar_periodo(self, cliente_id, producto_codigo, desde, hasta, balance, cantidad=1.00, usuario='admin'):
        tarifa = self.validar_periodo(cliente_id, producto_codigo, desde, hasta, balance)
        precio_6, precio_2, detalle = self.tarifa_service.calcular_impuesto(balance, tarifa)

        subtotal = Decimal(str(cantidad)) * precio_2

        # RF15 Trazabilidad - guardar tarifa, formula, version
        tarifa_json = json.dumps({
            "tarifa_id": tarifa['id'],
            "rango": f"{tarifa['desde']}-{tarifa['hasta']}",
            "precio_base": str(tarifa['precio_base']),
            "adicional": str(tarifa['adicional']),
            "porcentaje": str(tarifa['porcentaje']),
            "detalle_calculo": detalle,
            "version": "BLOQUES_CEIL_v1"
        })

        # Transacción RF - cliente, periodo, asignación
        ops = [(
            """INSERT INTO periodos
            (cliente_id, producto_codigo, fecha_desde, fecha_hasta, balance, cantidad, precio_mensual, subtotal, tarifa_aplicada, formula_version, usuario, fecha_calculo)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cliente_id, producto_codigo, desde, hasta, str(balance), str(cantidad), str(precio_2), str(subtotal), tarifa_json, "BLOQUES_CEIL_v1", usuario, datetime.now().isoformat())
        )]

        # Ejecutar transacción
        conn = self.db.conectar()
        try:
            cur = conn.cursor()
            for sql, params in ops:
                cur.execute(sql, params)
                periodo_id = cur.lastrowid

            # Auditoria RF17
            cur.execute("INSERT INTO auditoria (periodo_id, accion, balance_nuevo, usuario, fecha) VALUES (?,?,?,?,?)",
                        (periodo_id, 'CREACION', str(balance), usuario, datetime.now().isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

        return {"id": periodo_id, "precio_mensual": float(precio_2), "detalle": detalle, "subtotal": float(subtotal)}

    def calcular_preview(self, balance, producto_codigo):
        """RF17 Cálculo inmediato sin guardar"""
        tarifa = self.tarifa_service.seleccionar_tarifa(Decimal(str(balance)), producto_codigo)
        _, precio_2, detalle = self.tarifa_service.calcular_impuesto(balance, tarifa)
        return {"precio": float(precio_2), "detalle": detalle, "tarifa": dict(tarifa)}