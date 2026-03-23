"""Routers del dashboard — cada módulo expone un `router = APIRouter()`."""
from routers import ventas, catalogo, caja, clientes, reportes, historico, chat

__all__ = ["ventas", "catalogo", "caja", "clientes", "reportes", "historico", "chat"]
