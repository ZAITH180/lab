from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
from conexion import Conexion
from crud_clientes import ClienteCRUD
from crud_periodos import PeriodoCRUD
from decimal import Decimal

class AppHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.path = "/index.html"
            return SimpleHTTPRequestHandler.do_GET(self)

        elif parsed.path == "/api/clientes":
            crud = ClienteCRUD()
            clientes = crud.consultar()
            self.json_response([dict(c) for c in clientes])

        elif parsed.path.startswith("/api/periodos"):
            qs = parse_qs(parsed.query)
            cliente_id = qs.get('cliente_id', [None])[0]
            crud = PeriodoCRUD()
            periodos = crud.listar(cliente_id)
            self.json_response([dict(p) for p in periodos])

        elif parsed.path == "/api/productos":
            db = Conexion()
            prods = db.ejecutar_consulta("SELECT * FROM productos")
            self.json_response([dict(p) for p in prods])

        else:
            return SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode()
        data = json.loads(body) if body else {}

        try:
            if parsed.path == "/api/clientes/registrar":
                crud = ClienteCRUD()
                id_new = crud.registrar(data['nombre'], data['nit'], data.get('tipo','empresa'), data.get('direccion',''))
                self.json_response({"ok": True, "id": id_new})

            elif parsed.path == "/api/clientes/modificar":
                crud = ClienteCRUD()
                crud.modificar(data['id'], data['nombre'], data['nit'], data['direccion'])
                self.json_response({"ok": True})

            elif parsed.path == "/api/clientes/eliminar":
                crud = ClienteCRUD()
                crud.eliminar(data['id'])
                self.json_response({"ok": True})

            elif parsed.path == "/api/tarifas/calcular": # RF17 cálculo inmediato
                crud = PeriodoCRUD()
                res = crud.calcular_preview(data['balance'], data['producto_codigo'])
                self.json_response(res)

            elif parsed.path == "/api/periodos/registrar": # Registro independiente RF01
                crud = PeriodoCRUD()
                res = crud.registrar_periodo(
                    data['cliente_id'], data['producto_codigo'],
                    data['desde'], data['hasta'], data['balance'],
                    data.get('cantidad', 1.00), data.get('usuario','admin')
                )
                self.json_response({"ok": True, **res})

            else:
                self.json_response({"error": "Ruta no encontrada"}, 404)

        except ValueError as ve:
            self.json_response({"error": str(ve)}, 400)
        except Exception as e:
            self.json_response({"error": f"Error interno: {str(e)}"}, 500)

    def json_response(self, obj, status=200):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(obj, default=str).encode())

if __name__ == "__main__":
    Conexion().init_db()
    print("DB inicializada con tabla faltante 6000.01-8000.00 para validar RF11")
    print("Servidor en http://localhost:8000")
    HTTPServer(("0.0.0.0", 8000), AppHandler).serve_forever()