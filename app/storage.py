"""File storage for document attachments.

Defaults to saving on local disk (UPLOAD_FOLDER). If AZURE_STORAGE_CONNECTION_STRING
is set in the environment, uploads go to Azure Blob Storage instead — no code
changes needed elsewhere, just set the env var and install azure-storage-blob.
"""
import os
import uuid
from flask import current_app, send_file, abort

ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg', 'txt', 'csv'
}
MAX_FILE_SIZE_MB = 20


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _local_upload_dir():
    upload_dir = current_app.config.get('UPLOAD_FOLDER', 'instance/uploads')
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _azure_configured():
    return bool(os.environ.get('AZURE_STORAGE_CONNECTION_STRING'))


def save_upload(file_storage):
    """Save an uploaded werkzeug FileStorage. Returns (stored_filename, backend, size_bytes)."""
    from werkzeug.utils import secure_filename

    original = secure_filename(file_storage.filename)
    ext = original.rsplit('.', 1)[1].lower() if '.' in original else ''
    stored_name = f'{uuid.uuid4().hex}.{ext}' if ext else uuid.uuid4().hex

    if _azure_configured():
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError:
            current_app.logger.error(
                'AZURE_STORAGE_CONNECTION_STRING is set but azure-storage-blob '
                'is not installed — falling back to local disk. '
                'Run: pip install azure-storage-blob'
            )
        else:
            conn_str = os.environ['AZURE_STORAGE_CONNECTION_STRING']
            container = os.environ.get('AZURE_STORAGE_CONTAINER', 'attachments')
            service = BlobServiceClient.from_connection_string(conn_str)
            container_client = service.get_container_client(container)
            try:
                container_client.create_container()
            except Exception:
                pass  # already exists
            file_storage.stream.seek(0)
            data = file_storage.stream.read()
            container_client.upload_blob(name=stored_name, data=data, overwrite=False)
            return stored_name, 'azure', len(data)

    # local disk fallback (also the default when Azure isn't configured)
    upload_dir = _local_upload_dir()
    path = os.path.join(upload_dir, stored_name)
    file_storage.stream.seek(0)
    data = file_storage.stream.read()
    with open(path, 'wb') as f:
        f.write(data)
    return stored_name, 'local', len(data)


def send_attachment(attachment):
    """Return a Flask response streaming the attachment back to the browser."""
    if attachment.storage_backend == 'azure':
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError:
            abort(500, description='Azure storage backend not available on this server.')
        conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
        container = os.environ.get('AZURE_STORAGE_CONTAINER', 'attachments')
        service = BlobServiceClient.from_connection_string(conn_str)
        blob_client = service.get_blob_client(container=container, blob=attachment.stored_filename)
        stream = blob_client.download_blob()
        import io
        buf = io.BytesIO()
        stream.readinto(buf)
        buf.seek(0)
        return send_file(buf, download_name=attachment.original_filename, as_attachment=True)

    upload_dir = _local_upload_dir()
    path = os.path.join(upload_dir, attachment.stored_filename)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, download_name=attachment.original_filename, as_attachment=True)