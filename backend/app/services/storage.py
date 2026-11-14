import os
import uuid
from typing import Optional
from backend.app.config import settings

# If supabase client is available and configured, we can use it
try:
    from supabase import create_client, Client
    _supabase_available = True
except ImportError:
    _supabase_available = False


class StorageService:
    def __init__(self):
        self.bucket = settings.STORAGE_BUCKET
        self.local_dir = os.path.abspath(settings.STORAGE_LOCAL_FALLBACK_DIR)
        os.makedirs(self.local_dir, exist_ok=True)
        self.client: Optional[Client] = None

        if _supabase_available and settings.SUPABASE_URL and settings.SUPABASE_KEY and not settings.TESTING:
            try:
                self.client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            except Exception:
                self.client = None

    def generate_random_storage_path(self, case_id: str, ext: str) -> str:
        """
        Rule 3: Store files under a random UUID path, never the original filename.
        Path format: {case_id}/{random_uuid}.{ext}
        """
        random_name = f"{uuid.uuid4().hex}.{ext}"
        return f"{case_id}/{random_name}"

    def upload_file(self, storage_path: str, content: bytes, mime_type: str) -> str:
        """Uploads raw bytes to private storage under the random UUID path."""
        # If client configured and not testing, upload to Supabase Storage
        if self.client and not settings.TESTING:
            res = self.client.storage.from_(self.bucket).upload(
                path=storage_path,
                file=content,
                file_options={"content-type": mime_type, "upsert": "false"}  # Never overwrite
            )
            return storage_path

        # Local storage fallback (used for tests and offline development)
        local_target = os.path.join(self.local_dir, storage_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(local_target), exist_ok=True)
        
        # Rule 1: Never overwrite existing file
        if os.path.exists(local_target):
            raise FileExistsError(f"File already exists at {storage_path}. Overwrite is strictly forbidden.")

        with open(local_target, "wb") as f:
            f.write(content)
        return storage_path

    def download_file(self, storage_path: str) -> bytes:
        """Retrieves raw bytes from private storage."""
        if self.client and not settings.TESTING:
            return self.client.storage.from_(self.bucket).download(storage_path)

        local_target = os.path.join(self.local_dir, storage_path.replace("/", os.sep))
        if not os.path.exists(local_target):
            raise FileNotFoundError(f"Storage object not found: {storage_path}")

        with open(local_target, "rb") as f:
            return f.read()


storage_service = StorageService()

