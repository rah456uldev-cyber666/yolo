"""One-time setup: copy the embedding model into models/ so Medibot can run without internet.

Run once (with internet, or after you have used the app once before):
    python scripts/download_models.py

It first looks for the model in your local Hugging Face cache
(e.g. C:\\Users\\<you>\\.cache\\huggingface\\hub), and only downloads it if it is not there.
After this, the project folder contains everything it needs; you can copy the whole
folder (including models/) to another computer and it will work offline.
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
TARGET = os.path.join(ROOT, "models", "all-MiniLM-L6-v2")


def main():
    if os.path.isfile(os.path.join(TARGET, "config.json")):
        print(f"Already present: {TARGET}")
        return
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)

    from huggingface_hub import snapshot_download

    # 1) Try the local cache only (works with no internet if the app was used before).
    try:
        path = snapshot_download(MODEL_ID, local_files_only=True)
        print(f"Found the model in your Hugging Face cache: {path}")
    except Exception:
        print(f"Downloading {MODEL_ID} (about 90 MB, one time only)...")
        try:
            path = snapshot_download(
                MODEL_ID,
                allow_patterns=["*.json", "*.txt", "*.safetensors", "1_Pooling/*", "modules.json"],
                etag_timeout=60,
            )
        except Exception as e:
            sys.exit(
                f"\nCould not download the model: {e}\n\n"
                "If huggingface.co is slow or blocked on your network, try:\n"
                "  * another network (e.g. a mobile hotspot), then run this script again, or\n"
                "  * or download the files manually from\n"
                f"    https://huggingface.co/{MODEL_ID}/tree/main\n"
                f"    into {TARGET} (see readme.txt)."
            )
    shutil.copytree(path, TARGET, dirs_exist_ok=True)
    print(f"Saved the embedding model to {TARGET}\nMedibot can now run offline.")


if __name__ == "__main__":
    os.environ["HF_HUB_OFFLINE"] = "0"  # this script is the one place allowed to download
    main()
