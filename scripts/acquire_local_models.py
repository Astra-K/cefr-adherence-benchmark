"""Acquire pinned stock 4-bit local models; verify all sizes/LFS hashes."""
import hashlib
import json
from pathlib import Path
import urllib.request
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "2B": ("mlx-community/Qwen3.5-2B-4bit", "674aaa7240b91e8012fcad5d791b7dfe5ba90207"),
    "9B": ("mlx-community/Qwen3.5-9B-4bit", "8b2b98c00a6b4d291155e4890773ca8f769aee53"),
}

def main():
    records = {}
    for size, (repo, revision) in MODELS.items():
        print(f"ACQUIRE {size} {repo}@{revision}", flush=True)
        url = f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true"
        metadata = json.load(urllib.request.urlopen(url, timeout=60))
        assert metadata["sha"] == revision
        path = Path(snapshot_download(repo, revision=revision, max_workers=2,
                                     allow_patterns=["*.json", "*.jinja", "*.txt", "*.safetensors"]))
        checks = []
        for entry in metadata["siblings"]:
            file = path / entry["rfilename"]
            if not file.exists():
                continue
            assert file.stat().st_size == entry["size"], file
            digest = hashlib.file_digest(file.open("rb"), "sha256").hexdigest()
            if entry.get("lfs"):
                assert digest == entry["lfs"]["sha256"], file
            checks.append({"name":entry["rfilename"], "bytes":file.stat().st_size,
                           "sha256":digest})
        index = json.loads((path / "model.safetensors.index.json").read_text())
        for shard in set(index["weight_map"].values()):
            assert any(c["name"] == shard for c in checks), shard
        config = json.loads((path / "config.json").read_text())
        records[size] = {"repo":repo, "revision":revision, "path":str(path),
                         "quantization":config.get("quantization"), "files":checks}
        out = ROOT / "configs/local_models_verified.json"
        out.write_text(json.dumps(records, indent=2)+"\n")
        print(f"VERIFIED {size} {path}", flush=True)
    print("ACQUISITION_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
