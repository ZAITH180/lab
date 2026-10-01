from conexion import Conexion
from decimal import Decimal
import math

class ClienteCRUD:
    def __init__(self):
        self.db = Conexion()

    def consultar(self, id=None):
        if id:
            return self.db.ejecutar_consulta("SELECT * FROM clientes WHERE id=?", (id,))
        return self.db.ejecutar_consulta("SELECT * FROM clientes ORDER BY id DESC")

    def registrar(self, nombre, nit, tipo='empresa', direccion=''):
        if tipo!= 'empresa':
            raise ValueError("El Impuesto a las Actividades Económicas requiere un cliente de tipo empresa.")
        return self.db.ejecutar_escritura(
            "INSERT INTO clientes (nombre, nit, tipo, direccion) VALUES (?,?,?,?)",
            (nombre, nit, tipo, direccion)
        )

    def modificar(self, id, nombre, nit, direccion):
        return self.db.ejecutar_escritura(
            "UPDATE clientes SET nombre=?, nit=?, direccion=? WHERE id=?",
            (nombre, nit, direccion, id)
        )

    def eliminar(self, id):
        # Validar si tiene periodos facturados
        fact = self.db.ejecutar_consulta("SELECT COUNT(*) as c FROM periodos WHERE cliente_id=? AND estado='Facturado'", (id,))
        if fact[0]['c'] > 0:
            raise ValueError("El período ya fue utilizado en recibos y no puede recalcularse automáticamente.")
        return self.db.ejecutar_escritura("DELETE FROM clientes WHERE id=?", (id,))

class TarifaService:
    def __init__(self):
        self.db = Conexion()

    def seleccionar_tarifa(self, balance: Decimal, producto_codigo: str):
        balance = Decimal(balance)
        rows = self.db.ejecutar_consulta(
            "SELECT * FROM tarifas WHERE producto_codigo=? AND CAST(desde AS DECIMAL) <=? AND CAST(hasta AS DECIMAL) >=?",
            (producto_codigo, str(balance), str(balance))
        )
        # RF11 - Tarifa inexistente
        if len(rows) == 0:
            raise ValueError("No existe una tarifa configurada para el balance indicado.")
        # RF12 - Tarifas superpuestas
        if len(rows) > 1:
            raise ValueError("Existe más de una tarifa aplicable. Corrija la tabla tarifaria.")
        return rows[0]

    def calcular_impuesto(self, balance, tarifa_row):
        """Implementa 10.1 y 10.4 del doc"""
        balance = Decimal(str(balance))
        desde = Decimal(str(tarifa_row['desde']))
        precio_base = Decimal(str(tarifa_row['precio_base']))
        adicional = Decimal(str(tarifa_row['adicional']))
        porcentaje = Decimal(str(tarifa_row['porcentaje']))

        detalle = {}

        if porcentaje > 0:
            # Tarifa porcentual - RF no truncar 1.50
            impuesto = balance * porcentaje / Decimal('100')
            detalle = {
                "tipo": "porcentual",
                "balance": float(balance),
                "rango": f"{tarifa_row['desde']} a {tarifa_row['hasta']}",
                "porcentaje": float(porcentaje),
                "precio_base": float(precio_base),
                "excedente": 0,
                "bloques": 0,
                "adicional": 0,
                "resultado": float(impuesto)
            }
        else:
            excedente = balance - desde
            if excedente < 0:
                excedente = Decimal('0')
            # Si es exactamente inicio del rango, bloques 0
            if excedente == 0:
                bloques = 0
            else:
                bloques = math.ceil(float(excedente) / 1000.0)

            impuesto = precio_base + (Decimal(bloques) * adicional)

            detalle = {
                "tipo": "bloques",
                "balance": float(balance),
                "rango": f"{tarifa_row['desde']} a {tarifa_row['hasta']}",
                "precio_base": float(precio_base),
                "excedente": float(excedente),
                "bloques": bloques,
                "adicional": float(adicional),
                "porcentaje": 0,
                "resultado": float(impuesto),
                "formula": f"{precio_base} + ({bloques} x {adicional}) = {impuesto}"
            }

        # RF: conservar 6 decimales interno, mostrar 2 decimales
        impuesto_6 = impuesto.quantize(Decimal('0.000001'))
        impuesto_2 = impuesto.quantize(Decimal('0.01'))

        return impuesto_6, impuesto_2, detalle