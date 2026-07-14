"""Документооборот CIS Platform.

Пакет разбит по типам документов; общий движок маршрутов — в helpers.py.
Blueprint определяется здесь, модули ниже регистрируют свои маршруты.
"""
from flask import Blueprint

documents = Blueprint('documents', __name__, url_prefix='/documents',
                      template_folder='../../app/templates/documents')

from . import helpers, registry, approvals, requisitions, purchase_orders, defects, counterparties, internal  # noqa: E402,F401
