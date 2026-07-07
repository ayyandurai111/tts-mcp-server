"""
Safe extraction of the uploaded project zip to a temporary directory.
"""

import os
import zipfile


class ZipExtractError(ValueError):
    """Raised for invalid/corrupt zips or unsafe archive contents."""


def extract_zip(zip_path, dest_dir):
    """
    Extract `zip_path` into `dest_dir`, guarding against:
      - corrupt / non-zip files
      - zip-slip path traversal (entries that try to escape dest_dir)

    Returns the path to `dest_dir` on success.
    """
    if not os.path.isfile(zip_path):
        raise ZipExtractError(f"Zip file not found: {zip_path}")

    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise ZipExtractError(f"'{zip_path}' is not a valid zip file: {e}") from e

    with zf:
        bad_member = zf.testzip()
        if bad_member is not None:
            raise ZipExtractError(
                f"'{zip_path}' appears to be corrupt (bad CRC on member: {bad_member})"
            )

        dest_abs = os.path.abspath(dest_dir)
        os.makedirs(dest_abs, exist_ok=True)

        for member in zf.infolist():
            member_path = os.path.abspath(os.path.join(dest_abs, member.filename))
            if not member_path.startswith(dest_abs + os.sep) and member_path != dest_abs:
                raise ZipExtractError(
                    f"Unsafe path in zip (would extract outside target dir): "
                    f"{member.filename}"
                )

        try:
            zf.extractall(dest_abs)
        except OSError as e:
            raise ZipExtractError(f"Failed to extract '{zip_path}': {e}") from e

    return dest_abs
