"""Вход через Microsoft Entra ID (Azure AD) — OAuth2/OIDC через MSAL.

Активируется тремя переменными окружения:
  AZURE_CLIENT_ID      — Application (client) ID регистрации приложения
  AZURE_CLIENT_SECRET  — секрет клиента
  AZURE_TENANT_ID      — Directory (tenant) ID организации

Пока переменные не заданы, кнопка на странице входа не показывается,
а маршруты отвечают 404 — код безопасно «спит».
"""
import os
import uuid

SCOPES = ['User.Read']


def enabled():
    return all(os.environ.get(k) for k in
               ('AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET', 'AZURE_TENANT_ID'))


def _client():
    import msal
    authority = f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}"
    return msal.ConfidentialClientApplication(
        os.environ['AZURE_CLIENT_ID'],
        client_credential=os.environ['AZURE_CLIENT_SECRET'],
        authority=authority,
    )


def build_auth_url(redirect_uri, state):
    return _client().get_authorization_request_url(
        SCOPES, state=state, redirect_uri=redirect_uri)


def acquire_token(code, redirect_uri):
    """Exchange the auth code; returns MSAL result dict (id_token_claims on success)."""
    return _client().acquire_token_by_authorization_code(
        code, scopes=SCOPES, redirect_uri=redirect_uri)


def new_state():
    return uuid.uuid4().hex
