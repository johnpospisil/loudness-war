"""Build tests/fixtures/highlevel_fixture.tar.zst from the first 20 high-level dump records.

Streams only the first few MB of part 0 over HTTP; adds one invalid-JSON member.
Run once: uv run python tests/fixtures/make_highlevel_fixture.py
"""

import io
import tarfile
from pathlib import Path

import zstandard

from lw.build import parse_highlevel as hl
from lw.build import parse_lowlevel as ll

HERE = Path(__file__).parent


def main() -> None:
    members = []
    r = ll.ResumableHTTPReader(hl.part_url(0))
    for name, raw in ll.iter_documents(io.BufferedReader(r)):
        members.append((name, raw))
        if len(members) == 20:
            break
    r.close()
    prefix = members[0][0].split("/highlevel/")[0]
    members.append(
        (f"{prefix}/highlevel/ff/f/ffffffff-ffff-ffff-ffff-ffffffffffff-0.json", b"{not json")
    )
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in members:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    (HERE / "highlevel_fixture.tar.zst").write_bytes(
        zstandard.ZstdCompressor(level=19).compress(buf.getvalue())
    )


if __name__ == "__main__":
    main()
