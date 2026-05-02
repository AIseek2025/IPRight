"""Data export and import utilities for the demo application."""

import csv
import io
import json
from datetime import datetime
from typing import Optional, Any


class DataExporter:
    """Export data in various formats."""

    @staticmethod
    def to_csv(data: list[dict], fields: Optional[list[str]] = None) -> str:
        """Convert list of dicts to CSV string."""
        if not data:
            return ""
        output = io.StringIO()
        all_fields = fields or list(data[0].keys())
        writer = csv.DictWriter(output, fieldnames=all_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
        return output.getvalue()

    @staticmethod
    def to_json(data: Any, indent: int = 2) -> str:
        """Convert data to formatted JSON string."""
        return json.dumps(data, ensure_ascii=False, indent=indent, default=str)

    @staticmethod
    def to_excel_format(data: list[dict], sheet_name: str = "Sheet1") -> bytes:
        """Convert list of dicts to Excel-like format (CSV bytes for download)."""
        csv_content = DataExporter.to_csv(data)
        return csv_content.encode("utf-8-sig")

    @staticmethod
    def generate_filename(prefix: str, extension: str) -> str:
        """Generate a timestamped filename for exports."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{timestamp}.{extension}"


class DataImporter:
    """Import data from various formats."""

    @staticmethod
    def from_csv(csv_content: str, field_mapping: Optional[dict[str, str]] = None) -> list[dict]:
        """Parse CSV content into list of dicts."""
        if not csv_content.strip():
            return []
        reader = csv.DictReader(io.StringIO(csv_content))
        results = []
        for row in reader:
            if field_mapping:
                mapped = {}
                for csv_field, model_field in field_mapping.items():
                    if csv_field in row:
                        mapped[model_field] = row[csv_field]
                results.append(mapped)
            else:
                results.append(dict(row))
        return results

    @staticmethod
    def from_json(json_content: str) -> Any:
        """Parse JSON content."""
        return json.loads(json_content)

    @staticmethod
    def validate_import_data(
        data: list[dict],
        required_fields: list[str],
        field_validators: Optional[dict[str, callable]] = None,
    ) -> tuple[list[dict], list[dict]]:
        """Validate imported data and separate valid/invalid records."""
        valid: list[dict] = []
        invalid: list[dict] = []

        for i, record in enumerate(data):
            errors = []
            for field in required_fields:
                if field not in record or not record[field]:
                    errors.append(f"缺少必填字段: {field}")

            if field_validators:
                for field, validator in field_validators.items():
                    if field in record and record[field]:
                        try:
                            record[field] = validator(record[field])
                        except Exception as e:
                            errors.append(f"字段 {field} 校验失败: {e}")

            record["_row"] = i + 1
            if errors:
                record["_errors"] = errors
                invalid.append(record)
            else:
                valid.append(record)

        return valid, invalid


def export_users_csv(users: list[dict]) -> str:
    """Export users to CSV format."""
    fields = ["id", "name", "role", "email", "phone", "department", "status", "created_at"]
    exporter = DataExporter()
    return exporter.to_csv(users, fields)


def export_devices_csv(devices: list[dict]) -> str:
    """Export devices to CSV format."""
    fields = ["id", "name", "type", "location", "status", "ip", "last_check"]
    exporter = DataExporter()
    return exporter.to_csv(devices, fields)


def export_alerts_csv(alerts: list[dict]) -> str:
    """Export alerts to CSV format."""
    fields = ["id", "device", "type", "level", "time", "status"]
    exporter = DataExporter()
    return exporter.to_csv(alerts, fields)


def import_users_from_csv(csv_content: str) -> tuple[list[dict], list[dict]]:
    """Import users from CSV with validation."""
    required = ["name", "email", "role"]
    validators = {
        "email": lambda v: v.strip().lower(),
        "name": lambda v: v.strip(),
        "role": lambda v: v.strip(),
    }
    importer = DataImporter()
    data = importer.from_csv(csv_content)
    return importer.validate_import_data(data, required, validators)


class BackupManager:
    """Simple backup management utility."""

    def __init__(self, backup_dir: str = "/var/backups"):
        self.backup_dir = backup_dir

    def create_backup(self, data: dict, backup_type: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{backup_type}_{timestamp}.json"
        filepath = f"{self.backup_dir}/{filename}"

        backup_data = {
            "type": backup_type,
            "timestamp": datetime.now().isoformat(),
            "version": "1.0",
            "data": data,
        }

        import os
        os.makedirs(self.backup_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)

        return filepath

    def list_backups(self, backup_type: Optional[str] = None) -> list[dict]:
        import os
        if not os.path.exists(self.backup_dir):
            return []
        backups = []
        for filename in os.listdir(self.backup_dir):
            if filename.endswith(".json"):
                if backup_type and not filename.startswith(backup_type):
                    continue
                filepath = os.path.join(self.backup_dir, filename)
                stat = os.stat(filepath)
                backups.append({
                    "filename": filename,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                })
        return sorted(backups, key=lambda b: b["created_at"], reverse=True)

    def restore_backup(self, filename: str) -> Optional[dict]:
        filepath = f"{self.backup_dir}/{filename}"
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def cleanup_old_backups(self, retention_days: int) -> int:
        import os
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=retention_days)
        removed = 0
        if os.path.exists(self.backup_dir):
            for filename in os.listdir(self.backup_dir):
                filepath = os.path.join(self.backup_dir, filename)
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                if mtime < cutoff:
                    os.remove(filepath)
                    removed += 1
        return removed
