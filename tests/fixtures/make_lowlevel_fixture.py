"""Build tests/fixtures/lowlevel_fixture.tar.zst from the first 20 sample-dump records.

Records are trimmed to the sections the parser reads (lowlevel stats, rhythm scalars,
metadata) to keep the fixture small; two bad members (invalid JSON, empty file) are added.
Run once: uv run python tests/fixtures/make_lowlevel_fixture.py
"""

import io
import json
import tarfile
from pathlib import Path

import zstandard

from lw.build.parse_lowlevel import SAMPLE_PATH, iter_documents

HERE = Path(__file__).parent
KEEP_LL = {
    "average_loudness", "dynamic_complexity", "spectral_rms", "silence_rate_20dB",
    "silence_rate_30dB", "silence_rate_60dB", "spectral_centroid", "spectral_flux",
    "spectral_complexity", "spectral_energy", "spectral_energyband_low",
    "spectral_energyband_middle_low", "spectral_energyband_middle_high",
    "spectral_energyband_high", "barkbands_flatness_db",
}  # fmt: skip


def trim(doc: dict) -> dict:
    return {
        "lowlevel": {k: v for k, v in doc["lowlevel"].items() if k in KEEP_LL},
        "rhythm": {k: doc["rhythm"][k] for k in ("bpm", "onset_rate")},
        "metadata": doc["metadata"],
    }


def main() -> None:
    members = []
    with open(SAMPLE_PATH, "rb") as f:
        for name, raw in iter_documents(f):
            members.append((name, json.dumps(trim(json.loads(raw))).encode()))
            if len(members) == 20:
                break
    prefix = members[0][0].split("/lowlevel/")[0]
    members.append(
        (f"{prefix}/lowlevel/ff/f/ffffffff-ffff-ffff-ffff-ffffffffffff-0.json", b"{not json")
    )
    members.append((f"{prefix}/lowlevel/ee/e/eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee-0.json", b""))

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in members:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    out = HERE / "lowlevel_fixture.tar.zst"
    out.write_bytes(zstandard.ZstdCompressor(level=19).compress(buf.getvalue()))
    print(out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
